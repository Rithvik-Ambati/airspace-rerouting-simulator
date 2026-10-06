"""Scenario-driven multi-agent re-routing engine. Research simulation only.

The engine contains no scenario-id logic: scenario behaviour (hazards,
emergencies, runway state, data quality) is read from simulator.scenarios.
Planning is time-expanded A* (see planner.py). Mid-run events (a restriction
announced at step t, an emergency declared/escalated/cleared, a runway closing)
trigger a replanning round from every aircraft's current position.
"""
import math
import random
import time
from dataclasses import dataclass, field

from .grid import (ALT, AIRPORT_NODES, CELL_KM, DEFAULT_FUEL_STEPS, GRID_MAX, GRID_MIN, HORIZON, PRIMARY,
                   PROFILE_LIMITS, PROFILES, STEP_MINUTES, Hazards, RunwayBook, cell_bounds, crosswind_kt,
                   to_latlon)
from .landing import assign_overweight_case
from .planner import (Reservations, count_conflicts, plan_path, priority_key)
from .scenarios import get_effects, get_scenario

CENTER = (13.1986, 77.7066)   # Bengaluru, default reference point
PLANNERS = ("priority", "fifo", "independent")
EDGE_CELLS = [(x, y) for x in range(GRID_MIN, GRID_MAX + 1) for y in range(GRID_MIN, GRID_MAX + 1)
              if x in (GRID_MIN, GRID_MAX) or y in (GRID_MIN, GRID_MAX)]
SERVICES_REQUIRED = {"MAYDAY", "MEDICAL", "TECH", "7500", "7700", "FUEL", "PAN-PAN", "7600"}
EVENT_LABEL = {"MAYDAY": "MAYDAY (synthetic)", "PAN-PAN": "PAN-PAN (synthetic)", "7700": "7700 (synthetic)",
               "7500": "7500 (synthetic)", "7600": "7600 (synthetic)", "MEDICAL": "MEDICAL (synthetic)",
               "FUEL": "LOW FUEL (synthetic)", "TECH": "TECHNICAL (synthetic)"}


@dataclass
class Agent:
    id: int
    callsign: str
    profile: str
    kind: str                       # "arrival" or "overflight"
    start: tuple
    goal: tuple                     # overflight exit cell (arrivals use airports)
    event: str = None
    fuel: int = DEFAULT_FUEL_STEPS
    uncertain: bool = False
    identity_missing: bool = False
    hold_steps: int = 0
    landing_case: dict = None
    force_replan: bool = False
    track: list = field(default_factory=list)       # node at each absolute step, from step 0
    airport: str = None             # airport actually planned for (arrivals)
    land_t: int = None
    occupancy: int = 0
    failed: bool = False
    fail_reason: str = None
    revisions: int = 0              # times its future route was replaced during replanning
    original_track: list = field(default_factory=list)
    original_airport: str = None


def effective_wind(fx, wind_speed, gust_speed, wind_dir):
    ws, gs, wd = float(wind_speed), float(gust_speed), float(wind_dir)
    if fx["wind_floor"] and ws < fx["wind_floor"][0]:
        ws, wd = float(fx["wind_floor"][0]), float(fx["wind_floor"][1])
    if fx["gust_floor"]:
        gs = max(gs, float(fx["gust_floor"]))
    ws, gs = ws + fx["conservative_wind"], gs + fx["conservative_wind"]
    return ws, max(gs, ws), wd


def _opposite_edge(start, rng):
    x, y = start
    if x == GRID_MIN:
        return (GRID_MAX, rng.randint(GRID_MIN, GRID_MAX))
    if x == GRID_MAX:
        return (GRID_MIN, rng.randint(GRID_MIN, GRID_MAX))
    if y == GRID_MIN:
        return (rng.randint(GRID_MIN, GRID_MAX), GRID_MAX)
    return (rng.randint(GRID_MIN, GRID_MAX), GRID_MIN)


def build_fleet(fx, n, rng):
    emergencies = fx["emergencies"][:n]
    referenced = {ev[key]["agent"] for ev in fx["timeline"] for key in ("declare", "escalate", "clear")
                  if key in ev and ev[key]["agent"] < n}
    # Timeline events name specific aircraft, so those scenarios keep emergencies at ids 0..k-1.
    # Otherwise emergency aircraft are spread randomly through the fleet (id order != priority order).
    if referenced:
        emergency_idx = list(range(len(emergencies)))
    else:
        emergency_idx = rng.sample(range(n), len(emergencies))
    event_of = dict(zip(emergency_idx, emergencies))
    # aircraft that are (or later become) emergencies must be arrivals
    forced = set(emergency_idx) | referenced
    arrival_share = min(0.9, 0.5 + 0.08 * fx["extra_traffic"])
    starts = rng.sample(EDGE_CELLS, n)
    profiles = [rng.choice(PROFILES) for _ in range(n)]
    if fx["mixed_fleet"]:
        profiles = [PROFILES[i % len(PROFILES)] for i in range(n)]
        rng.shuffle(profiles)
    stale_pool = rng.sample(range(n), min(n, round(n * fx["stale_fraction"])))
    missing_pool = set(rng.sample(range(n), min(n, round(n * fx["missing_id_fraction"]))))
    low_fuel_left = fx["low_fuel"]
    overweight_left = fx["overweight"]
    agents = []
    for i in range(n):
        kind = "arrival" if (i in forced or rng.random() < arrival_share) else "overflight"
        start = starts[i]
        goal = AIRPORT_NODES[PRIMARY] if kind == "arrival" else _opposite_edge(start, rng)
        a = Agent(id=i, callsign=f"SIM{100 + i}", profile=profiles[i], kind=kind, start=start, goal=goal,
                  event=event_of.get(i))
        a.uncertain = fx["uncertain_all"] or i in stale_pool or i in missing_pool
        if i in missing_pool:
            a.identity_missing = True
            a.callsign = f"UNKNOWN-{i}"
        if a.event and low_fuel_left > 0:
            low_fuel_left -= 1
            a.fuel = max(octile_steps(start, goal) + 2, 6)
        if a.event and a.kind == "arrival" and overweight_left > 0:
            overweight_left -= 1
            a.landing_case = assign_overweight_case(a.profile, rng)
            a.hold_steps = a.landing_case["hold_steps"]
        agents.append(a)
    return agents


def octile_steps(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class _Round:
    """One planning run over a fixed set of agents; owns the replanning loop."""

    def __init__(self, fx, agents, wind, mode, damping):
        self.fx, self.agents, self.wind, self.mode, self.damping = fx, agents, wind, mode, damping
        self.hazards = Hazards(fx["hazards"])
        self.caps = {PRIMARY: fx["runways"] if fx["primary_open"] else 0,
                     ALT: fx["alt_runways"] if fx["alt_open"] else 0}
        self.change = fx["runways_after"]
        self.te = 0
        self.xwind = crosswind_kt(wind[0], wind[1], wind[2])

    # ---- destination logic -------------------------------------------------
    def eligible(self, a, airport):
        """Can this aircraft land here, given what is known at the current step?"""
        fx = self.fx
        cap = self.caps[airport]
        if airport == PRIMARY and self.change and self.te >= self.change[0]:
            cap = self.change[1]
        if cap <= 0:
            return False
        length = fx["runway_length_m"] if airport == PRIMARY else fx["alt_runway_length_m"]
        lim = PROFILE_LIMITS[a.profile]
        if length < lim["runway_m"] or self.xwind > lim["xwind_kt"]:
            return False
        if airport == PRIMARY and a.event in SERVICES_REQUIRED and not fx["primary_services"]:
            return False
        return True

    def occupancy_for(self, a, airport):
        extra = self.fx["occupancy_extra"] if airport == PRIMARY else self.fx["alt_occupancy_extra"]
        return PROFILE_LIMITS[a.profile]["occupancy"] + extra

    def options(self, a):
        return [ap for ap in (PRIMARY, ALT) if self.eligible(a, ap)]

    # ---- one aircraft ------------------------------------------------------
    def _plan_agent(self, a, te, res, book, known_change):
        pos = a.track[te]
        horizon = min(HORIZON, a.fuel)
        targets = [(None, a.goal)] if a.kind == "overflight" else [
            (ap, AIRPORT_NODES[ap]) for ap in self.options(a)]
        if not targets:
            return None, "NO FEASIBLE DESTINATION"
        coordinated = self.mode != "independent"
        for relax_fuel in (False, True):
            for airport, goal in targets:
                occ = self.occupancy_for(a, airport) if airport else 0
                path = plan_path(
                    pos, te, goal, hazards=self.hazards, known_t=te, res=res, wind=self.wind,
                    horizon=HORIZON if relax_fuel else horizon,
                    runways=book if (airport and coordinated) else None, airport=airport,
                    occupancy=occ, min_arrival=a.hold_steps, use_reservations=coordinated)
                if path:
                    return (airport, path, occ), ("INSUFFICIENT FUEL" if relax_fuel else None)
        return None, "NO FEASIBLE PLAN"

    def _future_valid(self, a, te, res, book):
        """Is the aircraft's current future still legal under what is known at step te?"""
        coordinated = self.mode != "independent"
        for t in range(te, len(a.track) - 1):
            nxt = a.track[t + 1]
            if nxt in self.hazards.active_at(t + 1, te):
                return False
            if coordinated:
                # airport cells may hold several aircraft, but head-on swaps are never allowed
                if (nxt not in AIRPORT_CELLS_SET and (nxt, t + 1) in res.vertex) or (nxt, a.track[t], t) in res.edge:
                    return False
        if a.airport and coordinated and a.land_t is not None and a.land_t >= te:
            if not self.eligible(a, a.airport) or not book.can_land(a.airport, a.land_t, a.occupancy):
                return False
        return len(a.track) - 1 <= min(HORIZON, a.fuel)

    # ---- a full round (initial plan, or rip-up replan at step te) -----------
    def round(self, te):
        self.te = te
        coordinated = self.mode != "independent"
        known_change = self.change if (self.change and te >= self.change[0]) else None
        book = RunwayBook(self.caps, known_change)
        res = Reservations()
        flying = []
        for a in self.agents:
            if a.failed:
                continue
            # An aircraft is finished once its last step is behind us. A landing scheduled for exactly
            # step te is NOT finished: the runway state announced at te (e.g. a closure) applies to it.
            last = len(a.track) - 1
            if te > 0 and (last < te or (last == te and not a.airport)):
                if a.airport and a.land_t is not None:
                    book.add(a.airport, a.land_t, a.occupancy)
                continue
            if coordinated:
                res.add_track(a.track[:te + 1], uncertain=a.uncertain)
            if a.airport and a.land_t is not None and a.land_t < te:
                book.add(a.airport, a.land_t, a.occupancy)
            flying.append(a)
        flying.sort(key=lambda a: priority_key(a, self.mode))
        for a in flying:
            if te > 0 and self.damping and not a.force_replan and a.track and self._future_valid(a, te, res, book):
                if coordinated:
                    res.add_track(a.track, from_t=te + 1, uncertain=a.uncertain)
                    if a.airport and a.land_t is not None and a.land_t >= te:
                        book.add(a.airport, a.land_t, a.occupancy)
                continue
            outcome, reason = self._plan_agent(a, te, res, book, known_change)
            a.force_replan = False
            if outcome is None:
                a.failed, a.fail_reason = True, reason
                a.track = a.track[:te + 1]
                a.airport = a.land_t = None
                continue
            airport, path, occ = outcome
            old_future = a.track[te:]
            if te > 0 and old_future != path:
                a.revisions += 1
            if reason:                  # reachable only by exceeding endurance -> not flyable
                a.failed, a.fail_reason = True, reason
                a.track = a.track[:te + 1]
                a.airport = a.land_t = None
                continue
            a.track = a.track[:te] + path
            a.airport, a.occupancy = airport, occ
            a.land_t = (len(a.track) - 1) if airport else None
            if coordinated:
                res.add_track(a.track, from_t=te + 1, uncertain=a.uncertain)
                if airport:
                    book.add(airport, a.land_t, occ)
        return book

    def event_times(self):
        times = set(self.hazards.change_times())
        for ev in self.fx["timeline"]:
            times.add(ev["t"])
        if self.change:
            times.add(self.change[0])
        return sorted(t for t in times if 0 < t <= HORIZON)

    def apply_timeline(self, te):
        for ev in self.fx["timeline"]:
            if ev["t"] != te:
                continue
            for key in ("declare", "escalate"):
                if key in ev and ev[key]["agent"] < len(self.agents):
                    a = self.agents[ev[key]["agent"]]
                    a.event, a.force_replan = ev[key]["type"], True
            if "clear" in ev and ev["clear"]["agent"] < len(self.agents):
                self.agents[ev["clear"]["agent"]].event = None

    def run(self):
        for a in self.agents:
            a.track = [a.start]
        book = self.round(0)
        for te in self.event_times():
            self.apply_timeline(te)
            book = self.round(te)
        return book


AIRPORT_CELLS_SET = set(AIRPORT_NODES.values())


def _path_km(track):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) * CELL_KM for a, b in zip(track, track[1:]) if a != b)


def _dedup(track):
    out = []
    for n in track:
        if not out or out[-1] != n:
            out.append(n)
    return out


class SimulationEngine:
    def __init__(self):
        self.last_result = None

    def run(self, scenario_id=50, aircraft_count=8, wind_speed=12, gust_speed=18, wind_dir=240, seed=7,
            center=None, planner="priority", damping=True, _demo=True):
        if planner not in PLANNERS:
            raise ValueError(f"planner must be one of {PLANNERS}")
        started = time.perf_counter()
        center = tuple(center or CENTER)
        scenario_id = int(scenario_id)
        scenario = get_scenario(scenario_id)
        fx = get_effects(scenario_id)
        wind = effective_wind(fx, wind_speed, gust_speed, wind_dir)
        rng = random.Random(f"{seed}-{scenario_id}-{aircraft_count}")
        agents = build_fleet(fx, aircraft_count, rng)

        # Baseline ("original") plans: each aircraft alone, no disruptions, primary airport.
        empty = Hazards([])
        for a in agents:
            goal = AIRPORT_NODES[PRIMARY] if a.kind == "arrival" else a.goal
            a.original_airport = PRIMARY if a.kind == "arrival" else None
            a.original_track = plan_path(a.start, 0, goal, hazards=empty, known_t=0, res=Reservations(),
                                         wind=wind, use_reservations=False) or [a.start]

        run = _Round(fx, agents, wind, planner, damping)
        book = run.run()

        # post-hoc measurements on the FINAL tracks (same definitions for every planner)
        vertex, swap = count_conflicts(agents)
        final_book = RunwayBook(run.caps, run.change)
        for a in agents:
            if a.airport and a.land_t is not None and not a.failed:
                final_book.add(a.airport, a.land_t, a.occupancy)
        runway_overload = final_book.overload()

        out_aircraft = [self._summarise(a, center, run) for a in agents]
        horizon_used = max([len(a.track) for a in agents] + [1])
        frames = {t: [{"label": label, "bounds": [cell_bounds(c, center) for c in sorted(cells)]}
                      for label, cells in run.hazards.snapshot(t)] for t in range(0, horizon_used + 1)}
        flown = [a for a in out_aircraft if not a["failed"]]
        elapsed = (time.perf_counter() - started) * 1000
        metrics = {
            "aircraft": aircraft_count,
            "rerouted": sum(a["route_changed"] for a in out_aircraft),
            "delayed": sum(a["delay_steps"] > 0 and not a["failed"] for a in out_aircraft),
            "diverted": sum(a["diverted"] for a in out_aircraft),
            "feasible": len(flown),
            "infeasible": len(out_aircraft) - len(flown),
            "landings": sum(1 for a in flown if a["destination"] in (PRIMARY, ALT)),
            "conflicts": vertex + swap + runway_overload,
            "vertex_conflicts": vertex, "swap_conflicts": swap, "runway_overload_steps": runway_overload,
            "total_delay_min": sum(max(0, a["delay_steps"]) for a in flown) * STEP_MINUTES,
            "extra_distance_km": round(sum(a["distance_km"] - a["original_distance_km"] for a in flown), 1),
            "route_revisions": sum(a["revisions"] for a in out_aircraft),
            "planning_ms": elapsed,
            "wind_speed": wind[0], "gust_speed": wind[1], "wind_direction": wind[2],
            "crosswind_kt": round(run.xwind, 1),
            "planner": planner, "damping": damping,
            "data_status": fx["data_status"],
        }
        if fx["damping_demo"] and _demo and damping:
            undamped = SimulationEngine().run(scenario_id, aircraft_count, wind_speed, gust_speed, wind_dir,
                                              seed, center, planner, damping=False, _demo=False)
            metrics["route_revisions_undamped"] = undamped["metrics"]["route_revisions"]
        result = {"scenario_id": scenario_id, "scenario": scenario, "effects": fx, "aircraft": out_aircraft,
                  "center": center, "metrics": metrics, "hazard_frames": frames,
                  "airports": {k: to_latlon(v, center) for k, v in AIRPORT_NODES.items()},
                  "airport_status": {PRIMARY: run.caps[PRIMARY] > 0, ALT: run.caps[ALT] > 0},
                  "max_step": horizon_used}
        self.last_result = result
        return result

    @staticmethod
    def _summarise(a, center, run):
        track = a.track
        orig = a.original_track
        distance, orig_distance = _path_km(track), _path_km(orig)
        arrival = len(track) - 1
        orig_arrival = len(orig) - 1
        route_changed = (not a.failed) and _dedup(track) != _dedup(orig)
        diverted = (not a.failed) and a.kind == "arrival" and a.airport != a.original_airport
        delay = arrival - orig_arrival
        waits = sum(1 for i in range(len(track) - 1) if track[i] == track[i + 1])
        if a.failed:
            status = a.fail_reason or "NO FEASIBLE PLAN"
        elif diverted:
            status = "DIVERTED to alternate"
        elif route_changed:
            status = "REROUTED"
        elif delay > 0:
            status = "DELAYED (holding)"
        else:
            status = "UNCHANGED"
        if a.event:
            status = "EMERGENCY · " + status
        return {
            "id": a.id, "callsign": a.callsign, "profile": a.profile, "kind": a.kind,
            "emergency": a.event is not None, "event": EVENT_LABEL.get(a.event, "Normal"),
            "status": status, "failed": a.failed, "fail_reason": a.fail_reason,
            "nodes": track, "original_nodes": orig,
            "route": [to_latlon(n, center) for n in track],
            "original_route": [to_latlon(n, center) for n in orig],
            "route_changed": route_changed, "diverted": diverted,
            "distance_km": distance, "original_distance_km": orig_distance,
            "arrival_step": arrival, "original_arrival_step": orig_arrival, "delay_steps": delay,
            "wait_steps": waits, "destination": (a.airport or "EXIT") if not a.failed else None,
            "fuel_steps": a.fuel, "uncertain_position": a.uncertain, "identity_missing": a.identity_missing,
            "hold_steps": a.hold_steps, "landing_case": a.landing_case, "revisions": a.revisions,
            "cost": distance,
        }
