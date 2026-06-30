# Construction Research — Residential Construction Stages

**Sprint 1 Reference Document**
**Scope:** Residential single-family construction, USA standards (IRC 2021, OSHA 29 CFR 1926)

---

## Why This Document Exists

The AI system extracts information from voice recordings and must understand construction domain context to:
- Identify which stage the foreman is describing
- Validate whether tasks are sequentially possible (e.g., painting before drywall is physically impossible)
- Generate contextually accurate safety toolbox talks
- Predict which materials are likely needed next
- Flag anomalies (e.g., roofing mentioned before framing)

This document is the human-readable reference for the `knowledge/construction_stages.json` file.

---

## The 11 Stages of Residential Construction

### Overview of Sequence

```
1. Foundation
      ↓
2. Concrete Flatwork  ←→ (parallel possible)
      ↓
3. Framing
      ↓
4. Roofing
      ↓
5. Electrical Rough-In  ←→ 6. HVAC Rough-In  ←→ 7. Plumbing Rough-In
      ↓                            ↓                      ↓
      ←←←←←←  Insulation  →→→→→→→→→→→→→→→→→→→→→→→→→→→→→
      ↓
8. Drywall
      ↓
9. Painting
      ↓
10. Finishing (Flooring, Trim, Cabinets, Fixtures)
      ↓
11. Inspection (occurs at multiple stages throughout)
      ↓
Certificate of Occupancy
```

---

## Stage 1: Foundation

### Purpose
Transfers all structural loads of the building safely to stable soil or bedrock. Every wall, floor, roof load travels down through the structure to the foundation and into the earth. An undersized or improperly constructed foundation causes structural failure, settling, cracking, and costly repairs that can require demolishing the building.

### Types (Residential)
| Type | Used When | Characteristics |
|------|-----------|----------------|
| Slab-on-grade | Warm climates, no basement needed | Concrete poured directly on prepared soil |
| Crawl space | Moderate climates, utility access desired | Foundation walls, floor elevated |
| Full basement | Cold climates, extra living space | Full depth excavation, 8+ foot walls |
| Pier-and-beam | Flood zones, expansive soil | Building elevated on concrete piers |

### Typical Duration
- Small residence: 1–2 weeks
- Large residence: 2–3 weeks

### Key Workers
- Excavator operator (licensed, heavy equipment)
- Concrete foreman
- Concrete workers (2–4)
- Form carpenters (2–3)
- General laborers (2–4)
- Surveyor (at layout)

### Critical Materials
| Material | Why It's Critical |
|----------|------------------|
| Ready-mix concrete (3000–4000 PSI) | Structural strength |
| Rebar (#4, #5) | Tensile reinforcement (concrete is strong in compression, weak in tension) |
| Form boards | Contain liquid concrete until cured |
| Waterproofing membrane | Prevents water intrusion, especially in basements |
| Anchor bolts | Connect foundation to framing above |
| Gravel base | Drainage and stable bearing surface |

### Common Delays
1. **Rain/flooding** — Wet excavations, compromised concrete pours
2. **Soil problems** — Unexpected rock, soft soil, high water table
3. **Permit delays** — Cannot excavate without approved building permit
4. **Concrete truck delays** — Must have continuous pour to avoid cold joints
5. **Underground utilities** — Gas, water, electrical lines discovered during excavation

### Safety Hazards (OSHA Critical)

**Trench Collapse — Fatal Risk**
- OSHA's single most dangerous construction hazard
- Soil weighs 100 lbs per cubic foot — a wall collapse buries a worker in seconds
- OSHA 29 CFR 1926.650-652 requires shoring, sloping, or shielding for excavations over 5 feet deep
- Industry rule: Never enter an unprotected trench. Period.

**Concrete Chemical Burns**
- Wet concrete = pH 12–13 (as caustic as bleach)
- Skin contact causes full-thickness chemical burns
- Eye contact can cause permanent vision damage
- Requires rubber gloves, rubber boots, safety glasses at all times

**Underground Utility Strike**
- Hitting a buried electrical conduit with an excavator bucket = electrocution
- Always call 811 (USA "Call Before You Dig") before any excavation
- Hand dig within 18 inches of marked utilities

### Daily Report Fields
- Excavation depth achieved (feet)
- Footings poured (linear feet)
- Slab area poured (sq ft)
- Concrete volume (cubic yards)
- Rebar placed (linear feet)
- Curing status
- Water table notes
- Inspection status

---

## Stage 2: Concrete Flatwork

### Purpose
Creates flat, durable horizontal concrete surfaces: garage slabs, driveways, sidewalks, patios, and interior floor slabs. Flatwork requires precise screeding and finishing to achieve correct slope for drainage and a smooth or textured surface as specified.

### Typical Duration
- Pour day: 1–2 days
- Curing: 7 days to 70% strength, 28 days to full design strength

### Key Technical Facts
- Concrete is measured in cubic yards (1 cubic yard = 27 cubic feet)
- A typical 4-inch thick garage slab, 20x20 feet = ~5 cubic yards
- Air temperature below 40°F or above 95°F requires special procedures
- Cannot pour during rain — water on surface ruins strength and finish

### Common Delays
- Rain during pour (most common)
- Extreme heat causing rapid evaporation and cracking
- Concrete truck delays causing cold joints (different pours that bond poorly)
- Pump breakdown mid-pour

### Safety Hazards
- Chemical burns from prolonged contact
- Heat stress (reflective concrete surface)
- Musculoskeletal strain from kneeling and repetitive finishing motions

---

## Stage 3: Framing

### Purpose
Creates the structural skeleton — the bones of the building. Every wall, floor, and roof surface is built from dimensional lumber or engineered wood products. Framing determines all room dimensions, ceiling heights, window and door locations, and defines all structural load paths.

### Why Framing is the Most Visible Stage
A house goes from a concrete slab to a recognizable structure in 2–3 weeks of framing. Clients are typically most excited and most likely to request site visits during this stage.

### Typical Duration
- 1,500 sq ft house: 10–15 days
- 3,000 sq ft house: 15–25 days
- 5,000+ sq ft: 25–40 days

### Critical Lead Time Issue
**Roof trusses must be ordered 3–6 weeks before needed.** They are custom-manufactured in a factory based on the specific roof design. If a foreman doesn't order them before framing begins, the project can sit with walls built and no roof for weeks. This is one of the most common scheduling failures in residential construction.

**LVL (Laminated Veneer Lumber) beams** — used for large spans like garage openings and load-bearing beams — require 2–4 week lead times. Must be ordered from an engineered lumber supplier with approved shop drawings.

### Common Delays
1. Lumber delivery delays
2. LVL beam lead times (must order early)
3. Truss delivery delays (must order very early)
4. High winds — OSHA stops elevated work at ~25 mph winds
5. Design changes from architect or owner mid-framing

### Safety Hazards (OSHA Statistics)
**Falls — #1 Cause of Construction Fatalities**
- OSHA 29 CFR 1926.501 requires fall protection for workers 6+ feet above lower levels
- Framers working on top of wall plates (8+ feet), on floor decking edges, setting trusses (20+ feet)
- Safety harnesses required on roof
- Guard rails required at floor deck edges

**Nail Gun Injuries**
- 37,000 nail gun injuries per year in USA
- Contact trip nailers (most common) can double-fire
- 3.5" framing nails can penetrate completely through hands and feet
- Never bypass the safety tip

### Daily Report Fields
- Floor level worked (1st floor, 2nd floor, attic)
- Walls framed (which rooms/sections)
- Linear feet of wall plates installed
- Subfloor sq ft installed
- Sheathing sq ft installed
- Roof trusses set (count)
- Hardware installed (joist hangers, hurricane ties)
- Lumber delivered today

---

## Stage 4: Roofing

### Purpose
Creates the weatherproof envelope that protects the entire structure. The roof is the most critical milestone in construction: once it is on, interior work can proceed in any weather. Every day without a roof is a day where framing, materials stored inside, and work in progress is exposed to rain.

### Typical Duration
- Asphalt shingles (most common): 2–4 days for 2,000 sq ft house
- Tile or metal roofing: 7–21 days

### How Roofing is Measured
Roofing materials are sold by the **square** (1 square = 100 sq ft of roof surface). A 2,000 sq ft house typically has a 2,400–3,000 sq ft roof surface (due to pitch) = 24–30 squares. Each square of architectural shingles weighs about 240 lbs and requires 3 bundles.

### Roofing System Components (must install in correct order)
1. Drip edge at eaves (before underlayment)
2. Ice & water shield at eaves and valleys
3. Synthetic underlayment over entire roof
4. Drip edge at rakes (after underlayment)
5. Step flashing at all wall connections
6. Pipe boot flashing at all penetrations
7. Shingles from bottom to top
8. Ridge cap
9. Ridge vent

**If any step is out of order, the roof leaks.** The most common error is forgetting step flashing at walls.

### Common Delays
- Rain (most weather-sensitive stage after flatwork)
- High winds (stop work above 30 mph)
- Material delivery scheduling (shingles are heavy)
- Decking damage discovered during installation

### Safety Hazards
**Falls — Roofers Have Highest Fall Death Rate of Any Trade**
- Personal fall arrest system (harness and anchor) required
- Roof jacks and planking for any pitch over 4:12
- Ladders must be tied off at top
- Never work on wet or icy roof surface

**Heat Stress**
- Black asphalt roof surface in summer = 150°F+
- Air temperature 90°F + roof radiation + sun = severe heat risk
- Schedule roof work early morning in summer
- Mandatory water breaks, shade area, buddy monitoring

---

## Stage 5: Electrical Rough-In

### Purpose
Installs all electrical wiring, conduit, boxes, and the main panel inside walls, floors, and ceilings **before** drywall covers them permanently. This is the first of three "rough-in" trades (electrical, HVAC, plumbing) that all happen simultaneously after framing and before drywall.

### Why "Rough-In" Matters
Rough-in = the work inside the walls. Once drywall goes up, you cannot see or easily access this work. A rough-in inspection is required to verify everything is correct **before** it is covered. This is why inspections are called "cover-up inspections" — they authorize you to cover the work.

### Two Phases of Electrical Work
1. **Rough-In Phase** (before drywall): Panel, all wiring, all boxes. Must pass inspection.
2. **Finish Phase** (after painting): Install outlets, switches, fixtures. No inspection usually needed.

### License Requirements
- A **Master Electrician license** is required in most states to pull electrical permits and be responsible for the installation.
- Journeymen can perform the physical work under a master's license.
- Unlicensed electrical work = illegal, insurance-voiding, and dangerous.

### NEC 2020 Key Requirements (most jurisdictions)
- AFCI (Arc Fault Circuit Interrupter) protection on nearly all circuits in living areas
- GFCI protection in kitchens, bathrooms, garages, outdoors, basements
- Dedicated circuits for: refrigerator, dishwasher, microwave, washer, dryer, HVAC

### Common Delays
- Inspection scheduling (24–72 hours advance notice required)
- Specific panel models or breakers on backorder
- Coordination conflicts with plumbing and HVAC for hole routing

### Safety Hazards
- Electrocution from temporary power on site
- Arc flash from panel work
- Falls while fishing wire in attic or elevated spaces

---

## Stage 6: HVAC Rough-In

### Purpose
Installs ductwork, registers, refrigerant lines, and condensate drain piping inside walls, floors, and ceilings before drywall. The system must be designed to ACCA Manual J (load calculation) and Manual D (duct design) standards to achieve proper heating/cooling and airflow.

### The HVAC Equipment Lead Time Problem
**This is one of the most common causes of schedule delays in residential construction.**

During normal times, HVAC equipment (air handler and condenser unit) has a 2–4 week lead time. During supply chain disruptions (post-COVID era), lead times reached 12–20 weeks. A foreman who doesn't order HVAC equipment before framing begins can find themselves with a complete house waiting weeks for the equipment to arrive.

**Best practice: Order HVAC equipment when framing starts.**

### HVAC System Components
- **Air handler** (inside): Forces air through ducts, contains evaporator coil
- **Condenser unit** (outside): Removes heat in cooling mode
- **Ductwork**: Steel or flex ducts carry conditioned air to every room
- **Refrigerant lines**: Copper tubing connecting inside and outside units
- **Condensate drain**: Removes moisture removed from air during cooling

### License Requirements
- Must be **EPA 608 certified** to handle refrigerants
- Most states require HVAC contractor license

### Common Delays
- Equipment lead times (biggest risk)
- Duct conflicts with structural members, electrical conduit, plumbing
- Inspection scheduling

---

## Stage 7: Plumbing Rough-In

### Purpose
Installs the drain-waste-vent (DWV) system and water supply lines inside walls and floors before drywall. The DWV system must be installed in precise slopes (1/4" per foot for drain pipes) to allow gravity drainage. All drains connect through vent stacks that exit through the roof to maintain atmospheric pressure.

### The Under-Slab Plumbing Critical Point
If the project has a **basement or slab-on-grade**, under-slab drain pipes must be installed **before** the concrete is poured. This is the single most schedule-sensitive coordination point in residential construction. Missing this means jackhammering finished concrete later.

### Two Phases of Plumbing
1. **Rough-In**: All pipe in walls and floor. Must pass pressure test and inspection.
2. **Finish**: Toilets, sinks, faucets, water heater, shower/tub. After drywall and painting.

### Pressure Testing
Before inspection, the plumber must pressure-test the DWV system (usually with air to 5 PSI for 15 minutes) and the water supply lines. Any leak = failed test = find and fix before calling inspector.

### License Requirements
- **Master Plumber license** required to pull permits
- Cannot substitute unlicensed labor for permitted plumbing work

### Safety Hazards
- Soldering torch fire risk near wood framing (most common cause of house fires during construction)
- Chemical burns from PVC primer and cement
- Heavy pipe handling causing back strain

---

## Stage 8: Drywall

### Purpose
Installs gypsum board panels on all interior walls and ceilings to create the smooth surfaces that will be painted. Drywall also provides fire resistance (5/8" Type X drywall in garages), sound isolation, and thermal mass.

### The Three Mandatory Phases
1. **Hanging** — Screw panels to framing. Ceiling first, then walls.
2. **Taping** — Embed paper tape in all joints with first coat of compound.
3. **Finishing** — 2nd coat, 3rd coat, final sand. Each coat must fully dry (24+ hours).

**These phases cannot overlap. Shortcuts cause visible defects under paint.**

### The Inspection Prerequisite
Cannot start drywall until **all three rough-in inspections have passed**: electrical, plumbing, and HVAC. Additionally, an insulation inspection must pass. Four separate inspections before drywall can begin.

A common beginner mistake is scheduling drywall crews before inspections are booked and passed. If one trade fails inspection, the drywall crew arrives and has nothing to do.

### The Humidity Problem
Joint compound is water-based. In high humidity, it takes 48–72 hours to dry instead of 24. In humid climates (Florida, Gulf Coast, Pacific Northwest), drywall finishing can add 2–4 weeks to schedule. Some contractors run dehumidifiers during finishing.

### Safety Hazards
**Silica Dust from Sanding — Serious Long-Term Health Risk**
- Drywall compound contains crystalline silica
- Sanding creates fine respirable dust that reaches deep lungs
- Silicosis is an incurable, fatal disease caused by chronic silica exposure
- OSHA 29 CFR 1926.1153 sets strict silica dust exposure limits
- **N95 minimum during all sanding. HEPA vacuum on sander. Non-negotiable.**

---

## Stage 9: Painting

### Purpose
Applies primer and finish paint coats to all surfaces, providing aesthetics, moisture protection, and surface sealing. Interior and exterior painting require different products and conditions.

### Correct Sequencing with Other Trades
The sequence matters:
1. Prime walls before cabinets installed (easier to paint without cabinets in way)
2. Finish coat on walls after cabinets installed (touch up around cabinets)
3. Primer and first coat on trim/doors before trim is installed (coat all sides)
4. Final coat on trim after installation

**Paint applied in wrong sequence gets damaged by other trades and must be redone.**

### Temperature and Humidity Limits
- Do not paint below 50°F (10°C) — paint doesn't bond properly
- Do not paint above 95°F (35°C) — dries too fast, brushmarks
- Do not paint above 85% relative humidity — blistering and adhesion failure
- Exterior paint should not be applied when rain is expected within 24 hours

### Safety Hazards
- VOC (volatile organic compound) inhalation from oil-based products
- Airless sprayer injection injury (2000–3000 PSI — never point at skin)
- Fall from ladder when overreaching

---

## Stage 10: Finishing

### Purpose
Completes all interior finish work that makes the building livable: flooring, trim carpentry, cabinet installation, countertops, door hanging, and completion of electrical, plumbing, and HVAC finish items. This stage involves the most coordination between trades.

### The Critical Path Sequence Within Finishing
1. Tile first (bathrooms, kitchen backsplash)
2. Hardwood or LVP flooring in bedrooms
3. Base molding and door casings after flooring
4. Cabinet boxes installed
5. Countertop template made (measures actual installed cabinets)
6. Countertop fabricated (1–3 weeks lead time for stone)
7. Countertop installed
8. Plumbing fixtures connected
9. Electrical fixtures installed
10. Carpet last (never before painting or other dusty trades)

**Countertops are one of the most common sources of delay.** Stone countertops must be templated after cabinets are set and level, then fabricated (2–3 weeks for granite/quartz), then installed. This 3–4 week process sits on the critical path.

### Lead Time Items to Order Early
| Item | Typical Lead Time |
|------|------------------|
| Custom cabinets | 6–12 weeks |
| Stone countertops | 2–4 weeks (after template) |
| Custom tile | 4–8 weeks |
| Special order fixtures | 4–12 weeks |
| Freestanding soaking tub | 8–16 weeks |

### Safety Hazards
- Saw injuries (miter saw, table saw) — most common finish trade injuries
- Silica dust from tile cutting (always use wet saw)
- Chemical fumes from adhesives, stains, sealers

---

## Stage 11: Inspection

### Purpose
Official code compliance verification by the Authority Having Jurisdiction (AHJ) — typically the city or county building department. Inspections are not optional and are required to legally occupy a building.

### Types of Inspections (Residential)
| Inspection | When Triggered | Common Pass Rate |
|------------|---------------|-----------------|
| Pre-pour foundation | Before concrete pour | High |
| Footing | After footings poured | High |
| Framing | After all rough-in complete | Moderate |
| Rough electrical | After rough-in, before drywall | Moderate |
| Rough plumbing | After pressure test, before drywall | Moderate |
| Rough HVAC | After rough-in, before drywall | High |
| Insulation | After insulation, before drywall | High |
| Final | All work complete | Moderate |
| Certificate of Occupancy | Final passed | Required for legal occupancy |

### What Inspectors Check
- Compliance with local building code (usually IRC 2021 + local amendments)
- Compliance with NEC (National Electrical Code) for electrical
- Proper materials (correct pipe type, wire gauge, etc.)
- Structural connections (correct fasteners, hangers, straps)
- Safe work practices completed (proper notching of joists, proper blocking)

### Failed Inspection Protocol
1. Inspector provides written list of corrections
2. Contractor corrects all items
3. Contractor schedules re-inspection
4. Re-inspection confirms corrections
5. Work can continue

A failed framing inspection that lists 10 items can cost 3–7 days and significant rework cost. Framing inspections have a meaningful fail rate because there are many code requirements.

### Common Inspection Delay Causes
1. Inspector scheduling (24–72 hour notice required, some areas 1–2 week wait)
2. Approved permit drawings not on site
3. Contractor or responsible party not present during inspection
4. Trade contractors not available to answer inspector questions

---

## Construction Sequencing Rules for AI Validation

The AI extraction engine uses these rules to validate extracted information:

**Absolute Rules (Cannot Violate)**
- Painting cannot happen before drywall
- Roofing cannot happen before framing
- Electrical rough-in cannot happen before framing
- Plumbing rough-in cannot happen before framing
- HVAC rough-in cannot happen before framing
- Drywall cannot happen before all rough-in inspections pass
- Interior finishing cannot happen before drywall
- Flooring cannot happen before painting (in most rooms)
- Under-slab plumbing must happen before any concrete slab pour

**Parallel-Allowed Rules**
- Electrical rough-in, HVAC rough-in, and plumbing rough-in all happen simultaneously
- Roofing and rough-in trades can overlap
- Flatwork and framing can overlap on different parts of the site
- Painting and flooring can happen in different rooms simultaneously

**Common Foreman Voice Patterns**
These phrases from voice recordings map to specific stages:
- "Poured footings" → foundation
- "Set trusses" / "truss delivery" → framing
- "Ran wire" / "roughed electrical" → electrical_rough_in
- "Hung drywall" / "first coat of mud" → drywall
- "Laid tile" / "set cabinets" → finishing
- "Passed inspection" / "inspector came out" → inspection
