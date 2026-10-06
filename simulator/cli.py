import argparse
import json

from .engine import PLANNERS, SimulationEngine


def main():
    p = argparse.ArgumentParser(description="Run one synthetic airspace re-routing scenario.")
    p.add_argument("--scenario", type=int, default=50)
    p.add_argument("--aircraft", type=int, default=8)
    p.add_argument("--wind", type=int, default=12)
    p.add_argument("--gusts", type=int, default=18)
    p.add_argument("--wind-direction", type=int, default=240)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--planner", choices=PLANNERS, default="priority")
    args = p.parse_args()
    r = SimulationEngine().run(args.scenario, args.aircraft, args.wind, args.gusts, args.wind_direction,
                               seed=args.seed, planner=args.planner)
    skip = ("route", "nodes", "original_route", "original_nodes")
    print(json.dumps({"scenario": r["scenario"]["title"], "metrics": r["metrics"],
                      "aircraft": [{k: v for k, v in a.items() if k not in skip} for a in r["aircraft"]]},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
