# Case Study — Report Structure

**Working title:** Dynamic Flight Re-Routing Under Airspace Disruptions: A Prioritised Multi-Agent A\* Simulation with Human-in-the-Loop Decision Support

**Status tags** used on every factor, feature and experiment in the report:
`[IMPL]` implemented in the simulator · `[SIMP]` implemented in simplified/illustrative form · `[NOT]` not modelled · `[PROP]` proposed / future work

**Rule for the whole report:** every claim is tagged. Nothing tagged `[NOT]` or `[PROP]` is ever reported as a result.

---

## Front matter
- Title page, abstract (150–250 words, ends with the 3 headline findings), keywords
- Declaration of simulation-only scope and safety notice (one paragraph)
- Table of contents, list of figures, list of tables, list of abbreviations
- *(New)* **How to read this report** — the status-tag legend above and a one-page map from research questions to the sections that answer them

---

## Chapter 1 — Introduction
1.1 Background: air traffic management and airspace disruptions
1.2 Problem statement
1.3 Motivation
  - 1.3.1 Historical motivation (9/11 airspace closure; 9W 555 — documented facts only, film dramatisation separated; hypothetical medical emergency labelled as hypothetical)
  - 1.3.2 Economic motivation (fuel price exposure; distance/delay as *proxies*, not fuel cost)
  - 1.3.3 Passenger-first motivation (safety above cost)
  - 1.3.4 Why AI search
1.4 Objectives — technical (T1–T6) and broader (B1–B4)
1.5 Scope and assumptions (synthetic IDs such as SIM100, grid world, simulated runways, no certified performance)
1.6 Research questions RQ1–RQ5
1.7 Contributions (stated so each maps to something in the repo)
1.8 Report organisation
  - *(New)* **Table 1.1 — RQ → experiment → section** (the single most useful table for a marker)

## Chapter 2 — Background and Literature Review
2.1 Air traffic management fundamentals (ATC, flight plans, airways, controlled/restricted airspace, phases of flight, diversion/holding/go-around, route vs runway choice)
2.2 Weather and operational factors in brief *(the long treatment is Chapter 4)*
2.3 AI search for routing: state space, UCS/Dijkstra, A\*, heuristics, time-dependent search
2.4 Multi-agent path planning
  - agents and environments; centralised vs decentralised
  - cooperative/prioritised planning, space-time reservations, Conflict-Based Search (as the optimal alternative)
  - **explicit positioning:** this project is *centralised prioritised planning with reservations*, not CBS and not decentralised negotiation
2.5 Runway assignment and arrival sequencing (aircraft landing problem; separate problem from routing)
2.6 Economic and passenger-centred planning (fuel/delay cost framing; disruption management in airlines)
2.7 Human factors and automation in safety-critical decisions *(moved forward from Chapter 7 so the framework is introduced before it is used)*
2.8 **Review of existing research** — one comparison table for ~12–18 verified papers, columns: objective · method · findings · limitations · relevance
  - areas: A\*/heuristic aircraft routing · weather-aware planning · dynamic restrictions · multi-agent conflict avoidance · runway sequencing · fuel-efficient/passenger-centred planning · human-automation
2.9 Research gap (justified only by what 2.8 shows; phrased as "this project examines…", not "first to…")

> Moved to Appendix A: the aviation glossary (previously 2.2).

## Chapter 3 — Problem Formulation and Methodology
*(New: 3.1 formal problem definition; the rest follows your outline)*
3.1 **Formal problem definition** — states, actions, transitions, hard constraints, objective, what "feasible" means
3.2 End-to-end workflow and data flow (synthetic vs external data clearly separated) → **Figure 3.1**
3.3 Airspace representation (grid, cell size, step = 1 min, airports, hazards over time)
3.4 Search algorithms considered: BFS, UCS, Greedy, A\* (theory only; results in Ch. 6)
3.5 A\* design: f = g + h, the octile heuristic, admissibility (wind discount ≤ 15%, so h is scaled by 0.85), consistency, effect of heuristic choice
3.6 Hard constraints vs soft preferences — table with the code's actual list
3.7 Time-expanded planning: (cell, time) states, hold action, vertex and swap reservations, runway slots, endurance/horizon
3.8 Multi-agent coordination: the three planners (independent / sequential / prioritised), priority ordering, why independent is kept as a baseline
3.9 Disruption detection and replanning: event timeline, rip-up-and-replan, damping, announced-vs-unknown hazards, failure handling
3.10 Landing logic: candidate airports, eligibility rules, diversion, runway occupancy, estimated arrival times (illustrative, not clearances)
3.11 Pseudocode (time-expanded A\*, replanning round) and complexity analysis
3.12 Contributions and limitations of the method
> Merged: the old 3.11 "comparative evaluation" duplicated 6.6; it now lives only in Chapter 6.

## Chapter 4 — Operational Factors and Constraint Modelling
Every section ends with a **status table**: factor · aviation principle · implemented as · tag.

4.1 Wind: direction convention (from vs toward), head/tail/crosswind, gusts, surface vs cruise wind — `[SIMP]`
4.2 Aircraft type, performance and runway compatibility — `[SIMP]` (four profile bands)
4.3 **Landing mass, fuel state and landing feasibility** (MLM/MLW, fuel burn, overweight landing and emergency exceptions, jettison, holding/diversion alternatives, residual fuel and post-impact fire hazard framed correctly) — `[SIMP]` (see note below)
4.4 Runway length, landing distance and surface condition — length `[SIMP]`; wet/contaminated/slope/overrun `[NOT]`
4.5 Weather hazards: visibility, fog, convective cells, wind shear, icing — storm cell and windshear area `[SIMP]`; the rest `[NOT]`
4.6 Approach procedures, navigation and terrain — `[NOT]`
4.7 Airspace restrictions, traffic density and separation (grid exclusivity vs real ATC separation) — `[SIMP]`
4.8 Emergencies and passenger-centred decisions (priority classes, endurance, diversion choice) — `[IMPL]`/`[SIMP]`
4.9 Constraint validation and cost formulation (illustrative objective function J, weights, limits) — objective: distance + wind cost `[IMPL]`; monetary cost `[PROP]`
4.10 Negative scenarios: what happens if constraints are ignored — **shortened to a boxed illustrative list** (tailwind, contaminated runway, restricted airspace, ignored separation, distant airport in an emergency), each pointing to the scenario that tests the safe behaviour
4.11 Implementation-status matrix (one table for the whole chapter) and what extra data would be needed for realism

> Note on 4.3: the simulator currently *forces a hold* for overweight emergency arrivals. The report must describe that honestly, and either (a) the model is changed to compare land-now / hold / divert, or (b) the limitation is stated in 4.3.10 and 7.5.

## Chapter 5 — System Architecture and Implementation
5.1 System overview and user workflow
5.2 Architecture and module responsibilities (`scenarios`, `grid`, `planner`, `engine`, `landing`, `benchmark`, `dashboard/`) → **Figure 5.1**
5.3 Technology stack and reproducibility (Python, Streamlit, Folium; seeds; CLI; tests)
5.4 Data inputs: synthetic fleet; OurAirports; OpenSky snapshot; Open-Meteo (display-only unless the user ticks the wind option); failure handling
5.5 Scenario configuration: how an effects entry becomes behaviour (worked example)
5.6 Planning engine walkthrough: original route → detect conflict → A\* → replan → failure
5.7 **One worked scenario, end-to-end** (e.g. scenario 50) with 5 screenshots: setup · expected · action · output · interpretation → **Figures 5.2–5.6**
5.8 Visualisation: original vs revised routes, time slider, hazards as planner cells
5.9 Metrics and output panel (what each number means and how it is computed)
5.10 Runway/approach outputs and their simplifications
5.11 Testing and verification (41 unit tests; conflict-free sweep over 648 runs; what the tests do *not* prove)
5.12 Implementation challenges and lessons (two bugs found by testing: swap-edge reservation, landing at the closure step — useful honest content)
5.13 Chapter summary
> Merged: the five repeated "scenario 1…5" walkthroughs of the old 5.7 become one worked example here; the others are experiments in Chapter 6.

## Chapter 6 — Experimental Design, Results and Evaluation
6.1 Setup: environment, data, seeds, metrics definitions, controlled variables
6.2 Baseline (no disruption): reference values and the "unimpeded route"
6.3 Closure and restricted-sector experiments (size and position sweeps; scenarios 9–15, 13, 21)
6.4 Wind and runway-suitability sensitivity (crosswind sweep over direction and speed; scenarios 16, 17, 25) — only what the model varies
6.5 Emergency-priority experiments (scenarios 1–8, 33, 38, 40, 41, 48) — priority vs FIFO
6.6 **Algorithm comparison** (BFS, UCS, Greedy, A\*): path cost, nodes expanded, time, success rate, under static and disrupted grids `[PROP until implemented]`
6.7 **Multi-aircraft coordination** (independent vs sequential vs prioritised; conflicts, delay, unserved emergencies; scenarios 27, 32, 36, 37)
6.8 Runway capacity and diversion (scenarios 12, 24, 28, 30, 35, 52)
6.9 Data-resilience experiments (scenarios 42–47; widened footprints, conservative weather, damping)
6.10 Landing-mass experiments — **proposed unless the extension is built**; seeded overweight cases (scenarios 6, 33, 38, 51, 54) reported as illustrations only
6.11 Failure and infeasible cases (scenarios 39, 49, 16): search failure vs operational infeasibility
6.12 Compound/flagship scenarios (50–54)
6.13 Summary of results, answers to RQ1–RQ5 (fills Table 1.1)
6.14 Threats to validity (internal, construct, external)

Each experiment uses one template: **Objective → Setup → Procedure → Results → Visual evidence → Analysis → Limits**, with mean ± 95% interval over ≥10 seeds.

## Chapter 7 — Discussion, Human Oversight and Real-World Implications
7.1 What the results show — and do not show
7.2 Trade-offs: shortest vs feasible; speed vs quality; disruption severity
7.3 Heuristic and cost-function sensitivity; risks of optimising an incomplete objective
7.4 Why algorithmic feasibility is not aviation safety
7.5 Limitations of the synthetic world and the external data (single consolidated limitations section)
7.6 **Human oversight as a design principle** *(merges old 7.6 and 7.7)*
  - roles of pilots, controllers, dispatchers
  - proposed human-in-the-loop workflow (detect → generate → validate → human review → authorise/modify/reject → after-action review) → **Figure 7.1**
  - decision-point table (data quality, feasibility, emergencies, conflicts, novelty, final action)
  - explanations, logging, accountability
  - what is `[IMPL]` (reasons for infeasibility; refusal to invent routes) vs `[PROP]` (approval workflow)
7.7 Uncertainty and the limits of control (mathematical optimality ≠ a good decision)
7.8 Reflection box: human judgement, humility and spiritual perspective — short, clearly marked as reflection, separate from findings
7.9 Deployment considerations: validation, certification, fail-safe behaviour, why this is not a flight-certified system
7.10 Overall discussion

## Chapter 8 — Conclusion and Future Work
8.1 Summary of problem and method
8.2 Summary of findings, tied to RQ1–RQ5
8.3 Contributions
8.4 Limitations in brief (full version is §7.5)
8.5 Responsible use of AI
8.6 Future work, prioritised: (1) land-now/hold/divert landing model, (2) fuel and cost model, (3) CBS or other complete MAPF baseline, (4) real airspace graph and altitude, (5) time-varying weather, (6) explainable HITL interface, (7) validation with domain experts
8.7 Final conclusion

## References
Verified academic sources only (A\* origin; cooperative pathfinding; CBS; aircraft landing problem; air traffic flow management; human-automation). News and film material only for the historical framing, labelled as such.

---

## Appendices
- **A** Aviation glossary (the table from your old 2.2)
- **B** Full scenario catalogue with effects (generated from `scenario_catalogue.json`)
- **C** Pseudocode and complexity derivations
- **D** Model parameters (cell size, step, horizon, per-type limits, occupancy, fuel, landing-mass values) — all flagged illustrative
- **E** Reproducibility: commands, seeds, versions, how every table and figure is regenerated
- **F** Test suite summary
- **G** Implementation-status matrix (the master table behind Chapter 4)
- **H** Extra screenshots

---

## What changed from your outline, and why
**Removed or merged**
| Change | Reason |
|---|---|
| Glossary (2.2) → Appendix A | Reference material interrupts the argument |
| Old 3.11 merged into 6.6 | Same comparison would be written twice |
| Old 5.7 scenario list → one worked example + Chapter 6 | Five walkthroughs duplicate the experiments |
| Old 7.6 + 7.7 merged | Both were human oversight; one section reads better |
| Old 8.4 shortened | Limitations belong in one full place (7.5) |
| 4.9 negative scenarios shortened to a boxed list | Real value is in showing the safe behaviour, which Chapter 6 tests |
| Ten-item sub-lists in 4.3 and 4.4 condensed | Over-granular; a status table carries the same information |

**Added**
| Addition | Reason |
|---|---|
| 3.1 formal problem definition | Gives A\*, constraints and objective a precise basis |
| 3.7 time-expanded planning | This is the core of what you now actually built |
| RQ → experiment → section table | Shows every question is answered |
| Status tags + matrix | Prevents over-claiming; anticipates the main objection |
| 2.4 explicit positioning vs CBS | Answers "is it really multi-agent?" |
| 5.11 testing and 5.12 lessons | Real evidence of verification |
| 6.14 threats to validity, 6.11 failure cases | Standard for evaluation chapters |
| Appendices B, D, E | Reproducibility, which is your strongest practical asset |

## Things I need from you
1. Your "awesome points" — send them and I'll place each one in the right section.
2. Landing mass: build the land-now / hold / divert comparison, or keep the forced hold and document it?
3. Build the BFS/UCS/Greedy baselines and the experiment script (needed for 6.6 and most of Chapter 6)?
