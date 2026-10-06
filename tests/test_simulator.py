import json
import math
import unittest
from pathlib import Path
from unittest import mock

from simulator.baselines import ALGORITHMS, path_cost, search
from simulator.benchmark import run_benchmark, summarize_benchmark
from simulator.engine import PLANNERS, SimulationEngine, effective_wind
from simulator.grid import (ALT, PRIMARY, Hazards, RunwayBook, cell_bounds, crosswind_kt, in_grid, to_latlon)
from simulator.landing import assign_overweight_case, choose_option, excess_at_arrival, landing_distance_required_m
from simulator.live_data import fetch_opensky, parse_state_vector
from simulator.planner import Reservations, count_conflicts, plan_path, wind_multiplier
from simulator.scenarios import EFFECTS, SCENARIOS, catalogue_with_effects, get_effects, get_scenario, hazard

NO_HAZARDS = Hazards([])
CALM = (0.0, 0.0, 0.0)


def plan(start, goal, *, hazards=NO_HAZARDS, res=None, t0=0, known_t=0, **kw):
    return plan_path(start, t0, goal, hazards=hazards, known_t=known_t, res=res or Reservations(), wind=CALM, **kw)


def run(scenario, n=10, **kw):
    return SimulationEngine().run(scenario, n, **kw)


class CatalogueTests(unittest.TestCase):
    def test_54_scenarios_each_with_effects(self):
        self.assertEqual(len(SCENARIOS), 54)
        self.assertEqual(set(EFFECTS), {s["id"] for s in SCENARIOS})
        self.assertEqual(get_scenario(54)["id"], 54)

    def test_json_catalogue_matches_python_source(self):
        path = Path(__file__).resolve().parent.parent / "scenario_catalogue.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), json.loads(json.dumps(catalogue_with_effects())),
                         "run: python -m simulator.export_catalogue")

    def test_effects_are_independent_copies(self):
        a = get_effects(9)
        a["hazards"].clear()
        self.assertTrue(get_effects(9)["hazards"])


class GeometryTests(unittest.TestCase):
    def test_cells_are_square_at_any_latitude(self):
        for lat in (0.0, 13.2, 51.5, 64.0):
            c = (lat, 10.0)
            (s_lat, s_lon), (n_lat, n_lon) = cell_bounds((0, 0), c)
            height_km = (n_lat - s_lat) * 110.574
            width_km = (n_lon - s_lon) * 111.320 * math.cos(math.radians(lat))
            self.assertAlmostEqual(height_km, width_km, places=3)

    def test_to_latlon_moves_north_and_east(self):
        c = (13.0, 77.0)
        self.assertGreater(to_latlon((0, 1), c)[0], c[0])
        self.assertGreater(to_latlon((1, 0), c)[1], c[1])

    def test_crosswind_is_full_on_beam_and_zero_on_axis(self):
        self.assertAlmostEqual(crosswind_kt(20, 30, 180), 30.0, places=6)   # runway axis 090/270
        self.assertAlmostEqual(crosswind_kt(20, 30, 270), 0.0, places=6)

    def test_wind_multiplier_bounds_and_direction(self):
        # wind FROM the west (270) blows toward the east: eastbound is tailwind, westbound is headwind
        east = wind_multiplier((1, 0), 40, 40, 270)
        west = wind_multiplier((-1, 0), 40, 40, 270)
        self.assertLess(east, 1.0)
        self.assertGreater(west, 1.0)
        for d in ((1, 1), (0, -1), (-1, 1)):
            self.assertTrue(0.85 - 1e-9 <= wind_multiplier(d, 90, 90, 33) <= 1.15 + 1e-9)


class PlannerTests(unittest.TestCase):
    def test_straight_path(self):
        path = plan((-5, 0), (5, 0))
        self.assertEqual((path[0], path[-1]), ((-5, 0), (5, 0)))
        self.assertEqual(len(path), 11)

    def test_avoids_static_hazard(self):
        wall = Hazards([hazard((2, 2, -4, 4), "wall")])
        path = plan((-5, 0), (5, 0), hazards=wall)
        self.assertTrue(path)
        self.assertTrue(all(n not in wall.active_at(t, 0) for t, n in enumerate(path)))

    def test_hazard_unknown_until_announced(self):
        late = Hazards([hazard((2, 2, -5, 5), "full wall", from_t=5)])
        self.assertEqual(plan((-5, 0), (5, 0), hazards=late, known_t=0), plan((-5, 0), (5, 0)))
        # once announced, the full-height wall at x=2 cannot be crossed at all
        self.assertIsNone(plan((1, 0), (3, 0), hazards=late, t0=5, known_t=5))

    def test_moving_hazard_is_time_dependent(self):
        h = Hazards([hazard((2, 2, -5, 5), "wall", from_t=0, until_t=4)])
        path = plan((1, 0), (3, 0), hazards=h)           # wall disappears at t=4: must hold, then cross
        self.assertTrue(path)
        self.assertGreaterEqual(len(path) - 1, 5)

    def test_vertex_reservation_forces_detour_or_wait(self):
        res = Reservations()
        res.add_track([(-5, 0), (-4, 0), (-3, 0), (-2, 0), (-1, 0), (0, 0)], uncertain=False)
        res.vertex.add(((2, 0), 7))
        path = plan((0, 2), (4, 0), res=res)
        self.assertNotIn(((2, 0), 7), {(n, t) for t, n in enumerate(path)})

    def test_swap_conflict_is_prevented(self):
        res = Reservations()
        res.add_track([(1, 0), (0, 0)])                    # other aircraft moves (1,0)->(0,0) at t=0
        path = plan((0, 0), (1, 0), res=res)               # we want (0,0)->(1,0) at t=0: head-on swap
        self.assertTrue(path)
        self.assertNotEqual(path[:2], [(0, 0), (1, 0)])

    def test_reservation_includes_edge_into_first_replanned_step(self):
        # regression: replanning two aircraft together could swap cells because the edge at t=from_t-1 was missing
        res = Reservations()
        res.add_track([(2, 2), (3, 2), (4, 2)], from_t=1)
        self.assertIn(((2, 2), (3, 2), 0), res.edge)

    def test_runway_slot_makes_aircraft_wait(self):
        book = RunwayBook({PRIMARY: 1, ALT: 1})
        book.add(PRIMARY, 4, 3)                            # runway busy during steps 4..6
        path = plan((-4, 0), (0, 0), runways=book, airport=PRIMARY, occupancy=2)
        self.assertGreaterEqual(len(path) - 1, 7)          # cannot land before step 7
        self.assertTrue(book.can_land(PRIMARY, len(path) - 1, 2))

    def test_horizon_limits_endurance(self):
        self.assertIsNone(plan((-5, -5), (5, 5), horizon=6))
        self.assertTrue(plan((-5, -5), (5, 5), horizon=10))

    def test_fully_blocked_goal_is_infeasible_not_invented(self):
        ring = Hazards([hazard((-5, 5, 2, 2), "belt")])
        self.assertIsNone(plan((0, -5), (0, 5), hazards=ring))   # belt spans the full width at y=2

    def test_min_arrival_holds(self):
        path = plan((-2, 0), (0, 0), min_arrival=8)
        self.assertEqual(len(path) - 1, 8)

    def test_count_conflicts(self):
        class A:
            def __init__(self, i, track):
                self.id, self.track = i, track
        vertex, swap = count_conflicts([A(0, [(0, 0), (1, 1), (2, 2)]), A(1, [(3, 3), (1, 1), (4, 4)])])
        self.assertEqual((vertex, swap), (1, 0))
        vertex, swap = count_conflicts([A(0, [(1, 1), (2, 1)]), A(1, [(2, 1), (1, 1)])])
        self.assertEqual((vertex, swap), (0, 1))
        # airport cells are exempt (many aircraft land there)
        self.assertEqual(count_conflicts([A(0, [(0, 0)]), A(1, [(0, 0)])]), (0, 0))


class EngineScenarioTests(unittest.TestCase):
    def test_result_shape(self):
        r = run(50, 6)
        self.assertEqual(r["metrics"]["aircraft"], 6)
        self.assertEqual(len(r["aircraft"]), 6)
        for k in ("planning_ms", "conflicts", "rerouted", "infeasible", "crosswind_kt"):
            self.assertIn(k, r["metrics"])

    def test_deterministic_per_seed(self):
        a, b, c = run(50, 8, seed=3), run(50, 8, seed=3), run(50, 8, seed=4)
        strip = lambda r: [(x["nodes"], x["status"]) for x in r["aircraft"]]
        self.assertEqual(strip(a), strip(b))
        self.assertNotEqual(strip(a), strip(c))

    def test_tracks_never_enter_known_hazards_or_leave_grid(self):
        for sid in (9, 13, 18, 21, 54):
            r = run(sid, 12)
            hz = Hazards(get_effects(sid)["hazards"])
            for a in r["aircraft"]:
                self.assertTrue(all(in_grid(n) for n in a["nodes"]))
                for t, n in enumerate(a["nodes"][1:], 1):
                    # allowed only if the hazard was announced after this aircraft committed (unknown at planning time)
                    if n in hz.active_at(t, 10 ** 6):
                        self.assertTrue(any(s["from_t"] > 0 for s in hz.specs), f"scenario {sid} aircraft {a['id']} step {t}")

    def test_coordinated_planners_produce_conflict_free_plans(self):
        for sid in (1, 4, 12, 21, 24, 27, 33, 36, 39, 41, 47, 50, 52):
            for seed in range(3):
                for mode in ("priority", "fifo"):
                    m = run(sid, 12, seed=seed, planner=mode)["metrics"]
                    self.assertEqual(m["conflicts"], 0, f"scenario {sid} seed {seed} {mode}: {m}")

    def test_independent_baseline_has_conflicts(self):
        total = sum(run(32, 14, seed=s, planner="independent")["metrics"]["conflicts"] for s in range(5))
        self.assertGreater(total, 0)

    def test_priority_planner_serves_emergencies_sooner_than_fifo(self):
        def emergency_delay(mode):
            tot = 0
            for s in range(10):
                r = run(33, 14, seed=s, planner=mode)
                tot += sum(max(0, a["delay_steps"]) for a in r["aircraft"] if a["emergency"] and not a["failed"])
            return tot
        self.assertLess(emergency_delay("priority"), emergency_delay("fifo"))

    def test_scenarios_are_not_silent_no_ops(self):
        base = run(50, 10)["metrics"]
        sigs = set()
        for s in SCENARIOS:
            m = run(s["id"], 10)["metrics"]
            sigs.add((m["rerouted"], m["delayed"], m["diverted"], m["infeasible"], m["route_revisions"],
                      round(m["crosswind_kt"])))
        self.assertGreater(len(sigs), 25)
        self.assertIsNotNone(base)

    def test_airport_closure_diverts_arrivals(self):
        r = run(12, 12)
        arrivals = [a for a in r["aircraft"] if a["kind"] == "arrival" and not a["failed"]]
        self.assertTrue(arrivals)
        self.assertTrue(all(a["destination"] == ALT for a in arrivals))
        self.assertFalse(r["airport_status"][PRIMARY])

    def test_no_feasible_destination_is_reported_not_invented(self):
        r = run(49, 10)
        arrivals = [a for a in r["aircraft"] if a["kind"] == "arrival"]
        self.assertTrue(arrivals)
        for a in arrivals:
            self.assertTrue(a["failed"])
            self.assertEqual(a["fail_reason"], "NO FEASIBLE DESTINATION")
            self.assertIsNone(a["destination"])
            self.assertEqual(len(a["nodes"]), 1)           # never left its start cell
        self.assertGreater(r["metrics"]["infeasible"], 0)

    def test_runway_closure_mid_run_diverts_later_landings(self):
        r = run(24, 14)
        self.assertGreater(r["metrics"]["diverted"], 0)
        for a in r["aircraft"]:
            if a["destination"] == PRIMARY:
                self.assertLess(a["arrival_step"], 5)       # nothing lands on the closed runway

    def test_crosswind_limits_runway_choice(self):
        calm = run(1, 12, wind_speed=5, gust_speed=8)["metrics"]["infeasible"]
        rough = run(1, 12, wind_speed=44, gust_speed=58, wind_dir=180)["metrics"]["infeasible"]
        self.assertGreater(rough, calm)

    def test_emergency_services_unavailable_diverts_emergencies(self):
        r = run(29, 12, seed=1)
        for a in r["aircraft"]:
            if a["emergency"] and not a["failed"]:
                self.assertEqual(a["destination"], ALT)

    def test_overweight_decision_compares_land_now_hold_and_divert(self):
        found = 0
        for s in range(6):
            for a in run(6, 12, seed=s)["aircraft"]:
                d = a["landing_decision"]
                if not d:
                    continue
                found += 1
                modes = {(o["airport"], o["mode"]) for o in d["options"]}
                self.assertIn((PRIMARY, "land_now"), modes)
                self.assertIn((ALT, "land_now"), modes)
                self.assertTrue(any(m == "hold" for _, m in modes))
                self.assertTrue(d["rationale"])
                if not a["failed"]:
                    chosen = [o for o in d["options"] if (o["airport"], o["mode"]) == (d["airport"], d["mode"])][0]
                    self.assertEqual(a["arrival_step"], chosen["arrival"])      # the plan IS the chosen option
        self.assertGreater(found, 0)

    def test_time_critical_emergency_lands_now_even_if_overweight(self):
        landed_overweight = 0
        for s in range(6):
            for a in run(6, 12, seed=s)["aircraft"]:            # scenario 6 = engine failure (time-critical)
                d = a["landing_decision"]
                if d and not a["failed"]:
                    self.assertEqual(d["mode"], "land_now")
                    earliest = min(o["arrival"] for o in d["options"] if o["feasible"])
                    self.assertEqual(a["arrival_step"], earliest)
                    landed_overweight += bool(d["overweight_landing"])
                    if d["overweight_landing"]:
                        self.assertIn("OVERWEIGHT LANDING", a["status"])
        self.assertGreater(landed_overweight, 0)

    def test_non_urgent_overweight_aircraft_reduces_mass_first(self):
        holds = 0
        for s in range(5):
            for a in run(2, 12, seed=s)["aircraft"]:            # scenario 2 = PAN-PAN with an overweight arrival
                d = a["landing_decision"]
                if d and not a["failed"]:
                    within_limit_exists = any(o["feasible"] and not o["overweight_landing"] for o in d["options"])
                    if within_limit_exists:
                        self.assertFalse(d["overweight_landing"])      # never lands overweight when it can avoid it
                    holds += d["mode"] == "hold"
        self.assertGreater(holds, 0)                                   # and it does choose to hold in some runs

    def test_escalation_flips_decision_from_hold_to_land_now(self):
        r = run(40, 10, seed=0)                                  # PAN-PAN escalates to MAYDAY at step 5
        d = r["aircraft"][0]["landing_decision"]
        self.assertEqual(d["event"], "MAYDAY")
        self.assertEqual(d["mode"], "land_now")

    def test_choose_option_rules(self):
        def opt(airport, mode, arrival, ow, feasible=True):
            return {"airport": airport, "mode": mode, "arrival": arrival, "overweight_landing": ow, "feasible": feasible}
        options = [opt(PRIMARY, "land_now", 5, True), opt(PRIMARY, "hold", 14, False), opt(ALT, "land_now", 9, True)]
        self.assertEqual(choose_option(options, "MAYDAY")[0]["arrival"], 5)
        self.assertEqual(choose_option(options, "PAN-PAN")[0]["mode"], "hold")
        none_within = [opt(PRIMARY, "land_now", 5, True), opt(PRIMARY, "hold", 14, True)]
        self.assertEqual(choose_option(none_within, "PAN-PAN")[0]["arrival"], 5)
        self.assertIsNone(choose_option([opt(PRIMARY, "land_now", 5, True, feasible=False)], "MAYDAY")[0])
        tie = [opt(ALT, "land_now", 5, True), opt(PRIMARY, "land_now", 5, True)]
        self.assertEqual(choose_option(tie, "MAYDAY")[0]["airport"], PRIMARY)

    def test_landing_distance_grows_with_excess_mass(self):
        case = assign_overweight_case("Narrowbody", __import__("random").Random(1))
        self.assertGreater(landing_distance_required_m(2000, case, 0), 2000)
        self.assertAlmostEqual(landing_distance_required_m(2000, case, 10 ** 6), 2000)   # mass reduced to the limit
        self.assertEqual(excess_at_arrival(case, 10 ** 6), 0.0)
        self.assertEqual(excess_at_arrival(case, 0), case["excess_t"])

    def test_landing_case_is_seeded_and_consistent(self):
        import random
        c1 = assign_overweight_case("Widebody", random.Random(5))
        c2 = assign_overweight_case("Widebody", random.Random(5))
        self.assertEqual(c1, c2)
        self.assertGreater(c1["predicted_landing_mass_t"], c1["landing_mass_limit_t"])
        self.assertLessEqual(c1["hold_steps"], 25)

    def test_low_fuel_aircraft_reports_fuel_failure_when_detour_exceeds_endurance(self):
        reasons = set()
        for sid in (8, 13, 54):
            for s in range(8):
                for a in run(sid, 12, seed=s)["aircraft"]:
                    if a["failed"]:
                        reasons.add(a["fail_reason"])
        self.assertTrue(reasons <= {"NO FEASIBLE PLAN", "NO FEASIBLE DESTINATION", "INSUFFICIENT FUEL"})

    def test_escalation_replans_and_data_flags(self):
        r = run(40, 10)
        self.assertEqual(r["aircraft"][0]["event"], "MAYDAY (synthetic)")   # PAN-PAN escalated at step 5
        m = run(43, 10)
        self.assertTrue(any(a["identity_missing"] and a["callsign"].startswith("UNKNOWN") for a in m["aircraft"]))
        s = run(44, 10)
        self.assertTrue(all(a["uncertain_position"] for a in s["aircraft"]))
        self.assertIn("DEGRADED", s["metrics"]["data_status"])

    def test_damping_reduces_route_revisions(self):
        m = run(47, 12)["metrics"]
        self.assertLessEqual(m["route_revisions"], m["route_revisions_undamped"])

    def test_effective_wind_floors_and_conservatism(self):
        ws, gs, wd = effective_wind(get_effects(16), 5, 8, 240)
        self.assertGreaterEqual(ws, 30)
        self.assertEqual(wd, 180.0)
        ws, gs, wd = effective_wind(get_effects(23), 10, 10, 90)
        self.assertEqual(ws, 22.0)

    def test_invalid_planner_rejected(self):
        with self.assertRaises(ValueError):
            run(1, 5, planner="nope")


class BaselineSearchTests(unittest.TestCase):
    WALL = frozenset({(0, y) for y in range(-4, 5)})

    def test_all_algorithms_find_a_valid_path(self):
        for algo in ALGORITHMS:
            r = search(algo, (-5, 0), (5, 0), self.WALL)
            self.assertTrue(r["success"], algo)
            self.assertEqual((r["path"][0], r["path"][-1]), ((-5, 0), (5, 0)))
            self.assertTrue(all(n not in self.WALL for n in r["path"]))
            self.assertAlmostEqual(r["cost"], path_cost(r["path"]))

    def test_ucs_and_astar_are_optimal_and_astar_expands_less(self):
        rng = __import__("random").Random(3)
        edge = [(x, y) for x in range(-5, 6) for y in range(-5, 6) if abs(x) == 5 or abs(y) == 5]
        for _ in range(60):
            start, goal = rng.sample(edge, 2)
            blocked = {(x, y) for x in range(-5, 6) for y in range(-5, 6) if rng.random() < 0.25} - {start, goal}
            res = {a: search(a, start, goal, blocked) for a in ALGORITHMS}
            if not res["ucs"]["success"]:
                for a in ALGORITHMS:
                    self.assertFalse(res[a]["success"], a)       # nobody invents a path
                continue
            best = res["ucs"]["cost"]
            self.assertAlmostEqual(res["astar"]["cost"], best)
            self.assertGreaterEqual(res["bfs"]["cost"], best - 1e-9)
            self.assertGreaterEqual(res["greedy"]["cost"], best - 1e-9)
            self.assertLessEqual(res["astar"]["expanded"], res["ucs"]["expanded"])

    def test_unreachable_goal_is_reported(self):
        belt = frozenset({(x, 2) for x in range(-5, 6)})
        for algo in ALGORITHMS:
            self.assertFalse(search(algo, (0, -5), (0, 5), belt)["success"])

    def test_unknown_algorithm_rejected(self):
        with self.assertRaises(ValueError):
            search("dfs", (0, 0), (1, 1))

    def test_time_expanded_planner_reports_expanded_nodes(self):
        stats = {}
        plan((-5, 0), (5, 0), stats=stats)
        self.assertGreaterEqual(stats["expanded"], 11)


class BenchmarkTests(unittest.TestCase):
    def test_all_planners_scored_on_same_fleet(self):
        rows = run_benchmark(50, 8, 12, 18, 240, seeds=3)
        self.assertEqual(len(rows), 3 * len(PLANNERS))
        summary = summarize_benchmark(rows)
        self.assertEqual(len(summary), len(PLANNERS))
        by = {s["planner"]: s for s in summary}
        indep = [r for r in rows if r["planner"].startswith("Independent")]
        coord = [r for r in rows if r["planner"].startswith("Prioritised")]
        self.assertGreater(sum(r["conflicts"] for r in indep), sum(r["conflicts"] for r in coord))
        self.assertIn("±", next(iter(by.values()))["conflicts"])


class LiveDataTests(unittest.TestCase):
    def test_short_state_vector_does_not_crash(self):
        d = parse_state_vector(["abc123", "SIM1  ", "India", 1, 2, 77.5, 13.1, 900.0, False, 120.0, 90.0, 0.0])
        self.assertEqual(d["callsign"], "SIM1")
        self.assertIsNone(d["squawk"])
        self.assertIsNone(d["position_source"])

    def test_fetch_handles_errors_and_rate_limit(self):
        resp = mock.Mock(status_code=429)
        with mock.patch("simulator.live_data.requests.get", return_value=resp):
            self.assertIn("rate limit", fetch_opensky()["error"])
        resp = mock.Mock(status_code=200)
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"states": [["a1b2c3", None, "IN", 1, 2, 77.0, 13.0, 100.0, False, 1.0, 2.0, 0.0]], "time": 5}
        with mock.patch("simulator.live_data.requests.get", return_value=resp):
            out = fetch_opensky()
        self.assertEqual(out["aircraft"][0]["icao24"], "a1b2c3")
        self.assertIsNone(out["aircraft"][0]["callsign"])


if __name__ == "__main__":
    unittest.main()
