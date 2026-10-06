"""Time-expanded multi-agent planning on the synthetic grid.

Search space is (cell, time). Each step an aircraft may move to any of the 8
neighbours or hold position. Hard constraints, checked while expanding:
  * closed sectors at the step being entered (hazards known to the planner),
  * vertex conflicts - two aircraft in one cell at one step,
  * swap conflicts   - two aircraft exchanging cells between two steps,
  * runway capacity  - a landing needs a free runway slot for its occupancy,
  * fuel/horizon     - arrival no later than the aircraft's endurance.
Soft cost: distance, with a wind-dependent head/tailwind multiplier.

Three planning modes are provided so they can be compared honestly:
  independent - each aircraft planned alone (no reservations, no runway slots)
  fifo        - sequential planning in id order against a reservation table
  priority    - sequential planning, emergencies first (then low fuel)
"""
import heapq
import math

from .grid import (AIRPORT_CELLS, HORIZON, in_grid, octile)

MOVES = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
MIN_COST_MULT = 0.85            # tailwind can discount a move by at most 15%
MAX_WIND_EFFECT = 0.15
EMERGENCY_RANK = {"MAYDAY": 0, "7500": 0, "7700": 0, "MEDICAL": 0, "FUEL": 0, "TECH": 0, "PAN-PAN": 1, "7600": 1}


class Reservations:
    """Space-time cells and edges already claimed by planned aircraft."""

    def __init__(self):
        self.vertex = set()
        self.edge = set()

    def add_track(self, track, from_t=0, uncertain=False):
        # Edges starting one step before from_t are included: the move into step from_t
        # must also be reserved, or two aircraft replanned together could swap cells.
        for t in range(max(0, from_t - 1), len(track)):
            node = track[t]
            if t < from_t:
                if t + 1 < len(track) and track[t + 1] != node:
                    self.edge.add((node, track[t + 1], t))
                continue
            if node not in AIRPORT_CELLS:
                self.vertex.add((node, t))
                if uncertain:
                    # Stale/uncertain position: also keep others out of the 4 adjacent cells.
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        self.vertex.add(((node[0] + dx, node[1] + dy), t))
            if t + 1 < len(track) and track[t + 1] != node:
                self.edge.add((node, track[t + 1], t))


def wind_multiplier(move, wind_kt, gust_kt, wind_dir_deg):
    """Cost multiplier (0.85..1.15) for a move: headwind costs more, tailwind less."""
    dx, dy = move
    if (dx, dy) == (0, 0) or wind_kt <= 0:
        return 1.0
    norm = math.hypot(dx, dy)
    toward = math.radians((wind_dir_deg + 180) % 360)       # wind blows TOWARD this bearing
    wx, wy = math.sin(toward), math.cos(toward)             # x east, y north
    along = (dx * wx + dy * wy) / norm                      # +1 = tailwind
    strength = min(1.0, ((wind_kt + gust_kt) / 2) / 40.0)
    return 1.0 - MAX_WIND_EFFECT * along * strength


def plan_path(start, t0, goal, *, hazards, known_t, res, wind, horizon=HORIZON,
              runways=None, airport=None, occupancy=0, min_arrival=0, use_reservations=True, stats=None):
    """Time-expanded A*. Returns the node sequence for steps t0..t_arrive, or None.

    `wind` = (wind_kt, gust_kt, dir_deg). If `stats` is a dict, it receives the number of
    (cell, time) states expanded under key "expanded". With `runways`/`airport` set the goal is
    only accepted at a step where a runway slot is free (the aircraft may hold
    until one opens, within the horizon).
    """
    counter = 0
    heap = [(octile(start, goal) * MIN_COST_MULT, counter, 0.0, start, t0)]
    came = {(start, t0): None}
    best_g = {(start, t0): 0.0}
    closed = set()
    while heap:
        _, _, g, node, t = heapq.heappop(heap)
        if (node, t) in closed:
            continue
        closed.add((node, t))
        if stats is not None:
            stats["expanded"] = stats.get("expanded", 0) + 1
        if node == goal and t >= min_arrival and (
                runways is None or runways.can_land(airport, t, occupancy)):
            path = []
            state = (node, t)
            while state is not None:
                path.append(state[0])
                state = came[state]
            return path[::-1]
        if t >= horizon:
            continue
        blocked_next = hazards.active_at(t + 1, known_t)
        for dx, dy in MOVES:
            nxt = (node[0] + dx, node[1] + dy)
            if not in_grid(nxt) or nxt in blocked_next:
                continue
            if use_reservations:
                if nxt not in AIRPORT_CELLS and (nxt, t + 1) in res.vertex:
                    continue
                if nxt != node and (nxt, node, t) in res.edge:       # head-on swap
                    continue
            if (dx, dy) == (0, 0):
                step_cost = 1.0
            else:
                step_cost = (math.sqrt(2) if dx and dy else 1.0) * wind_multiplier((dx, dy), *wind)
            ng = g + step_cost
            key = (nxt, t + 1)
            if ng < best_g.get(key, float("inf")):
                best_g[key] = ng
                came[key] = (node, t)
                counter += 1
                heapq.heappush(heap, (ng + octile(nxt, goal) * MIN_COST_MULT, counter, ng, nxt, t + 1))
    return None


def priority_key(agent, mode):
    if mode == "priority":
        rank = EMERGENCY_RANK.get(agent.event, 2)
        return (rank, agent.fuel, agent.id)
    return (agent.id,)


def count_conflicts(agents):
    """Vertex and swap conflicts between final tracks (airport cells exempt)."""
    occupancy = {}
    vertex = swap = 0
    for a in agents:
        for t, node in enumerate(a.track):
            if node in AIRPORT_CELLS:
                continue
            if (node, t) in occupancy and occupancy[(node, t)] != a.id:
                vertex += 1
            occupancy[(node, t)] = a.id
    moves = {}
    for a in agents:
        for t in range(len(a.track) - 1):
            if a.track[t] != a.track[t + 1]:
                moves[(a.track[t], a.track[t + 1], t)] = a.id
    for (p, q, t), aid in moves.items():
        other = moves.get((q, p, t))
        if other is not None and other != aid and aid < other:
            swap += 1
    return vertex, swap
