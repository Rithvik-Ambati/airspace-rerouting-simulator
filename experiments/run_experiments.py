"""Regenerates every table and figure used by the report's results chapter.

    python -m experiments.run_experiments            # all experiments (a few minutes)
    python -m experiments.run_experiments --quick    # smaller sample, for a smoke test

Output goes to results/: one CSV per experiment, PNG charts, and summary.md. Everything is
seeded, so re-running gives identical numbers (planning times vary by machine).
"""
import argparse
import random
import time
from pathlib import Path
from statistics import mean

import pandas as pd

from simulator.baselines import ALGORITHMS, search
from simulator.benchmark import PLANNER_LABEL, run_benchmark, summarize_benchmark
from simulator.engine import PLANNERS, SimulationEngine
from simulator.grid import GRID_MAX, GRID_MIN
from simulator.metrics import mean_ci
from simulator.scenarios import hazard

OUT = Path(__file__).resolve().parent.parent / "results"
CELLS = [(x, y) for x in range(GRID_MIN, GRID_MAX + 1) for y in range(GRID_MIN, GRID_MAX + 1)]
EDGE = [c for c in CELLS if c[0] in (GRID_MIN, GRID_MAX) or c[1] in (GRID_MIN, GRID_MAX)]


def _plt():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        return None


def _save(df, name):
    OUT.mkdir(exist_ok=True)
    df.to_csv(OUT / f"{name}.csv", index=False)


def _md(df):
    """Small markdown table without extra dependencies."""
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(lines)


# --- E1: BFS / UCS / Greedy / A* on random obstacle grids ---------------------------------
def e1_algorithms(instances):
    rng = random.Random(1)
    rows = []
    for density in (0.0, 0.1, 0.2, 0.3, 0.4):
        for i in range(instances):
            start, goal = rng.sample(EDGE, 2)
            blocked = {c for c in CELLS if c not in (start, goal) and rng.random() < density}
            results = {a: search(a, start, goal, blocked) for a in ALGORITHMS}
            best = results["ucs"]["cost"]                    # UCS is optimal, so it defines the optimum
            for a, r in results.items():
                rows.append({"density": density, "instance": i, "algorithm": a, "success": r["success"],
                             "cost": r["cost"], "optimum": best, "expanded": r["expanded"], "ms": r["ms"],
                             "optimal": r["success"] and best is not None and abs(r["cost"] - best) < 1e-9,
                             "reachable": best is not None})
    df = pd.DataFrame(rows)
    _save(df, "e1_algorithms_raw")
    reach = df[df["reachable"]]
    summary = reach.groupby(["density", "algorithm"]).agg(
        success_rate=("success", "mean"), optimal_rate=("optimal", "mean"),
        mean_cost=("cost", "mean"), mean_expanded=("expanded", "mean"), mean_ms=("ms", "mean")).round(3).reset_index()
    _save(summary, "e1_algorithms")
    plt = _plt()
    if plt:
        fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
        for a in ALGORITHMS:
            sub = summary[summary["algorithm"] == a]
            ax[0].plot(sub["density"] * 100, sub["mean_expanded"], marker="o", label=a)
            ax[1].plot(sub["density"] * 100, sub["optimal_rate"] * 100, marker="o", label=a)
        ax[0].set(xlabel="obstacle density (%)", ylabel="mean nodes expanded", title="Search effort")
        ax[1].set(xlabel="obstacle density (%)", ylabel="runs returning the optimal cost (%)", title="Route optimality")
        ax[0].legend()
        fig.tight_layout()
        fig.savefig(OUT / "e1_algorithms.png", dpi=150)
        plt.close(fig)
    return summary


# --- E2: planners on identical seeded fleets -----------------------------------------------
def e2_planners(seeds):
    out = []
    for sid, n in ((27, 14), (32, 14), (33, 14), (36, 14), (50, 14)):
        rows = run_benchmark(sid, n, 12, 18, 240, seeds=seeds)
        for r in summarize_benchmark(rows):
            out.append({"scenario": sid, "aircraft": n, **r})
    df = pd.DataFrame(out)
    _save(df, "e2_planners")
    return df[["scenario", "planner", "conflicts", "emergencies_unserved", "emergency_delay_min",
               "total_delay_min", "planning_ms"]]


# --- E3: disruption size sweep ---------------------------------------------------------------
def e3_disruption_size(seeds):
    from simulator import scenarios
    original = dict(scenarios.EFFECTS)
    rows = []
    try:
        for width in range(0, 9):
            # a vertical closed band of increasing height, centred north of the airport
            fx = {"hazards": [hazard((2, 2, -5, -5 + width), "closed band")] if width else []}
            scenarios.EFFECTS[999] = fx
            for seed in range(seeds):
                r = SimulationEngine().run(999, 12, seed=seed)
                m = r["metrics"]
                rows.append({"closed_cells_tall": width, "seed": seed, "infeasible": m["infeasible"],
                             "rerouted": m["rerouted"], "extra_distance_km": m["extra_distance_km"],
                             "total_delay_min": m["total_delay_min"]})
    finally:
        scenarios.EFFECTS.clear()
        scenarios.EFFECTS.update(original)
    df = pd.DataFrame(rows)
    _save(df, "e3_disruption_size_raw")
    summary = df.groupby("closed_cells_tall").mean(numeric_only=True).round(2).drop(columns="seed").reset_index()
    _save(summary, "e3_disruption_size")
    plt = _plt()
    if plt:
        fig, ax = plt.subplots(figsize=(5.5, 3.6))
        ax.plot(summary["closed_cells_tall"], summary["extra_distance_km"], marker="o")
        ax.set(xlabel="height of closed band (cells)", ylabel="mean extra distance (km)",
               title="Rerouting cost vs disruption size")
        fig.tight_layout()
        fig.savefig(OUT / "e3_disruption_size.png", dpi=150)
        plt.close(fig)
    return summary


# --- E4: wind sensitivity ---------------------------------------------------------------------
def e4_wind(seeds):
    rows = []
    for direction in (270, 240, 210, 180):               # 270 = along the runway, 180 = full crosswind
        for speed in range(0, 46, 5):
            for seed in range(seeds):
                m = SimulationEngine().run(1, 12, wind_speed=speed, gust_speed=speed + 8, wind_dir=direction,
                                           seed=seed)["metrics"]
                rows.append({"direction": direction, "wind_kt": speed, "seed": seed, "crosswind_kt": m["crosswind_kt"],
                             "infeasible": m["infeasible"], "diverted": m["diverted"],
                             "total_delay_min": m["total_delay_min"]})
    df = pd.DataFrame(rows)
    summary = df.groupby(["direction", "wind_kt"]).mean(numeric_only=True).round(2).drop(columns="seed").reset_index()
    _save(summary, "e4_wind")
    plt = _plt()
    if plt:
        fig, ax = plt.subplots(figsize=(6, 3.8))
        for d in sorted(summary["direction"].unique()):
            sub = summary[summary["direction"] == d]
            ax.plot(sub["wind_kt"], sub["infeasible"] + sub["diverted"], marker="o", label=f"from {d}°")
        ax.set(xlabel="wind speed (kt, gusts +8)", ylabel="aircraft diverted or not flyable",
               title="Wind and landing feasibility")
        ax.legend()
        fig.tight_layout()
        fig.savefig(OUT / "e4_wind.png", dpi=150)
        plt.close(fig)
    return summary[summary["direction"].isin([270, 180])]


# --- E5: scaling with fleet size ------------------------------------------------------------
def e5_scaling(seeds):
    rows = []
    for n in (4, 8, 12, 16, 20, 24):
        for mode in PLANNERS:
            for seed in range(seeds):
                m = SimulationEngine().run(50, n, seed=seed, planner=mode)["metrics"]
                rows.append({"aircraft": n, "planner": PLANNER_LABEL[mode], "seed": seed,
                             "planning_ms": m["planning_ms"], "conflicts": m["conflicts"],
                             "total_delay_min": m["total_delay_min"]})
    df = pd.DataFrame(rows)
    summary = df.groupby(["aircraft", "planner"]).mean(numeric_only=True).round(2).drop(columns="seed").reset_index()
    _save(summary, "e5_scaling")
    plt = _plt()
    if plt:
        fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
        for p in summary["planner"].unique():
            sub = summary[summary["planner"] == p]
            ax[0].plot(sub["aircraft"], sub["planning_ms"], marker="o", label=p)
            ax[1].plot(sub["aircraft"], sub["conflicts"], marker="o", label=p)
        ax[0].set(xlabel="aircraft", ylabel="planning time (ms)", title="Planning cost")
        ax[1].set(xlabel="aircraft", ylabel="conflicts", title="Conflicts in the final plan")
        ax[0].legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(OUT / "e5_scaling.png", dpi=150)
        plt.close(fig)
    return summary


# --- E6: every scenario, one row each ----------------------------------------------------------
def e6_all_scenarios(seeds):
    rows = []
    from simulator.scenarios import SCENARIOS
    for s in SCENARIOS:
        agg = [SimulationEngine().run(s["id"], 12, seed=seed)["metrics"] for seed in range(seeds)]
        rows.append({"id": s["id"], "scenario": s["title"],
                     **{k: round(mean(m[k] for m in agg), 2) for k in
                        ("rerouted", "delayed", "diverted", "infeasible", "conflicts", "total_delay_min",
                         "extra_distance_km", "route_revisions")}})
    df = pd.DataFrame(rows)
    _save(df, "e6_all_scenarios")
    return df


# --- E7: overweight landing decisions (land now / hold / divert) --------------------------------
def e7_landing_decisions(seeds):
    rows = []
    for sid in (2, 6, 33, 38, 40, 51, 54):
        for seed in range(seeds * 3):
            r = SimulationEngine().run(sid, 12, seed=seed)
            for a in r["aircraft"]:
                d = a["landing_decision"]
                if not d or a["failed"] or not d["mode"]:
                    continue
                feas = [o for o in d["options"] if o["feasible"]]
                holds = [o for o in feas if o["mode"] == "hold" and o["airport"] == "PRIMARY"]
                chosen = next(o for o in d["options"] if (o["airport"], o["mode"]) == (d["airport"], d["mode"]))
                rows.append({"scenario": sid, "seed": seed, "event": d["event"], "profile": a["profile"],
                             "mode": d["mode"], "airport": d["airport"],
                             "overweight_at_touchdown": bool(d["overweight_landing"]),
                             "touchdown_step": chosen["arrival"],
                             "primary_hold_touchdown_step": holds[0]["arrival"] if holds else None})
    df = pd.DataFrame(rows)
    _save(df, "e7_landing_decisions_raw")
    summary = df.groupby("scenario").agg(
        cases=("mode", "size"), land_now=("mode", lambda s: round((s == "land_now").mean(), 2)),
        hold=("mode", lambda s: round((s == "hold").mean(), 2)),
        alternate_airport=("airport", lambda s: round((s == "ALT").mean(), 2)),
        overweight_at_touchdown=("overweight_at_touchdown", lambda s: round(s.mean(), 2)),
        mean_touchdown_step=("touchdown_step", "mean"),
        mean_touchdown_if_held_at_primary=("primary_hold_touchdown_step", "mean")).round(2).reset_index()
    _save(summary, "e7_landing_decisions")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="small samples for a smoke test")
    args = ap.parse_args()
    inst, seeds = (30, 3) if args.quick else (200, 10)
    OUT.mkdir(exist_ok=True)
    t0 = time.time()
    sections = [
        ("E1 — Search algorithms on random obstacle grids (reachable instances only)", e1_algorithms, inst,
         "UCS defines the optimum. BFS and Greedy are scored on how often they return that optimum."),
        ("E2 — Planner comparison on identical seeded fleets (mean ± 95% interval)", e2_planners, seeds,
         "Conflicts, delay and unserved emergencies, all measured by the same post-hoc check."),
        ("E3 — Effect of disruption size", e3_disruption_size, seeds, "Closed band growing from the south edge."),
        ("E4 — Wind sensitivity (selected directions)", e4_wind, seeds,
         "Direction is where the wind blows FROM; 270 is along runway 09/27, 180 is a full crosswind."),
        ("E5 — Scaling with fleet size (scenario 50)", e5_scaling, seeds, "Means over seeds."),
        ("E6 — All 54 scenarios, 12 aircraft", e6_all_scenarios, seeds, "Means over seeds."),
        ("E7 — Overweight landing decisions (land now / hold / divert)", e7_landing_decisions, seeds,
         "Share of overweight emergency arrivals choosing each option. Scenarios 2 and 40 start as PAN-PAN (non-urgent); "
         "scenario 40 escalates to MAYDAY at step 5. Illustrative decision rule, not an operational procedure."),
    ]
    md = ["# Experiment results", "", f"Generated by `python -m experiments.run_experiments` "
          f"({'quick' if args.quick else 'full'} run, {seeds} seeds, {inst} instances per cell).",
          "Synthetic model results only; they describe this simulator, not real-world aviation safety.", ""]
    for title, fn, arg, note in sections:
        print(f"running {title} ...", flush=True)
        df = fn(arg)
        md += [f"## {title}", "", note, "", _md(df), ""]
    (OUT / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print(f"done in {time.time() - t0:.0f}s -> {OUT}")


if __name__ == "__main__":
    main()
