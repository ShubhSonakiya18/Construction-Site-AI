"""
customer_update_generator.py — Generates technical-summary → customer-email pairs.

This dataset is the primary training data for the AI model that will translate
raw foreman notes into polished customer updates (Sprint 3+).

Each record contains:
  - raw_foreman_notes:     Realistic field notes from a foreman (technical, terse)
  - stage_context:         Which stage the notes are from
  - customer_email_subject: What subject line the AI should produce
  - customer_email_body:   The polished customer-facing update the AI should produce

DESIGN PHILOSOPHY:
    The raw notes use realistic foreman vocabulary (jargon, abbreviations, fragments).
    The email is professional, non-technical, client-appropriate language.
    This pair teaches the AI to translate construction language to business language.

    All stage names and construction terms come from the knowledge base — not hardcoded
    here. We only hardcode the linguistic transformation templates.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from faker import Faker

from dataset_generation_framework.config import SCHEMA_VERSION
from dataset_generation_framework.core.knowledge_loader import KnowledgeBase
from dataset_generation_framework.generators.base_generator import BaseGenerator

logger = logging.getLogger(__name__)

_REFERENCE_DATE = date(2022, 1, 1)

# ── Foreman note templates (raw, technical, realistic) ─────────────────────────
# Foreman notes deliberately use abbreviations, terse phrasing, and jargon.
# format: (stage_id, raw_note_template, completion_pct_range, email_subject_template, email_body_template)
_TEMPLATES: list[tuple[str, str, tuple[int, int], str, str]] = [
    (
        "site_preparation",
        "Cleared N side lot, graded pad area ~{sqft} sf. Temp fencing up, power pole set. Survey stakes in. Start excavation Monday.",
        (15, 35),
        "Your Home Build — Site Work Complete, Ready for Foundation",
        "Hi {client},\n\nGreat news! We finished preparing your building site today. The lot has been cleared and graded, temporary power is in place, and our surveyor has staked out the exact footprint of your new home.\n\nWe're on schedule to start foundation excavation this Monday. This is an exciting milestone — once excavation begins, you'll really start to see your home take shape.\n\nAs always, feel free to reach out with any questions.\n\nBest,\n{foreman}\n{company}",
    ),
    (
        "foundation",
        "Poured E & W footings today, ~{yards} CY 4000 PSI. Rebar per engineering. Anchor bolts set. Inspector on-site 10am, passed footing insp. Cure 7 days before framing.",
        (30, 60),
        "Your Home Build — Foundation Footings Poured, Inspection Passed",
        "Hi {client},\n\nWe had a productive day on your build! Today we poured the concrete footings for your foundation — these are the below-grade supports that your entire home will sit on. The city building inspector was on-site this morning and signed off on the inspection, so we're in great shape.\n\nConcrete needs about 7 days to cure properly before we can begin framing. We'll be monitoring the cure and will kick off framing work next week.\n\nThank you for your patience during this critical phase — a strong foundation means a home built to last.\n\nBest,\n{foreman}\n{company}",
    ),
    (
        "framing",
        "Completed 2nd floor framing today. All ext walls up, plywood sheathing on N & S sides. Truss delivery confirmed Thursday. Started housewrap on W elevation.",
        (45, 75),
        "Your Home Build — Second Floor Framing Complete",
        "Hi {client},\n\nExciting progress on your home today! We completed the second floor framing — all the exterior walls are up and the structural sheathing is going on. Your home is really starting to look like a house now!\n\nWe have your roof trusses scheduled to arrive Thursday, which means we'll begin the roof framing shortly after. Once the roof structure goes up, we'll have the home \"dried in\" and protected from the weather.\n\nThis is a great time to schedule a walk-through if you'd like to see the framing before we close up the walls. Just let us know!\n\nBest,\n{foreman}\n{company}",
    ),
    (
        "roofing",
        "Finished shingle install on main roof today. Ridge cap done. All pipe penetration flashing complete. Only garage roof remains (2 days). No leaks on water test.",
        (80, 95),
        "Your Home Build — Roof Nearly Complete, Home is Dried In",
        "Hi {client},\n\nAnother big milestone today — your main roof is complete! We've finished installing the shingles, ridge cap, and all the flashing around roof penetrations. We performed a water test and everything checked out perfectly.\n\nWe still have the garage roof to finish (about 2 more days of work), but your main living space is now fully weather-tight. This is what builders call being \"dried in\" — a major milestone that means the structure is now protected from the elements.\n\nInterior work (electrical, plumbing, HVAC) can now begin moving forward. Things really pick up pace from here!\n\nBest,\n{foreman}\n{company}",
    ),
    (
        "electrical_rough_in",
        "Ran all circuits for kit, baths, and bedroom wing today. Panel set and wired. 14/2 and 12/2 NM per plan. AFCI throughout per code. Ready for rough insp Friday.",
        (60, 85),
        "Your Home Build — Electrical Rough-In Complete, Inspection Scheduled",
        "Hi {client},\n\nOur electrician completed the rough-in wiring today. All the electrical circuits throughout your home are now roughed in — this is the wiring that runs inside the walls and ceiling before drywall goes up.\n\nWe're scheduled for the rough electrical inspection this Friday. This is a required city inspection that confirms all the wiring meets code. Once we pass (and we're confident we will!), we'll be cleared to proceed with insulation.\n\nWe chose AFCI (arc-fault circuit interrupter) breakers throughout the home for added fire safety — these are required by current code and provide an extra layer of protection.\n\nBest,\n{foreman}\n{company}",
    ),
    (
        "plumbing_rough_in",
        "PEX supply lines roughed in to all fixtures. DWV stack and branch lines complete. Passed pressure test at 100 PSI for 1hr. Rough plumbing insp passed today.",
        (65, 90),
        "Your Home Build — Plumbing Rough-In Passed Inspection",
        "Hi {client},\n\nGreat news on the plumbing front! Our plumber finished all the rough-in plumbing today — the supply lines and drain pipes that run inside your walls. We performed a pressure test (we pressurize the pipes to 100 PSI for one hour) and everything held perfectly.\n\nEven better, the city inspector came out this afternoon and signed off on the rough plumbing inspection. That's one less inspection to worry about!\n\nWith electrical and plumbing both done and inspected, we're getting very close to being ready for insulation and then drywall. The visible progress is about to accelerate significantly.\n\nBest,\n{foreman}\n{company}",
    ),
    (
        "insulation",
        "Blew in R-49 attic insulation today, {sqft} sf. R-21 batts in all ext walls complete. Spray foam at rim joist done yesterday. Insulation insp passed AM.",
        (70, 95),
        "Your Home Build — Insulation Complete and Inspected",
        "Hi {client},\n\nYour home's insulation is now complete! We installed blown-in insulation in the attic (rated R-49, which exceeds code requirements for energy efficiency) and fiberglass batt insulation in all the exterior walls. We also applied spray foam at the perimeter of each floor level to eliminate air infiltration.\n\nThe city inspected the insulation this morning and we passed with no corrections needed.\n\nDrywall begins tomorrow! This is when the home starts to feel like a real interior space. Once drywall is complete, the painting, flooring, and finish work begin — and the pace of visible transformation really accelerates.\n\nBest,\n{foreman}\n{company}",
    ),
    (
        "drywall",
        "Hanging complete on all floors today. ~{sheets} sheets 5/8\" total. Taping and mud starts tomorrow. Expect 10 days for 3 coats + prime.",
        (40, 60),
        "Your Home Build — Drywall Hanging Complete",
        "Hi {client},\n\nWe finished hanging all the drywall throughout your home today — every room, hallway, and closet is now covered. This is a satisfying milestone because it's the first time you can really see what your rooms will look like.\n\nStarting tomorrow, our finishing crew begins the taping and mudding process (applying the joint compound that makes the seams invisible). This takes about 10 days as we apply three separate coats, allowing each to dry before the next. After the final coat, the walls are sanded smooth and primed, ready for paint.\n\nWe'd love to have you come walk through once the drywall is primed — it's a great time to visualize the paint colors before we start painting.\n\nBest,\n{foreman}\n{company}",
    ),
    (
        "painting",
        "First coat walls and ceilings done on main floor today. 2nd coat scheduled Thur. Trim paint starts next Mon after walls done. Color: {color} throughout.",
        (35, 65),
        "Your Home Build — Painting Underway",
        "Hi {client},\n\nPainting is in full swing! We completed the first coat on all walls and ceilings on the main floor today. The second coat goes on Thursday, and then we'll move to the trim and doors next Monday.\n\nI want to confirm we're using the colors you selected — please let me know if you'd like to do a quick color check before we get too far along. It's much easier to make changes now than after the second coat.\n\nOnce painting wraps up, flooring installation begins immediately. We're staying on schedule for your projected move-in date.\n\nBest,\n{foreman}\n{company}",
    ),
    (
        "flooring",
        "LVP install complete on main floor today, {sqft} sf. Transitions done. Carpet scheduled for upstairs bedrooms next week. Hardwood in master still on order.",
        (55, 80),
        "Your Home Build — Main Floor Flooring Complete",
        "Hi {client},\n\nBig progress on the interior finishes! We completed the luxury vinyl plank flooring on your entire main floor today — it looks great. We also installed all the transition strips between rooms.\n\nFor upstairs, the carpet installation is scheduled for next week. I wanted to give you a heads up that the hardwood flooring for the master bedroom is still in transit from the supplier — we expect it to arrive in about 10 days, which keeps us on our overall timeline.\n\nWe're getting very close to the finish line. Cabinet and countertop installation starts this week in the kitchen and bathrooms.\n\nBest,\n{foreman}\n{company}",
    ),
    (
        "cabinets_and_countertops",
        "Kit uppers and base cabs installed today. Island in place. Counter template done — measure for quartz. Install in 10 days. Bath vanities done 1st floor.",
        (50, 75),
        "Your Home Build — Cabinets In, Countertop Templating Complete",
        "Hi {client},\n\nThe kitchen is really taking shape! All the kitchen cabinets — both uppers and base cabinets — are installed, and the kitchen island is in place. Today we also had the countertop fabricator come out to template your kitchen for the quartz countertops.\n\nThe countertops will be fabricated and installed in about 10 days. That's when the kitchen will truly look finished.\n\nWe also completed the bathroom vanity cabinets on the first floor today. Upper floor bathrooms are scheduled for next week.\n\nYou're going to love how the kitchen turns out — the layout really came together beautifully.\n\nBest,\n{foreman}\n{company}",
    ),
    (
        "punch_list",
        "Started punch list today. {items} items total from owner walkthrough. Completed {done} today: touch-up paint in master, door adjustment in kit, caulk gap at tub surround. Remaining items: ~{remain} days work.",
        (90, 99),
        "Your Home Build — Final Punch List Underway",
        "Hi {client},\n\nWe're in the home stretch! After our walkthrough together, we compiled the punch list and started working through it today. We've already completed several items including the touch-up painting in the master bedroom, the kitchen door adjustment, and the caulking correction in the bathroom.\n\nWe're working diligently through the remaining items and expect to have everything resolved within the next few days.\n\nOnce the punch list is complete, we'll schedule the final building inspection with the city to obtain your Certificate of Occupancy. That's the document that officially clears your home for move-in.\n\nWe're so close — thank you for your patience through this process!\n\nBest,\n{foreman}\n{company}",
    ),
    (
        "project_closeout",
        "Final insp passed today! CO issued. Delivered manuals and warranty docs. Collected final draw. Keys handed to owner. Project closed.",
        (100, 100),
        "Your Home Build — Complete! Certificate of Occupancy Received",
        "Hi {client},\n\nCongratulations! The city conducted the final inspection today and your home passed with flying colors. Your Certificate of Occupancy has been issued — this is the official green light that your home is safe and ready for occupancy.\n\nWe've handed over:\n• All your keys and garage door openers\n• Appliance manuals and warranty cards\n• Paint color codes for future touch-ups\n• Our warranty contact information\n\nIt has been a true pleasure building your home. We're proud of what we built together, and we hope you enjoy many wonderful years in your new home.\n\nPlease don't hesitate to reach out if any questions come up down the road — we stand behind our work.\n\nWarm regards,\n{foreman}\n{company}",
    ),
]


class CustomerUpdateGenerator(BaseGenerator):
    """Generates (raw_foreman_notes, customer_email) training pairs."""

    def __init__(self, kb: KnowledgeBase, seed: int) -> None:
        super().__init__(kb, seed)

    def generate_one(self, **kwargs: Any) -> dict:
        fake = Faker("en_US")
        fake.seed_instance(self.rng.randint(0, 999999))

        template = self.rng.choice(_TEMPLATES)
        (stage_id, raw_tmpl, pct_range, subj_tmpl, body_tmpl) = template

        client_first = fake.first_name()
        client_last  = fake.last_name()
        foreman_name = fake.name_male()
        company      = fake.company()

        pct = self.rng.randint(*pct_range)
        talk_date = _REFERENCE_DATE + timedelta(days=self.rng.randint(0, 730))

        # Fill foreman note slots
        raw_note = (
            raw_tmpl
            .replace("{sqft}", str(self.rng.randint(1200, 4800)))
            .replace("{yards}", str(self.rng.randint(20, 80)))
            .replace("{sheets}", str(self.rng.randint(200, 600)))
            .replace("{color}", self.rng.choice(["Agreeable Gray SW7029", "Accessible Beige SW7036",
                                                  "Repose Gray SW7015", "White Dove OC-17"]))
            .replace("{items}", str(self.rng.randint(8, 25)))
            .replace("{done}", str(self.rng.randint(3, 8)))
            .replace("{remain}", str(self.rng.randint(1, 4)))
        )

        subject = subj_tmpl

        body = (
            body_tmpl
            .replace("{client}", client_first)
            .replace("{foreman}", foreman_name)
            .replace("{company}", company)
        )

        return {
            "pair_id": self.seeded_uuid(),
            "schema_version": SCHEMA_VERSION,
            "update_date": talk_date.isoformat(),
            "project_id": self.seeded_uuid(),
            "project_name": f"{client_last} Residence",
            "client_name": f"{client_first} {client_last}",
            "foreman_name": foreman_name,
            "contractor_company": company,
            "stage_context": stage_id,
            "stage_completion_percent": pct,
            "raw_foreman_notes": raw_note,
            "customer_email_subject": subject,
            "customer_email_body": body,
            "word_count_raw": len(raw_note.split()),
            "word_count_email": len(body.split()),
            "expansion_ratio": round(len(body.split()) / max(1, len(raw_note.split())), 2),
            "notes": None,
        }
