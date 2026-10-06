"""Planner comparison over seeded runs.

All three planners face identical fleets (same seed -> same aircraft, starts,
goals and events) and are scored with the same post-hoc conflict check, so the
differences are down to the planning algorithm only.
"""
from .engine import PLANNERS, SimulationEngine
from .metrics import mean_ci

PLANNER_LABEL = {
    "priority": "Prioritised A* (emergencies first)",
    "fifo": "Sequential A* (id order)",
    "independent": "Independent A* (no coordination)",
}
SCORE_COLUMNS = ["feasible", "infeasible", "conflicts", "rerouted", "delayed", "diverted",
                 "total_delay_min", "extra_distance_km", "planning_ms"]


def run_benchmark(scenario_id, aircraft_count, wind_speed, gust_speed, wind_dir, seeds=10, planners=PLANNERS):
    """One row per (planner, seed)."""
    rows = []
    for planner in planners:
        for seed in range(seeds):
            result = SimulationEngine().run(scenario_id, aircraft_count, wind_speed, gust_speed, wind_dir,
                                            seed=seed, planner=planner)
            m = result["metrics"]
            emergency_ok = [a for a in result["aircraft"] if a["emergency"]]
            rows.append({
                "planner": PLANNER_LABEL[planner], "seed": seed, "aircraft": m["aircraft"],
                **{k: round(m[k], 2) if isinstance(m[k], float) else m[k] for k in SCORE_COLUMNS},
                "emergency_delay_min": sum(max(0, a["delay_steps"]) for a in emergency_ok if not a["failed"]),
                "emergencies_unserved": sum(1 for a in emergency_ok if a["failed"]),
            })
    return rows


def summarize_benchmark(rows):
    """Mean +/- 95% half-width per planner for every score column."""
    by_planner = {}
    for row in rows:
        by_planner.setdefault(row["planner"], []).append(row)
    out = []
    for planner, group in by_planner.items():
        entry = {"planner": planner, "runs": len(group)}
        for col in SCORE_COLUMNS + ["emergency_delay_min", "emergencies_unserved"]:
            mu, hw = mean_ci([r[col] for r in group])
            entry[col] = f"{mu:.2f} ± {hw:.2f}"
        out.append(entry)
    return out
