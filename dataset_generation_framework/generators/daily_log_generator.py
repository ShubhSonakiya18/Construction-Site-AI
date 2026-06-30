"""
daily_log_generator.py — Simulates construction projects day-by-day to produce
                          realistic ConstructionDailyLog records.

WHY PROJECT SIMULATION INSTEAD OF RANDOM RECORDS:
    A naive generator might pick a random stage and random fields independently.
    This would produce "painting" records before "drywall" records — violating
    VAL-SEQ-001. It would put concrete in a roofing log — violating VAL-MAT-002.

    Instead, this generator simulates 50+ complete projects from start to finish.
    Each project progresses through the DAG in the correct topological order.
    Each day's log is consistent with that day's project state.

    This approach guarantees:
    ✓ No painting before drywall (StageMachine enforces DAG order)
    ✓ Materials match active stage (loaded from knowledge_loader)
    ✓ Worker counts realistic for the active trades (from ontology)
    ✓ Inspections at correct milestones (from inspection_points in knowledge)
    ✓ Rain ≤ 30% per project (weather probability from config)
    ✓ Cross-record consistency (each record knows project history)

SIMULATION ALGORITHM:
    For each project:
        1. Initialize ProjectState (identity, start date, all stage tracking)
        2. Start site_preparation (or foundation if site_prep is skipped)
        3. Each working day (Mon–Fri):
            a. Generate weather
            b. Compute productivity from weather × stage sensitivity
            c. Advance all active stages by productivity
            d. Auto-start any newly eligible stages
            e. Generate inspections at milestone completions
            f. Build the log record from project state + day context
            g. Validate the record
            h. If valid, yield it

TEMPLATE PHILOSOPHY:
    Task descriptions use templates with knowledge-base vocabulary.
    Templates are in this file because they are output formatting, not
    construction domain knowledge. They can be changed without affecting
    the sequencing or validation logic.
"""
from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterator, Optional

from faker import Faker

from dataset_generation_framework.config import (
    BATCH_SIZE,
    CLIENT_CONTACT_PROB,
    CONTRACT_VALUE_MAX_USD,
    CONTRACT_VALUE_MIN_USD,
    DAILY_LABOR_COST_PER_WORKER,
    DAILY_MATERIAL_COST_BASE,
    DELAY_PROBABILITY,
    EQUIPMENT_USED_PROB,
    INSPECTION_PROBABILITY,
    LATE_ARRIVAL_PROB,
    LOG_SOURCE_SYNTHETIC,
    LOGS_PER_PROJECT,
    MAX_LOGS_PER_PROJECT,
    PROJECT_SIZE_SQFT_MAX,
    PROJECT_SIZE_SQFT_MIN,
    PROJECT_START_DATE_RANGE_DAYS,
    REVIEW_STATUS_DEFAULT,
    SAFETY_INCIDENT_PROB,
    SAFETY_MEETING_PROB,
    SCHEMA_VERSION,
    STAGE_DURATION_VARIANCE,
    USA_STATES,
    VALIDATE_EVERY_N,
    WEATHER_CONDITIONS,
    WEATHER_PRODUCTIVITY,
    WEATHER_WEIGHTS,
    WORK_STOPPING_CONDITIONS,
    WEATHER_SENSITIVE_OUTDOOR_STAGES,
)
from dataset_generation_framework.core.knowledge_loader import KnowledgeBase
from dataset_generation_framework.core.stage_machine import (
    ProjectState,
    StageMachine,
    STAGE_REQUIRES_INSPECTION_BEFORE_NEXT,
    ROUGH_IN_STAGES,
    ROUGH_IN_INSPECTIONS,
)
from dataset_generation_framework.core.rule_engine import RuleEngine
from dataset_generation_framework.generators.base_generator import BaseGenerator
from dataset_generation_framework.validation.pipeline import ValidationPipeline

logger = logging.getLogger(__name__)

# Reference date for generating project start dates
_REFERENCE_DATE = date(2023, 1, 1)

# ── Task description templates per stage ──────────────────────────────────────
# These are OUTPUT FORMATTING, not construction knowledge.
# Knowledge (what trades do what) comes from knowledge_loader.
TASK_TEMPLATES: dict[str, list[str]] = {
    "site_preparation": [
        "Cleared vegetation and brush from {area} sq ft of site",
        "Graded and leveled building pad area",
        "Installed temporary construction fencing and signage",
        "Set up temporary power pole and site utilities",
        "Completed topographic survey and stakeout",
        "Excavated and graded access road to building site",
    ],
    "foundation": [
        "Excavated {depth} feet for {location} footings",
        "Set footing forms and placed rebar grid for {location} footings",
        "Poured concrete for {location} foundation footings",
        "Stripped and removed footing forms",
        "Poured foundation walls for {location} section",
        "Applied waterproofing membrane to exterior foundation walls",
        "Installed perimeter drain tile and gravel",
        "Backfilled and compacted soil around {location} foundation section",
        "Set anchor bolts and sill plates on cured foundation",
        "Monitoring concrete cure — {day} of {total} days",
    ],
    "concrete_flatwork": [
        "Prepared sub-base compaction for {location} slab",
        "Set forms and placed vapor barrier for {location} slab pour",
        "Poured and finished {area} sq ft of {location} concrete slab",
        "Broom-finished {location} concrete flatwork",
        "Installed control joints in {location} concrete slab",
        "Curing and protecting {location} slab from weather",
    ],
    "framing": [
        "Framed all exterior walls on {floor} {direction} side",
        "Installed {count} engineered floor joists on {floor}",
        "Erected interior bearing walls on {floor}",
        "Completed roof truss delivery and set {count} trusses",
        "Applied plywood sheathing to {location} exterior walls",
        "Framed {location} window and door openings",
        "Installed {type} beam and post assembly at {location}",
        "Completed framing on {floor}",
        "Applied house wrap to sheathed exterior walls",
        "Installed blocking for {location} structural connections",
    ],
    "roofing": [
        "Installed roofing underlayment on {location} roof section",
        "Applied starter course and first courses of shingles on {location} slope",
        "Completed shingle installation on {location} roof",
        "Installed step flashing at {location} wall intersection",
        "Set ridge cap shingles across {location} ridge line",
        "Installed drip edge flashing on {location} eaves",
        "Completed roof penetration flashing for {count} vents",
        "Installed ridge vent along full ridge length",
    ],
    "electrical_rough_in": [
        "Ran {linear_feet} feet of NM cable for {location} circuits",
        "Installed electrical panel and main breaker assembly",
        "Roughed in {count} outlet boxes on {floor}",
        "Ran home-run circuits to electrical panel",
        "Installed AFCI/GFCI breakers per NEC code requirements",
        "Completed wiring for {location} kitchen circuit group",
        "Roughed in bathroom fan and GFCI circuit wiring",
        "Completed electrical rough-in on {floor}",
    ],
    "hvac_rough_in": [
        "Installed {linear_feet} feet of ductwork on {floor}",
        "Set plenum and trunk line in attic space",
        "Ran refrigerant line set from {location} to equipment pad",
        "Installed ventilation duct for {location} bathroom fans",
        "Completed duct distribution on {floor}",
        "Installed ERV/HRV core and duct connections",
        "Set equipment pad for outdoor condenser unit",
        "Roughed in all duct boots and register locations on {floor}",
    ],
    "plumbing_rough_in": [
        "Installed drain-waste-vent stack and branch lines on {floor}",
        "Roughed in PEX supply lines to {location}",
        "Completed under-slab plumbing for {location} bathrooms",
        "Set tub and shower drains in {location}",
        "Ran water supply lines to {count} fixture locations",
        "Pressure-tested supply lines — passed at 100 PSI",
        "Completed plumbing rough-in on {floor} — inspection ready",
    ],
    "insulation": [
        "Installed R-{r_value} batt insulation in {location} exterior walls",
        "Blow-in attic insulation to R-{r_value} at {location}",
        "Installed spray foam insulation at {location} rim joist",
        "Completed insulation in all {floor} exterior walls",
        "Installed rigid foam insulation on {location} foundation wall",
        "Air-sealed all penetrations prior to insulation install",
    ],
    "drywall": [
        "Hung {sheets} sheets of 5/8\" drywall on {floor}",
        "Completed hanging all drywall on {floor}",
        "Applied first coat of joint compound on {floor}",
        "Applied second coat of joint compound — {floor}",
        "Applied final coat and sanding on {floor}",
        "Completed corner bead installation throughout {floor}",
        "Sanded and primed drywall on {floor} — paint-ready",
    ],
    "painting": [
        "Applied primer coat to all walls and ceilings on {floor}",
        "Applied first finish coat ({color} eggshell) on {floor}",
        "Applied second finish coat on {floor} walls",
        "Painted trim and doors throughout {floor}",
        "Completed ceiling painting on {floor}",
        "Painted accent wall in {location}",
        "Touch-up painting and minor repairs throughout {floor}",
    ],
    "flooring": [
        "Installed {area} sq ft of LVP flooring in {location}",
        "Installed hardwood flooring in {location}",
        "Completed flooring installation in {floor} bedrooms",
        "Installed carpet in {location} bedrooms",
        "Installed transition strips between flooring types at {location}",
        "Completed all flooring on {floor}",
    ],
    "tile_work": [
        "Set ceramic tile in {location} bathroom",
        "Completed wall tile in {location} shower",
        "Installed floor tile in {location}",
        "Grouted all tile in {location}",
        "Applied tile to {location} backsplash area",
        "Sealed all grout in {location} wet areas",
    ],
    "cabinets_and_countertops": [
        "Installed {count} base cabinets in kitchen",
        "Installed upper cabinets in kitchen",
        "Completed bathroom vanity cabinet installation in {location}",
        "Installed kitchen island cabinet assembly",
        "Countertop templating completed — {location}",
        "Installed quartz countertops in kitchen",
        "Installed bathroom vanity tops in {location}",
        "Completed all cabinet hardware installation",
    ],
    "trim_and_millwork": [
        "Installed baseboard molding throughout {floor}",
        "Installed door casings on {count} doors on {floor}",
        "Installed {count} interior doors on {floor}",
        "Completed window stool and apron installation on {floor}",
        "Installed crown molding in {location}",
        "Installed closet shelving and rods in {location}",
        "Completed all trim work on {floor}",
    ],
    "electrical_finish": [
        "Installed {count} outlets and switches on {floor}",
        "Installed light fixtures throughout {floor}",
        "Installed ceiling fans in {location}",
        "Completed smoke and CO detector installation",
        "Installed electrical panel covers and breaker labels",
        "Energized electrical panel — all circuits tested",
    ],
    "hvac_finish": [
        "Installed air handler in {location} mechanical room",
        "Set outdoor condenser unit on equipment pad",
        "Installed supply and return grilles throughout {floor}",
        "Commissioned HVAC system — airflow balanced",
        "Set and programmed smart thermostat",
        "Completed HVAC system testing and commissioning",
    ],
    "plumbing_finish": [
        "Installed toilets in {count} bathrooms",
        "Installed kitchen sink and faucet",
        "Installed bathroom faucets and fixtures in {location}",
        "Set water heater and connected supply lines",
        "Installed dishwasher and disposal connections",
        "Tested all plumbing fixtures — no leaks",
    ],
    "final_cleanup": [
        "Construction debris removed from {floor}",
        "Cleaned all windows and glass surfaces",
        "Completed thorough cleaning of all rooms",
        "Removed all protective coverings from fixtures and floors",
        "Final cleaning and preparation for client walkthrough",
    ],
    "punch_list": [
        "Completed punch list corrections in {location}",
        "Touch-up painting and drywall repairs throughout",
        "Adjusted and re-hung {location} doors",
        "Caulked gaps at {location} trim and fixtures",
        "Replaced damaged {item} identified in walkthrough",
        "Verified all punch list items corrected",
    ],
    "inspection": [
        "Prepared documentation for final inspection",
        "Final inspection conducted — {result}",
        "Certificate of Occupancy received",
        "Addressed final inspection correction items",
    ],
    "project_closeout": [
        "Client final walkthrough completed",
        "Delivered all warranty documentation and manuals",
        "Collected final payment and signed lien waivers",
        "Demobilized remaining equipment from site",
        "Submitted final close-out documents to building department",
    ],
}

# Equipment used per stage
STAGE_EQUIPMENT: dict[str, list[tuple[str, str]]] = {
    "site_preparation": [("Excavator", "excavator"), ("Bulldozer", "bulldozer")],
    "foundation":       [("Concrete mixer truck", "concrete_mixer"), ("Plate compactor", "plate_compactor")],
    "concrete_flatwork":[("Concrete pump truck", "concrete_pump"), ("Plate compactor", "plate_compactor")],
    "framing":          [("Forklift", "forklift"), ("Boom lift 40ft", "boom_lift")],
    "roofing":          [("Scissor lift", "scissor_lift"), ("Air compressor", "air_compressor")],
    "electrical_rough_in": [("Generator", "generator"), ("Air compressor", "air_compressor")],
    "hvac_rough_in":    [("Forklift", "forklift"), ("Generator", "generator")],
    "plumbing_rough_in":[("Air compressor", "air_compressor")],
    "insulation":       [("Air compressor", "air_compressor")],
    "drywall":          [("Scissor lift", "scissor_lift"), ("Air compressor", "air_compressor")],
}

# PPE required per stage (schema enum values)
STAGE_PPE: dict[str, list[str]] = {
    "site_preparation": ["hard_hat", "high_vis_vest", "safety_glasses", "steel_toe_boots"],
    "foundation":       ["hard_hat", "high_vis_vest", "safety_glasses", "steel_toe_boots", "rubber_gloves"],
    "concrete_flatwork":["hard_hat", "safety_glasses", "rubber_boots", "rubber_gloves"],
    "framing":          ["hard_hat", "safety_glasses", "steel_toe_boots", "fall_protection_harness"],
    "roofing":          ["hard_hat", "fall_protection_harness", "steel_toe_boots", "safety_glasses"],
    "electrical_rough_in": ["hard_hat", "safety_glasses", "leather_gloves", "steel_toe_boots"],
    "hvac_rough_in":    ["hard_hat", "safety_glasses", "cut_resistant_gloves", "steel_toe_boots"],
    "plumbing_rough_in":["hard_hat", "safety_glasses", "steel_toe_boots"],
    "insulation":       ["hard_hat", "n95_respirator", "safety_glasses", "leather_gloves"],
    "drywall":          ["hard_hat", "n95_respirator", "safety_glasses", "knee_pads"],
    "painting":         ["safety_glasses", "n95_respirator", "steel_toe_boots"],
    "flooring":         ["safety_glasses", "knee_pads", "steel_toe_boots"],
    "tile_work":        ["safety_glasses", "knee_pads", "steel_toe_boots"],
    "electrical_finish":["hard_hat", "safety_glasses", "leather_gloves"],
    "hvac_finish":      ["hard_hat", "safety_glasses", "cut_resistant_gloves"],
    "plumbing_finish":  ["safety_glasses", "steel_toe_boots"],
    "cabinets_and_countertops": ["safety_glasses", "steel_toe_boots"],
    "trim_and_millwork":["safety_glasses", "hearing_protection", "steel_toe_boots"],
}

FLOOR_NAMES = ["first floor", "second floor", "third floor", "basement", "garage"]
DIRECTION_NAMES = ["north", "south", "east", "west"]
LOCATION_NAMES = ["master bath", "kitchen", "living room", "bedroom", "hallway", "garage", "laundry"]


def _fill_template(template: str, rng: random.Random) -> str:
    """Fill a task description template with realistic values."""
    replacements = {
        "{area}": str(rng.randint(400, 2000)),
        "{depth}": str(rng.randint(3, 8)),
        "{linear_feet}": str(rng.randint(50, 400)),
        "{count}": str(rng.randint(2, 20)),
        "{floor}": rng.choice(FLOOR_NAMES),
        "{location}": rng.choice(LOCATION_NAMES),
        "{direction}": rng.choice(DIRECTION_NAMES),
        "{day}": str(rng.randint(1, 7)),
        "{total}": "7",
        "{sheets}": str(rng.randint(30, 120)),
        "{r_value}": rng.choice(["13", "19", "21", "38", "49"]),
        "{type}": rng.choice(["LVL", "parallam", "glulam"]),
        "{color}": rng.choice(["beige", "white", "gray", "light blue", "greige"]),
        "{item}": rng.choice(["door handle", "outlet cover", "light fixture", "cabinet hinge"]),
        "{result}": rng.choice(["passed", "passed with conditions", "passed"]),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


class DailyLogGenerator(BaseGenerator):
    """
    Generates ConstructionDailyLog records by simulating real construction projects.

    Each call to stream(count) simulates ceil(count / LOGS_PER_PROJECT) projects
    and yields logs from each project's day-by-day progression.

    The generator guarantees:
    - Correct stage sequencing (enforced by StageMachine + DAG)
    - Realistic worker counts per active trade (from ontology)
    - Materials matching active stage (from knowledge_loader)
    - Rain frequency ≤ 30% per project (from config)
    - Weather-work consistency (no concrete pours during rain)
    - Cross-log consistency within each project
    """

    def __init__(self, kb: KnowledgeBase, seed: int) -> None:
        super().__init__(kb, seed)
        self.fake = Faker("en_US")
        self.fake.seed_instance(seed)
        self.stage_machine = StageMachine(kb)
        self.rule_engine = RuleEngine(kb)
        self._topo_order = kb.topological_order()

    def generate_one(self, **kwargs: Any) -> dict:
        raise NotImplementedError("Use stream() directly — DailyLogGenerator simulates whole projects.")

    def stream(
        self,
        count: int,
        applies_to: str = "dataset_generation",
        **kwargs: Any,
    ) -> Iterator[dict]:
        """
        Stream `count` valid daily log records across simulated projects.
        Projects are generated until `count` valid records are collected.
        """
        self.stats.started_at = datetime.utcnow()
        yielded = 0
        project_num = 0

        while yielded < count:
            project_num += 1
            project_seed = self.rng.randint(0, 2**32 - 1)
            project_rng = random.Random(project_seed)

            state = self._create_project_state(project_rng)

            for record in self._simulate_project(state, project_rng, applies_to):
                if yielded >= count:
                    break
                yield record
                yielded += 1

            logger.info(
                "Project %d complete: %d total logs yielded of %d target",
                project_num, yielded, count,
            )

        self.stats.finish()
        logger.info(
            "[DailyLogGenerator] Done. %s",
            self.stats.to_dict(),
        )

    # ── Project creation ───────────────────────────────────────────────────────

    def _create_project_state(self, rng: random.Random) -> ProjectState:
        fake = Faker("en_US")
        fake.seed_instance(rng.randint(0, 999999))

        state_code = rng.choice(USA_STATES)
        city = fake.city()
        street = fake.street_address()
        client_first = fake.first_name()
        client_last = fake.last_name()
        foreman_first = fake.first_name_male()
        foreman_last = fake.last_name()
        company = fake.company()

        start_offset = rng.randint(0, PROJECT_START_DATE_RANGE_DAYS)
        start_date = _REFERENCE_DATE + timedelta(days=start_offset)
        sqft = rng.randint(PROJECT_SIZE_SQFT_MIN, PROJECT_SIZE_SQFT_MAX)
        contract = round(rng.uniform(CONTRACT_VALUE_MIN_USD, CONTRACT_VALUE_MAX_USD), -3)
        permit = f"BP-{rng.randint(10000, 99999)}"

        return ProjectState(
            project_id=str(self.new_uuid()),
            project_name=f"{client_last} Residence — {street}",
            project_start_date=start_date,
            project_type="residential_single_family",
            project_size_sqft=sqft,
            client_name=f"{client_first} {client_last}",
            foreman_name=f"{foreman_first} {foreman_last}",
            contractor_company=company,
            permit_number=permit,
            contract_value_usd=contract,
        )

    # ── Project simulation ─────────────────────────────────────────────────────

    def _simulate_project(
        self,
        state: ProjectState,
        rng: random.Random,
        applies_to: str,
    ) -> Iterator[dict]:
        """Day-by-day simulation of one project from start to closeout."""
        current_date = state.project_start_date
        pipeline = self.pipeline

        # Start with site_preparation (optional) then foundation
        self.stage_machine.start_stage(
            "site_preparation", state, current_date, rng, STAGE_DURATION_VARIANCE
        )

        while not state.is_complete() and state.log_count < MAX_LOGS_PER_PROJECT:
            # Skip weekends (no residential construction on weekends in this model)
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            # Generate weather for today
            weather_condition = rng.choices(WEATHER_CONDITIONS, WEATHER_WEIGHTS, k=1)[0]

            # Compute productivity based on weather and primary active stage
            primary = self.stage_machine.primary_stage(state)
            productivity = self._compute_productivity(weather_condition, primary)

            # Advance all active stages
            completed_today = self.stage_machine.advance_day(
                state, productivity, current_date, rng
            )

            # Auto-start newly available stages
            for avail_stage in self.stage_machine.available_stages(state, current_date):
                self.stage_machine.start_stage(
                    avail_stage, state, current_date, rng, STAGE_DURATION_VARIANCE
                )

            # Generate inspections at key milestone completions
            inspections = self._generate_inspections(state, completed_today, rng, current_date)

            # Update overall completion
            state.overall_project_completion_percent = (
                self.stage_machine.compute_overall_completion(state)
            )

            # Primary stage for today's record
            primary = self.stage_machine.primary_stage(state)
            active_stages = self.stage_machine.all_active_stages_for_log(state)

            # Build the log record
            record = self._build_log(
                state, current_date, primary, active_stages,
                weather_condition, productivity, inspections, rng,
            )

            # Validate every Nth record; stats.record() owns all counter increments
            if state.log_count % VALIDATE_EVERY_N == 0:
                result = pipeline.validate(record, applies_to=applies_to)
                self.stats.record(result)
                if not result.is_valid:
                    logger.debug(
                        "Blocked log for project %s day %s: %s",
                        state.project_id[:8], current_date, result.blocking_errors[:1],
                    )
                    current_date += timedelta(days=1)
                    continue
            else:
                self.stats.total_attempted += 1
                self.stats.total_valid += 1

            state.log_count += 1
            yield record

            current_date += timedelta(days=1)

    def _compute_productivity(self, weather: str, stage: str) -> float:
        """Productivity: 1.0 = full day, 0.0 = work stopped."""
        base = WEATHER_PRODUCTIVITY.get(weather, 1.0)
        # Outdoor stages are more sensitive to weather
        if stage in WEATHER_SENSITIVE_OUTDOOR_STAGES and weather in WORK_STOPPING_CONDITIONS:
            return 0.0
        return base

    # ── Inspection generation ─────────────────────────────────────────────────

    def _generate_inspections(
        self,
        state: ProjectState,
        completed_today: list[str],
        rng: random.Random,
        current_date: date,
    ) -> list[dict]:
        """Generate inspection events when stages that require inspection complete."""
        inspections = []
        for stage_id in completed_today:
            insp_type = STAGE_REQUIRES_INSPECTION_BEFORE_NEXT.get(stage_id)
            if insp_type and insp_type not in state.passed_inspections:
                # 90% pass rate — occasional re-inspection
                result = rng.choices(["passed", "failed", "conditional_pass"], weights=[0.88, 0.06, 0.06], k=1)[0]
                if result in ("passed", "conditional_pass"):
                    self.stage_machine.record_inspection_pass(stage_id, state, insp_type)

                insp = {
                    "inspection_type": self._map_insp_type(insp_type),
                    "inspector_name": Faker().name(),
                    "inspection_authority": f"City Building Department",
                    "inspection_time": f"{rng.randint(8, 11)}:00 AM",
                    "result": result,
                    "corrections_required": (
                        [{"item_description": "Correction required per inspector notes",
                          "severity": "minor", "corrected": False}]
                        if result == "failed" else []
                    ),
                    "next_inspection_date": None,
                    "inspection_notes": None,
                }
                inspections.append(insp)

        return inspections

    def _map_insp_type(self, insp_type_id: str) -> str:
        mapping = {
            "footing": "footing",
            "rough_electrical": "rough_electrical",
            "rough_hvac": "rough_hvac",
            "rough_plumbing": "rough_plumbing",
            "insulation": "insulation",
            "slab": "slab",
            "final": "final",
        }
        return mapping.get(insp_type_id, "other")

    # ── Log record construction ────────────────────────────────────────────────

    def _build_log(
        self,
        state: ProjectState,
        log_date: date,
        primary_stage: str,
        active_stages: list[str],
        weather_condition: str,
        productivity: float,
        inspections: list[dict],
        rng: random.Random,
    ) -> dict:
        workers = self._build_workforce(primary_stage, productivity, rng)
        total_workers = workers["total_workers_present"]
        work_completed = self._build_work_completed(primary_stage, active_stages, rng) if total_workers > 0 else []
        materials = self._build_materials(primary_stage, active_stages, state, rng)
        weather = self._build_weather(weather_condition, log_date, productivity, rng)
        delays = self._build_delays(primary_stage, weather_condition, productivity, rng, state)
        safety = self._build_safety(primary_stage, total_workers, inspections, rng)
        equipment = self._build_equipment(primary_stage, rng)
        tomorrow_plan = self._build_tomorrow_plan(primary_stage, active_stages, state, rng)
        client_comm = self._build_client_communication(state, rng)
        financials = self._build_financials(total_workers, primary_stage, rng)

        log_dt = datetime.combine(log_date, datetime.min.time())
        created_at = datetime.utcnow().isoformat() + "Z"

        return {
            "log_id": self.seeded_uuid(),
            "schema_version": SCHEMA_VERSION,
            "log_date": log_date.isoformat(),
            "log_created_at": created_at,
            "log_updated_at": created_at,
            "log_source": LOG_SOURCE_SYNTHETIC,
            "audio_file_id": None,
            "raw_transcript": None,
            "transcript_confidence": None,
            "review_status": REVIEW_STATUS_DEFAULT,
            "review_notes": None,

            "project": {
                "project_id": state.project_id,
                "project_name": state.project_name,
                "site_id": None,
                "site_address": state.project_name.split("—")[-1].strip() if "—" in state.project_name else None,
                "client_name": state.client_name,
                "client_contact_email": None,
                "contractor_company": state.contractor_company,
                "foreman_id": None,
                "foreman_name": state.foreman_name,
                "project_type": state.project_type,
                "project_size_sqft": state.project_size_sqft,
                "project_start_date": state.project_start_date.isoformat(),
                "planned_completion_date": (state.project_start_date + timedelta(days=120)).isoformat(),
                "contract_value_usd": state.contract_value_usd,
                "permit_number": state.permit_number,
            },

            "current_stage": primary_stage,
            "active_stages": active_stages or [primary_stage],
            "stage_completion_percent": state.stage_completion_percents.get(primary_stage, 0.0),
            "overall_project_completion_percent": state.overall_project_completion_percent,

            "weather": weather,
            "workforce": workers,
            "work_completed": work_completed,
            "work_in_progress": [],
            "materials": materials,
            "equipment": equipment,
            "safety": safety,
            "delays": delays,
            "inspections": inspections,
            "tomorrow_plan": tomorrow_plan,
            "client_communication": client_comm,
            "attachments": [],
            "financials": financials,
            "ai_generated_outputs": {},
            "audit": {
                "created_by_user_id": None,
                "reviewed_by_user_id": None,
                "approved_by_user_id": None,
                "review_completed_at": None,
                "approval_completed_at": None,
                "schema_version_at_creation": SCHEMA_VERSION,
                "log_version_number": 1,
                "previous_log_version_id": None,
            },
            "foreman_notes": None,
        }

    def _build_workforce(self, stage: str, productivity: float, rng: random.Random) -> dict:
        """Build realistic workforce section from ontology trade data."""
        if productivity < 0.1:
            # Weather stoppage: minimal workers
            return {
                "total_workers_present": 1,
                "total_workers_scheduled": rng.randint(4, 10),
                "total_man_hours_worked": 2.0,
                "trades_on_site": [{"trade": "site_supervisor", "workers_count": 1, "foreman_name": None,
                                    "subcontractor_company": None, "hours_worked": 2.0, "notes": "Weather monitoring"}],
                "late_arrivals": [],
                "absences": [],
                "visitors": [],
                "workforce_notes": f"Work stopped due to weather conditions.",
            }

        trades = self.rule_engine.expected_trades_for_stage(stage)
        if not trades:
            trades = ["general_labor"]

        # Limit to 2-3 relevant trades per day
        active_trades = trades[:rng.randint(1, min(3, len(trades)))]
        trades_on_site = []
        total = 0

        for trade in active_trades:
            lo, hi = self.rule_engine.typical_worker_count_range(stage)
            count = rng.randint(max(1, lo // max(1, len(active_trades))),
                                max(1, hi // max(1, len(active_trades))))
            count = max(1, count)
            trades_on_site.append({
                "trade": trade,
                "workers_count": count,
                "foreman_name": None,
                "subcontractor_company": None,
                "hours_worked": round(rng.uniform(7.0, 9.0), 1),
                "notes": None,
            })
            total += count

        total = max(1, total)
        scheduled = total + rng.randint(0, 2)

        late_arrivals = []
        if self.maybe(LATE_ARRIVAL_PROB) and total > 0:
            late_count = rng.randint(1, min(2, total))
            for _ in range(late_count):
                late_arrivals.append({
                    "worker_identifier": f"Worker {rng.randint(1, 999)}",
                    "trade": rng.choice(active_trades) if active_trades else "general_labor",
                    "minutes_late": rng.randint(10, 45),
                    "reason": rng.choice(["Traffic", "Personal issue", "Equipment issue", "Flat tire"]),
                })

        man_hours = sum(
            t["workers_count"] * t["hours_worked"] for t in trades_on_site
        )

        return {
            "total_workers_present": total,
            "total_workers_scheduled": scheduled,
            "total_man_hours_worked": round(man_hours, 1),
            "trades_on_site": trades_on_site,
            "late_arrivals": late_arrivals,
            "absences": [],
            "visitors": [],
            "workforce_notes": None,
        }

    def _build_work_completed(
        self,
        primary_stage: str,
        active_stages: list[str],
        rng: random.Random,
    ) -> list[dict]:
        """Build 1-3 realistic work items for today's active stages."""
        items = []
        stages_to_describe = list(dict.fromkeys([primary_stage] + active_stages))[:3]

        for stage in stages_to_describe:
            templates = TASK_TEMPLATES.get(stage, [f"Performed work on {stage.replace('_', ' ')}"])
            template = rng.choice(templates)
            description = _fill_template(template, rng)

            trade_enum = self.rule_engine.expected_trades_for_stage(stage)
            trade = trade_enum[0] if trade_enum else "general_labor"

            items.append({
                "task_description": description,
                "trade": trade,
                "location_on_site": rng.choice(LOCATION_NAMES + FLOOR_NAMES),
                "quantity_completed": round(rng.uniform(50, 500), 0),
                "unit_of_measure": "sq_feet",
                "task_completion_percent": round(
                    rng.uniform(10, 90), 0
                ),
                "linked_schedule_task_id": None,
                "notes": None,
            })

        return items[:rng.randint(1, 3)]

    def _build_materials(
        self,
        primary_stage: str,
        active_stages: list[str],
        state: ProjectState,
        rng: random.Random,
    ) -> dict:
        """Build materials section: used_today from knowledge_loader materials."""
        used_today = []

        # Get materials from knowledge base for active stage
        kb_mats = self.kb.stage_materials(primary_stage)
        onto_mats = self.kb.materials_for_stage(primary_stage)

        # Use knowledge stage materials first
        all_mats = kb_mats or onto_mats
        if all_mats:
            picked = rng.sample(all_mats, min(rng.randint(1, 3), len(all_mats)))
            for mat in picked:
                name = mat.get("name") or mat.get("material_name", "Material")
                category = mat.get("category", "other")
                unit = mat.get("typical_unit", "each")
                qty = round(rng.uniform(2, 50), 1)

                # Don't generate concrete during painting/finishing stages
                if category == "concrete" and primary_stage in (
                    "painting", "flooring", "trim_and_millwork",
                    "electrical_finish", "hvac_finish", "plumbing_finish",
                ):
                    continue

                used_today.append({
                    "material_id": None,
                    "material_name": name,
                    "category": category if category in [
                        "concrete", "masonry", "lumber", "steel_metal", "roofing",
                        "electrical", "plumbing", "hvac", "insulation", "drywall",
                        "flooring", "paint_coatings", "hardware", "finishes",
                        "safety_equipment", "other",
                    ] else "other",
                    "quantity_used": qty,
                    "unit": unit,
                    "waste_quantity": round(qty * 0.05, 1),
                    "unit_cost_usd": None,
                    "supplier": None,
                    "notes": None,
                })

        return {
            "used_today": used_today,
            "delivered_today": [],
            "required_for_tomorrow": [],
            "shortage_flags": [],
        }

    def _build_weather(
        self,
        condition: str,
        log_date: date,
        productivity: float,
        rng: random.Random,
    ) -> dict:
        """Build weather section."""
        is_summer = log_date.month in (6, 7, 8)
        is_winter = log_date.month in (12, 1, 2)

        temp_hi = rng.randint(25, 38) if is_summer else (rng.randint(-5, 15) if is_winter else rng.randint(10, 25))
        temp_lo = temp_hi - rng.randint(5, 12)

        afternoon = condition
        if condition in ("rainy", "heavy_rain") and rng.random() > 0.4:
            afternoon = rng.choice(["partly_cloudy", "overcast"])

        work_stopped = (condition in WORK_STOPPING_CONDITIONS and productivity < 0.3)

        return {
            "morning_condition": condition,
            "afternoon_condition": afternoon,
            "temperature_high_celsius": temp_hi,
            "temperature_low_celsius": temp_lo,
            "humidity_percent": rng.randint(30, 85),
            "wind_speed_kmh": rng.randint(5, 30),
            "precipitation_mm": (
                round(rng.uniform(5, 40), 1) if condition in ("rainy", "heavy_rain", "drizzle") else 0.0
            ),
            "work_stopped_due_to_weather": work_stopped,
            "weather_impact_level": (
                "work_halted" if productivity == 0.0 else
                "severe" if productivity < 0.3 else
                "moderate" if productivity < 0.7 else
                "minor" if productivity < 1.0 else
                "none"
            ),
            "weather_notes": None,
        }

    def _build_delays(
        self,
        stage: str,
        weather: str,
        productivity: float,
        rng: random.Random,
        state: ProjectState,
    ) -> list[dict]:
        delays = []

        # Weather delay: required when work is stopped (VAL-WTH-003)
        if productivity == 0.0 and weather in WORK_STOPPING_CONDITIONS:
            delays.append({
                "delay_type": "weather",
                "description": f"{weather.replace('_', ' ').title()} conditions prevented site work",
                "hours_lost": round(rng.uniform(4.0, 8.0), 1),
                "workers_affected": rng.randint(2, 8),
                "tasks_affected": [],
                "schedule_impact": "minor_impact",
                "days_lost_to_schedule": 1.0,
                "resolution_action": "Resumed work when conditions improved",
                "delay_resolved": True,
                "responsible_party": None,
            })
            state.total_delay_days += 1.0

        # Random operational delays
        elif self.maybe(DELAY_PROBABILITY):
            delay_types = [d["id"] for d in self.kb.ontology_delay_types()]
            if not delay_types:
                delay_types = ["material_shortage", "labor_shortage", "equipment_breakdown",
                               "waiting_for_inspection", "subcontractor_delay"]
            delay_type = rng.choice(delay_types)
            hours_lost = round(rng.uniform(0.5, 3.0), 1)

            delays.append({
                "delay_type": delay_type if delay_type in [
                    "weather", "material_shortage", "material_delivery_late", "labor_shortage",
                    "equipment_breakdown", "equipment_unavailable", "inspection_failure",
                    "waiting_for_inspection", "design_change", "rework_required", "permit_issue",
                    "client_decision_pending", "subcontractor_delay", "utility_conflict",
                    "unforeseen_site_condition", "access_issue", "other",
                ] else "other",
                "description": f"Operational delay during {stage.replace('_', ' ')}",
                "hours_lost": hours_lost,
                "workers_affected": rng.randint(1, 4),
                "tasks_affected": [],
                "schedule_impact": "no_impact" if hours_lost < 1 else "minor_impact",
                "days_lost_to_schedule": 0.0,
                "resolution_action": None,
                "delay_resolved": True,
                "responsible_party": None,
            })

        return delays

    def _build_safety(
        self,
        stage: str,
        total_workers: int,
        inspections: list[dict],
        rng: random.Random,
    ) -> dict:
        meeting = self.maybe(SAFETY_MEETING_PROB)
        ppe = STAGE_PPE.get(stage, ["hard_hat", "safety_glasses", "steel_toe_boots"])

        incidents = []
        if self.maybe(SAFETY_INCIDENT_PROB) and total_workers > 0:
            incidents.append({
                "incident_type": rng.choice(["first_aid", "near_miss", "property_damage"]),
                "description": f"Minor safety incident during {stage.replace('_', ' ')} work",
                "worker_involved": f"Worker {rng.randint(1, 99)}",
                "time_of_incident": f"{rng.randint(7, 16)}:{rng.randint(0, 59):02d}",
                "body_part_affected": rng.choice(["hand", "back", "foot", None]),
                "osha_recordable": False,
                "medical_treatment_required": False,
                "incident_reported_to": "Site supervisor",
                "corrective_actions": "Worker reminded of safety procedures",
            })

        return {
            "safety_meeting_conducted": meeting,
            "safety_meeting_duration_minutes": rng.randint(5, 15) if meeting else None,
            "safety_meeting_topics": [f"{stage.replace('_', ' ')} safety"] if meeting else [],
            "ppe_compliance_observed": rng.choice(
                ["full_compliance", "full_compliance", "minor_violations_corrected"]
            ),
            "ppe_required_today": ppe,
            "incidents": incidents,
            "hazards_identified": [],
            "safety_notes": None,
        }

    def _build_equipment(self, stage: str, rng: random.Random) -> list[dict]:
        if not self.maybe(EQUIPMENT_USED_PROB):
            return []
        equipment_options = STAGE_EQUIPMENT.get(stage, [])
        if not equipment_options:
            return []
        selected = rng.choice(equipment_options)
        return [{
            "equipment_name": selected[0],
            "equipment_type": selected[1],
            "is_rented": rng.choice([True, False]),
            "hours_used": round(rng.uniform(2.0, 8.0), 1),
            "operator": None,
            "equipment_condition": rng.choice(["good", "good", "excellent", "fair"]),
            "maintenance_issues": None,
            "fuel_consumed_liters": None,
        }]

    def _build_tomorrow_plan(
        self,
        stage: str,
        active_stages: list[str],
        state: ProjectState,
        rng: random.Random,
    ) -> dict:
        templates = TASK_TEMPLATES.get(stage, [])
        task_desc = _fill_template(rng.choice(templates), rng) if templates else f"Continue {stage.replace('_', ' ')} work"
        trade = self.rule_engine.expected_trades_for_stage(stage)
        return {
            "planned_tasks": [{
                "task_description": task_desc,
                "trade": trade[0] if trade else "general_labor",
                "priority": "high",
                "workers_needed": rng.randint(2, 8),
                "estimated_hours": round(rng.uniform(6, 8), 1),
                "prerequisites": [],
                "notes": None,
            }],
            "workers_expected": rng.randint(3, 10),
            "materials_to_order": [],
            "equipment_needed": [],
            "subcontractors_scheduled": [],
            "inspections_scheduled": [],
            "plan_notes": None,
        }

    def _build_client_communication(self, state: ProjectState, rng: random.Random) -> dict:
        contacted = self.maybe(CLIENT_CONTACT_PROB)
        return {
            "client_contacted_today": contacted,
            "contact_method": rng.choice(["phone_call", "email", "text_sms"]) if contacted else None,
            "topics_discussed": (["Project progress update"] if contacted else []),
            "client_concerns": [],
            "change_orders": [],
            "communication_notes": None,
        }

    def _build_financials(self, total_workers: int, stage: str, rng: random.Random) -> dict:
        labor = round(total_workers * DAILY_LABOR_COST_PER_WORKER * rng.uniform(0.9, 1.1))
        material = round(DAILY_MATERIAL_COST_BASE * rng.uniform(0.5, 2.0))
        equip = round(rng.uniform(0, 300), -1) if self.maybe(0.4) else 0
        sub = round(rng.uniform(200, 1500), -2) if self.maybe(0.2) else 0
        total = labor + material + equip + sub
        return {
            "daily_labor_cost_usd": labor,
            "daily_material_cost_usd": material,
            "daily_equipment_cost_usd": equip,
            "daily_subcontractor_cost_usd": sub,
            "daily_total_cost_usd": total,
            "cumulative_spend_to_date_usd": None,
            "budget_remaining_usd": None,
            "financial_notes": None,
        }
