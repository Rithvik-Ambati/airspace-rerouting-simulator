# AeroRescue — Dynamic Flight Re-Routing Under Airspace Disruptions

A research prototype that simulates multi-agent aircraft routing when the airspace changes: closed or moving sectors, emergencies, runway closures, weather limits and degraded data. Live data (OpenSky positions, Open-Meteo weather, OurAirports) is shown beside the simulation as context only.

> **Safety notice:** This is a research/educational simulation, not an operational air traffic control system. Never use it to direct real aircraft. All emergencies, route plans, restricted areas and runway outcomes are synthetic. The OpenSky connector is a read-only snapshot, not an authoritative flight plan or emergency feed.

## What it does

- **Scenario-driven.** Each of the 54 scenarios carries machine-readable *effects* (hazards, emergencies, timed events, runway state, data quality) in `simulator/scenarios.py`. The engine has no scenario-id lists; adding behaviour means editing that table. `scenario_catalogue.json` is generated from it (`python -m simulator.export_catalogue`) and a test keeps them in sync.
- **Real multi-agent planning.** Time-expanded A\* over (cell, minute): 8 moves plus *hold*, closed sectors that can move or appear later, same-cell and head-on-swap conflicts, runway-slot capacity, fuel endurance and a wind-dependent head/tailwind cost.
- **Priority.** The `priority` planner plans emergencies first (then by remaining endurance). `fifo` plans in id order. `independent` ignores other aircraft (a baseline that shows what coordination buys).
- **Dynamic replanning.** When something changes mid-run (a restriction announced at step *t*, an emergency declared/escalated/cleared, a runway closing) every aircraft is replanned from its current position. Plans that are still legal are kept (damping), so routes do not flap; scenario 47 reports revisions with and without damping.
- **Landing logic.** Aircraft land at a primary or alternate airport. Eligibility depends on airport/runway open, runway length vs type, crosswind vs type limit (from wind and gusts on runway 09/27) and emergency services. Failing that an aircraft is diverted; if nothing works it is reported as **not flyable** with a reason (`NO FEASIBLE DESTINATION`, `NO FEASIBLE PLAN`, `INSUFFICIENT FUEL`) and is never given an invented route.
- **Overweight landing.** Scenario-assigned, seeded cases turn the required fuel burn-off/jettison into a minimum landing time; the aircraft holds and other traffic is planned around it. Mass limits and rates are class-level illustrations.
- **Data resilience.** Stale/uncertain positions get a widened safety footprint, missing callsigns stay `UNKNOWN-n`, and weather loss uses a conservative wind.
- **Honest evaluation.** The Evaluation tab runs all three planners on identical seeded fleets and reports mean ± 95% interval per planner (conflicts, unserved emergencies, delay, extra distance, planning time).
- **Search baselines.** `simulator/baselines.py` implements BFS, uniform-cost search, greedy best-first and A\* on the same grid and costs, reporting path cost, nodes expanded, run time and success.
- **Reproducible experiments.** `python -m experiments.run_experiments` regenerates every table and chart (algorithm comparison, planner comparison, disruption-size and wind sweeps, fleet-size scaling, all 54 scenarios) into `results/`.
- Streamlit dashboard with a time slider that shows hazards and aircraft positions step by step, CLI, and 46 unit tests.

## Quick start (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

Run the tests: `python -m unittest discover -s tests -v`

Run one scenario from the CLI:

```powershell
python -m simulator.cli --scenario 50 --aircraft 8 --planner priority --seed 7
```

## Model conventions

- Grid: 11 × 11 cells, 8 km each (≈ 88 km square), centred on the chosen airport. Cells are square at any latitude. Primary airport at the centre, alternate airport 4 cells east and 3 south.
- One planning step = 1 minute = one cell move. Speed differences between aircraft types are **not** modelled; types differ in runway length, crosswind limit and runway occupancy.
- Separation is cell exclusivity (no two aircraft in a cell at a step, no head-on swaps); airport cells may hold several aircraft, limited by runway slots.
- Runs are deterministic for a given scenario, aircraft count, seed and planner.

## Project structure

```text
app.py                      thin Streamlit entry point
dashboard/                  UI modules (sidebar, map, overview, live data, static tabs, style)
simulator/
  scenarios.py              54 scenarios + executable effects (single source of truth)
  grid.py                   grid, hazards over time, runway book, crosswind, geometry
  planner.py                time-expanded A*, reservations, conflict counting
  engine.py                 fleet generation, destination logic, replanning loop
  landing.py                illustrative overweight-landing model
  baselines.py              BFS / UCS / Greedy / A* single-aircraft baselines
  benchmark.py / metrics.py planner comparison and statistics
  live_data.py / airport_context.py   OpenSky, ADSBdb, Open-Meteo, OurAirports
  cli.py / export_catalogue.py
experiments/run_experiments.py   regenerates results/ (CSVs, charts, summary.md)
results/                    generated experiment outputs
tests/test_simulator.py
```

## Limitations

1. The airspace is a synthetic grid, not real airspace geometry; there is no altitude layer.
2. All aircraft move at one cell per minute regardless of type; no certified performance data, separation minima or runway occupancy models.
3. Prioritised planning is greedy sequential planning with reservations. It is not optimal and does not implement CBS or other complete MAPF solvers.
4. Crosswind is evaluated once per run from the configured wind; there is no time-varying weather beyond sector hazards.
5. The alternate airport is a second synthetic airport; real diversion choice, fuel reserves and approach procedures are not modelled.
6. OpenSky anonymous access is rate-limited and often needs authentication; live fetches can fail and the simulation still runs.
7. Obtain aviation-domain review before any higher-stakes use.

## Live data

The optional OpenSky connector calls the documented state-vector endpoint with a bounding box and tolerates short state vectors and HTTP 401/403/429. No API key is embedded in this repository. Do not commit credentials.
