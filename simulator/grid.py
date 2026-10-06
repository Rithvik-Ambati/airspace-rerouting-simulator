"""Synthetic airspace grid, time-varying hazards and the airport/runway model.

Conventions
-----------
* Nodes are (x, y) cells, x east / y north, each axis -5..5.
* One planning step = one minute and one cell move (orthogonal or diagonal).
  A cell is CELL_KM wide, so the grid spans ~88 km. Speed differences between
  aircraft types are deliberately NOT modelled (every aircraft moves one cell
  per step); types differ in runway length, crosswind limit and runway time.
* The primary airport sits at the origin, the alternate at ALT_NODE.
"""
import math

GRID_MIN, GRID_MAX = -5, 5
CELL_KM = 8.0
STEP_MINUTES = 1.0
HORIZON = 60                      # planning horizon in steps
DEFAULT_FUEL_STEPS = 55           # endurance of a normal aircraft, in steps

PRIMARY = "PRIMARY"
ALT = "ALT"
AIRPORT_NODES = {PRIMARY: (0, 0), ALT: (4, -3)}
AIRPORT_CELLS = set(AIRPORT_NODES.values())
RUNWAY_AXIS_DEG = 90              # runway 09/27 (axis east-west)

# Representative, illustrative per-profile values (not certified performance data).
PROFILE_LIMITS = {
    #                 min runway (m), crosswind limit (kt), runway occupancy (steps)
    "Regional jet": {"runway_m": 1500, "xwind_kt": 30, "occupancy": 2},
    "Turboprop":    {"runway_m": 1100, "xwind_kt": 25, "occupancy": 2},
    "Narrowbody":   {"runway_m": 2000, "xwind_kt": 33, "occupancy": 2},
    "Widebody":     {"runway_m": 2800, "xwind_kt": 38, "occupancy": 3},
}
PROFILES = list(PROFILE_LIMITS)


def in_grid(node):
    return GRID_MIN <= node[0] <= GRID_MAX and GRID_MIN <= node[1] <= GRID_MAX


def octile(a, b):
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return (max(dx, dy) - min(dx, dy)) + math.sqrt(2) * min(dx, dy)


def to_latlon(node, center):
    """Cell centre -> (lat, lon). Longitude spacing is corrected for latitude so cells are square."""
    lat0, lon0 = center
    dlat = CELL_KM / 110.574
    dlon = CELL_KM / (111.320 * max(0.05, math.cos(math.radians(lat0))))
    return (lat0 + node[1] * dlat, lon0 + node[0] * dlon)


def cell_bounds(node, center):
    """South-west and north-east lat/lon corners of a cell (for drawing rectangles)."""
    lat, lon = to_latlon(node, center)
    lat0 = center[0]
    hlat = CELL_KM / 110.574 / 2
    hlon = CELL_KM / (111.320 * max(0.05, math.cos(math.radians(lat0)))) / 2
    return [(lat - hlat, lon - hlon), (lat + hlat, lon + hlon)]


class Hazards:
    """Closed sectors as a function of time; only hazards the planner already
    'knows' (from_t <= known_t) are returned, so a restriction that appears
    mid-run cannot influence plans made before it was announced."""

    def __init__(self, specs):
        self.specs = specs
        self._cache = {}

    def _cells(self, spec, t):
        if spec["kind"] == "rect":
            x0, x1, y0, y1 = spec["rect"]
            return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
        cx = spec["start"][0] + spec["velocity"][0] * (t - spec["from_t"])
        cy = spec["start"][1] + spec["velocity"][1] * (t - spec["from_t"])
        cx, cy, s = round(cx), round(cy), spec["size"]
        return {(x, y) for x in range(cx - s, cx + s + 1) for y in range(cy - s, cy + s + 1) if in_grid((x, y))}

    def active_at(self, t, known_t):
        key = (t, known_t)
        if key not in self._cache:
            cells = set()
            for spec in self.specs:
                if spec["from_t"] > known_t or t < spec["from_t"]:
                    continue
                if spec["until_t"] is not None and t >= spec["until_t"]:
                    continue
                cells |= self._cells(spec, t)
            # Airports themselves are never closed by a sector: airport closure is a separate flag.
            self._cache[key] = cells - AIRPORT_CELLS
        return self._cache[key]

    def change_times(self):
        times = set()
        for spec in self.specs:
            if spec["from_t"] > 0:
                times.add(spec["from_t"])
            if spec["until_t"] is not None:
                times.add(spec["until_t"])
        return times

    def snapshot(self, t):
        """Draw data: [(label, cells)] of everything physically active at step t."""
        out = []
        for spec in self.specs:
            if t < spec["from_t"] or (spec["until_t"] is not None and t >= spec["until_t"]):
                continue
            out.append((spec["label"], self._cells(spec, t)))
        return out


class RunwayBook:
    """Runway slots at each airport. A landing holds a runway for `occ` steps."""

    def __init__(self, capacities, schedule_change=None):
        # capacities: {airport: runway count}; schedule_change: (t, n) applies to PRIMARY only.
        self.capacities = dict(capacities)
        self.change = schedule_change
        self.uses = {name: [] for name in capacities}

    def capacity(self, airport, t):
        if airport == PRIMARY and self.change and t >= self.change[0]:
            return self.change[1]
        return self.capacities.get(airport, 0)

    def active(self, airport, t):
        return sum(1 for (s, o) in self.uses[airport] if s <= t < s + o)

    def can_land(self, airport, t, occ):
        """A landing needs a runway free for its whole occupancy window. A runway that
        closes later only affects landings that START after the closure."""
        cap = self.capacity(airport, t)
        return cap >= 1 and all(self.active(airport, u) + 1 <= cap for u in range(t, t + occ))

    def add(self, airport, t, occ):
        self.uses[airport].append((t, occ))

    def overload(self):
        """Landings that start while more aircraft occupy the runways than exist."""
        return sum(1 for airport, uses in self.uses.items() for (s, _) in uses
                   if self.active(airport, s) > self.capacity(airport, s))

    def copy(self):
        other = RunwayBook(self.capacities, self.change)
        other.uses = {k: list(v) for k, v in self.uses.items()}
        return other


def crosswind_kt(wind_kt, gust_kt, wind_dir_deg):
    """Crosswind component (kt) on runway 09/27 using the stronger of wind and gust."""
    speed = max(wind_kt, gust_kt)
    return abs(speed * math.sin(math.radians(wind_dir_deg - RUNWAY_AXIS_DEG)))
