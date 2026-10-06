"""Scenario catalogue: 49 individual cases plus 5 compound demonstrations.

Every scenario has two parts:
  * descriptive metadata (title, category, description, tags) in SCENARIOS, and
  * an ``effects`` dict (EFFECTS / DEFAULT_EFFECTS below) that the engine
    actually executes: hazards, emergencies, runway state, data quality...
The engine contains no scenario-id lists - add or change behaviour here only.
"""
import copy


def _s(i, title, category, description, tags):
    return {"id": i, "title": title, "category": category, "description": description, "tags": tags}


SCENARIOS = [
_s(1,"MAYDAY — critical distress","Emergency","A simulated aircraft declares distress and needs urgent assistance.",["mayday","distress","priority"]),
_s(2,"PAN-PAN — urgency","Emergency","An urgent but not yet distress-level event may escalate.",["pan-pan","urgency","escalation"]),
_s(3,"Squawk 7700 — general emergency","Emergency","A general emergency indication is raised; cause remains a separate field.",["7700","emergency"]),
_s(4,"Squawk 7500 — unlawful interference","Emergency","A security-sensitive simulated event invokes a dedicated policy.",["7500","security"]),
_s(5,"Squawk 7600 — radio failure","Emergency","Communication loss is simulated with uncertainty and contingency assumptions.",["7600","communications"]),
_s(6,"Engine failure / technical malfunction","Emergency","Aircraft performance assumptions change and candidate destinations are reevaluated.",["technical","performance"]),
_s(7,"Onboard medical emergency","Emergency","Medical response time and feasible diversion options are considered.",["medical","time-sensitive"]),
_s(8,"Low fuel / fuel-system alert","Emergency","Available endurance constrains feasible destination and route choices.",["fuel","resource"]),
_s(9,"Presidential visit / VIP security zone","Security & airspace","A temporary security zone conflicts with normal traffic and an unexpected emergency.",["VIP","restriction"]),
_s(10,"Sudden temporary flight restriction","Security & airspace","A region closes while agents are in flight.",["TFR","closure"]),
_s(11,"Military exercise airspace","Security & airspace","A restricted military sector blocks otherwise attractive paths.",["military","restricted"]),
_s(12,"Airport closure","Security & airspace","One airport is removed from the destination set.",["airport","closure"]),
_s(13,"Airspace corridor closure","Security & airspace","A major graph corridor is blocked and affected paths are recomputed.",["corridor","reroute"]),
_s(14,"Drone incursion near airport","Security & airspace","A localized synthetic hazard affects nearby traffic.",["drone","hazard"]),
_s(15,"Security restriction changes mid-flight","Security & airspace","The restricted geometry changes while routes are active.",["dynamic","restriction"]),
_s(16,"Severe crosswind","Weather","Runway feasibility is evaluated against configured aircraft limits.",["crosswind","runway"]),
_s(17,"Gusting wind","Weather","Gust inputs change and runway feasibility is recalculated.",["gusts","runway"]),
_s(18,"Moving thunderstorm","Weather","A time-varying weather hazard moves across the graph.",["storm","moving"]),
_s(19,"Heavy rain / reduced visibility","Weather","Configurable visibility constraints change feasible options.",["rain","visibility"]),
_s(20,"Fog / low visibility","Weather","Landing options are reevaluated under simulated visibility limits.",["fog","visibility"]),
_s(21,"Windshear alert","Weather","A synthetic alert marks an approach area as unavailable for the scenario.",["windshear","hazard"]),
_s(22,"Weather deteriorates during reroute","Weather","A route becomes invalid after conditions change.",["dynamic","replan"]),
_s(23,"Weather feed unavailable","Weather","Weather uncertainty is explicitly surfaced instead of assuming safe conditions.",["data","uncertainty"]),
_s(24,"Sudden runway closure","Airport & runway","A runway is marked unavailable during the simulation.",["runway","closure"]),
_s(25,"Aircraft-specific runway compatibility","Airport & runway","Runway candidates are filtered by configurable length and compatibility.",["aircraft","compatibility"]),
_s(26,"Heterogeneous aircraft performance","Airport & runway","Heavy, narrowbody, regional and turboprop profiles have different constraints.",["aircraft","heterogeneous"]),
_s(27,"Runway congestion","Airport & runway","Several arrivals compete for limited runway occupancy windows.",["capacity","queue"]),
_s(28,"Limited runway capacity","Airport & runway","Landing slots are constrained and must be scheduled.",["capacity","scheduling"]),
_s(29,"Required emergency services unavailable","Airport & runway","Relevant destinations are filtered or flagged when modeled support is unavailable.",["services","feasibility"]),
_s(30,"Diversion airport at capacity","Airport & runway","An alternate airport cannot accept unlimited redirected traffic.",["diversion","capacity"]),
_s(31,"Taxiway / ground movement disruption","Airport & runway","A post-landing ground constraint is included in scenario outcomes.",["taxiway","ground"]),
_s(32,"Two aircraft converge on same cell","Multi-agent","Space-time occupancy conflicts are detected and resolved where possible.",["conflict","separation"]),
_s(33,"Multiple emergency landing requests","Multi-agent","Several urgent agents compete for limited capacity.",["multiple","emergency"]),
_s(34,"Emergency versus VIP restriction","Multi-agent","Emergency and security constraints are evaluated together.",["emergency","VIP"]),
_s(35,"Emergency diverts regional traffic","Multi-agent","A destination disruption causes neighboring airports to absorb traffic.",["cascade","diversion"]),
_s(36,"Aircraft compete for same runway","Multi-agent","Runway occupancy and arrival sequencing are modeled.",["runway","scheduling"]),
_s(37,"Reroute creates a new conflict","Multi-agent","A changed route is checked against other agents' reservations.",["replan","conflict"]),
_s(38,"Several emergencies simultaneously","Multi-agent","Different event types are active in one compound simulation.",["multi-event","coordination"]),
_s(39,"No feasible conflict-free plan","Multi-agent","The planner should report infeasibility rather than invent a safe route.",["infeasible","safety"]),
_s(40,"PAN-PAN escalates to MAYDAY","Emergency","An event state changes and triggers reprioritization and replanning.",["escalation","mayday"]),
_s(41,"Second emergency mid-reroute","Data resilience","A new event invalidates part of the current solution.",["dynamic","event"]),
_s(42,"Delayed aircraft position update","Data resilience","Stale observations are identified and flagged.",["stale-data","uncertainty"]),
_s(43,"Missing callsign or identity","Data resilience","Incomplete data is handled without inventing identity.",["missing-data","identity"]),
_s(44,"Position uncertainty increases","Data resilience","Aircraft position is represented by an uncertainty region.",["GPS","uncertainty"]),
_s(45,"Flight API unavailable","Data resilience","The last snapshot is retained with a stale-data warning.",["API","resilience"]),
_s(46,"Mismatched data timestamps","Data resilience","Flight and weather data freshness is tracked independently.",["timestamps","resilience"]),
_s(47,"Route oscillation","Data resilience","Repeated route changes are monitored and damped in the prototype.",["oscillation","replanning"]),
_s(48,"Emergency resolves / is cancelled","Data resilience","An active event clears and routes can be recomputed.",["event-clear","replan"]),
_s(49,"No feasible destination","Data resilience","The simulator reports that no candidate satisfies current modeled constraints.",["infeasible","safety"]),
_s(50,"Flagship: VIP restriction + MAYDAY","Combined","A distress event occurs during a security restriction with normal traffic present.",["compound","VIP","mayday"]),
_s(51,"Flagship: MAYDAY + medical + gusts","Combined","Multiple urgent cases and weather constraints compete for landing options.",["compound","medical","weather"]),
_s(52,"Flagship: multiple emergencies + runway closure","Combined","Limited runway availability intersects multiple urgent requests.",["compound","runway","capacity"]),
_s(53,"Flagship: moving storm + cascading diversions","Combined","A moving hazard redirects traffic and triggers a second event.",["compound","storm","cascade"]),
_s(54,"Flagship: full-system stress test","Combined","A compound scenario combines restrictions, emergencies, weather, runway and data issues.",["compound","stress-test"]),
]

# --------------------------------------------------------------------------
# Effects. Grid coordinates: x east, y north, both -5..5; the primary airport
# is the origin and the alternate airport sits at (4, -3).
# --------------------------------------------------------------------------
DEFAULT_EFFECTS = {
    "emergencies": [],          # event keys for aircraft 0,1,... (MAYDAY, PAN-PAN, 7700, 7500, 7600, MEDICAL, FUEL, TECH)
    "hazards": [],              # see hazard() / storm() below
    "timeline": [],             # {"t":int, "declare"/"escalate"/"clear": {...}}
    "runways": 2,               # primary airport runway count
    "runways_after": None,      # (t, n): runway count changes to n at step t
    "alt_runways": 2,
    "primary_open": True,
    "alt_open": True,
    "primary_services": True,   # emergency/medical services at the primary airport
    "runway_length_m": 3400,
    "alt_runway_length_m": 3000,
    "occupancy_extra": 0,       # extra runway-occupancy steps per landing (fog, ground delays...)
    "alt_occupancy_extra": 0,
    "wind_floor": None,         # (speed_kt, direction_deg) minimum wind forced by the scenario
    "gust_floor": None,
    "conservative_wind": 0,     # kt added when weather data is missing/stale
    "mixed_fleet": False,       # force every aircraft profile to appear
    "extra_traffic": 0,
    "stale_fraction": 0.0,      # share of aircraft whose position is stale/uncertain
    "uncertain_all": False,
    "missing_id_fraction": 0.0,
    "data_status": "LIVE",
    "overweight": 0,            # emergency arrivals that must burn/jettison fuel before landing
    "low_fuel": 0,              # emergency aircraft with little endurance
    "damping_demo": False,      # also run an undamped replan to report route-revision savings
}


def hazard(rect, label, from_t=0, until_t=None):
    """A static rectangular closed sector (x0, x1, y0, y1), active in [from_t, until_t)."""
    return {"kind": "rect", "rect": rect, "label": label, "from_t": from_t, "until_t": until_t}


def storm(label="Moving thunderstorm cell", from_t=0, start=(-5, 3), velocity=(0.7, -0.2), size=1):
    """A (2*size+1)-square storm cell drifting across the grid."""
    return {"kind": "storm", "label": label, "from_t": from_t, "until_t": None,
            "start": start, "velocity": velocity, "size": size}


VIP_ZONE = (1, 3, -2, 3)
CORRIDOR = (-3, -2, -5, 2)
APPROACH_DRONE = (-1, 1, 1, 2)
WINDSHEAR = (-2, -1, -1, 1)
MIL_ZONE = (1, 4, -3, 1)


def _fx(**kw):
    return kw


EFFECTS = {
    1: _fx(emergencies=["MAYDAY"]),
    2: _fx(emergencies=["PAN-PAN"], overweight=1),
    3: _fx(emergencies=["7700"]),
    4: _fx(emergencies=["7500"], hazards=[hazard((-1, 1, -1, 1), "Security isolation area")]),
    5: _fx(emergencies=["7600"]),
    6: _fx(emergencies=["TECH"], overweight=1),
    7: _fx(emergencies=["MEDICAL"]),
    8: _fx(emergencies=["FUEL"], low_fuel=1),
    9: _fx(emergencies=["MAYDAY"], hazards=[hazard(VIP_ZONE, "VIP security zone")]),
    10: _fx(hazards=[hazard(VIP_ZONE, "Temporary flight restriction", from_t=4)]),
    11: _fx(hazards=[hazard(MIL_ZONE, "Military exercise area")]),
    12: _fx(primary_open=False, emergencies=["MEDICAL"]),
    13: _fx(hazards=[hazard(CORRIDOR, "Closed corridor")]),
    14: _fx(hazards=[hazard(APPROACH_DRONE, "Drone incursion hazard", from_t=3, until_t=14)]),
    15: _fx(hazards=[hazard(VIP_ZONE, "Restriction (initial)", until_t=5),
                     hazard((0, 3, -3, 4), "Restriction (expanded)", from_t=5)]),
    16: _fx(wind_floor=(30, 180), gust_floor=33),
    17: _fx(wind_floor=(20, 200), gust_floor=31),
    18: _fx(hazards=[storm()]),
    19: _fx(occupancy_extra=1, runways=1),
    20: _fx(occupancy_extra=2, runways=1),
    21: _fx(hazards=[hazard(WINDSHEAR, "Windshear alert area", from_t=3, until_t=18)]),
    22: _fx(hazards=[hazard((-1, 2, -3, 3), "Weather deteriorates", from_t=5)]),
    23: _fx(conservative_wind=12, data_status="WEATHER UNAVAILABLE - conservative wind assumed"),
    24: _fx(runways=1, runways_after=(5, 0), alt_runways=2),
    25: _fx(mixed_fleet=True, runway_length_m=2300, alt_runway_length_m=2300),
    26: _fx(mixed_fleet=True, extra_traffic=3),
    27: _fx(runways=1, extra_traffic=4),
    28: _fx(runways=1, occupancy_extra=2, extra_traffic=2),
    29: _fx(emergencies=["MEDICAL", "MEDICAL"], primary_services=False),
    30: _fx(primary_open=False, alt_runways=1, alt_occupancy_extra=2, extra_traffic=3),
    31: _fx(occupancy_extra=3, runways=1),
    32: _fx(extra_traffic=5),
    33: _fx(emergencies=["MAYDAY", "MAYDAY", "MEDICAL"], runways=1, overweight=1),
    34: _fx(emergencies=["MAYDAY"], hazards=[hazard(VIP_ZONE, "VIP security zone")]),
    35: _fx(primary_open=False, extra_traffic=3),
    36: _fx(runways=1, extra_traffic=3),
    37: _fx(hazards=[hazard(CORRIDOR, "New restriction", from_t=4)], extra_traffic=4),
    38: _fx(emergencies=["MAYDAY", "7700", "PAN-PAN"], overweight=1),
    39: _fx(emergencies=["MAYDAY", "MAYDAY", "MAYDAY", "MAYDAY"], runways=1, occupancy_extra=12,
            alt_runways=1, alt_occupancy_extra=12, extra_traffic=2),
    40: _fx(emergencies=["PAN-PAN"], overweight=1, timeline=[{"t": 5, "escalate": {"agent": 0, "type": "MAYDAY"}}]),
    41: _fx(emergencies=["MAYDAY"], timeline=[{"t": 6, "declare": {"agent": 2, "type": "7700"}}]),
    42: _fx(stale_fraction=0.4, data_status="STALE - delayed position updates"),
    43: _fx(missing_id_fraction=0.4, data_status="INCOMPLETE - callsigns missing"),
    44: _fx(uncertain_all=True, data_status="DEGRADED - position uncertainty widened"),
    45: _fx(stale_fraction=1.0, data_status="STALE - flight API unavailable, last snapshot retained"),
    46: _fx(stale_fraction=0.3, conservative_wind=8, data_status="MISMATCHED - flight and weather timestamps differ"),
    47: _fx(hazards=[hazard((-1, 1, -3, 2), "Flickering restriction", from_t=3, until_t=6),
                     hazard((-1, 1, -3, 2), "Flickering restriction", from_t=9, until_t=12),
                     hazard((-1, 1, -3, 2), "Flickering restriction", from_t=15, until_t=18)],
            damping_demo=True),
    48: _fx(emergencies=["MAYDAY"], hazards=[hazard(VIP_ZONE, "VIP security zone")],
            timeline=[{"t": 5, "clear": {"agent": 0}}]),
    49: _fx(primary_open=False, alt_open=False, emergencies=["MAYDAY"]),
    50: _fx(emergencies=["MAYDAY"], hazards=[hazard(VIP_ZONE, "VIP security zone")], extra_traffic=2),
    51: _fx(emergencies=["MAYDAY", "MEDICAL"], wind_floor=(18, 200), gust_floor=30, overweight=1),
    52: _fx(emergencies=["MAYDAY", "7700"], runways=1, runways_after=(6, 0), extra_traffic=2),
    53: _fx(hazards=[storm()], runways=1, extra_traffic=3,
            timeline=[{"t": 8, "declare": {"agent": 3, "type": "7700"}}]),
    54: _fx(emergencies=["MAYDAY", "MEDICAL"],
            hazards=[hazard(VIP_ZONE, "VIP security zone"), storm(start=(-5, -3), velocity=(0.6, 0.25))],
            runways=1, runways_after=(10, 0), wind_floor=(14, 190), gust_floor=24, stale_fraction=0.3,
            conservative_wind=4, overweight=1, extra_traffic=3,
            data_status="DEGRADED - stale positions + conservative weather"),
}


def get_scenario(scenario_id):
    return next((s for s in SCENARIOS if s["id"] == int(scenario_id)), SCENARIOS[0])


def get_effects(scenario_id):
    """Effects for a scenario, filled with defaults. Returns a fresh deep copy."""
    fx = copy.deepcopy(DEFAULT_EFFECTS)
    fx.update(copy.deepcopy(EFFECTS.get(int(scenario_id), {})))
    return fx


def build_events(scenario_id):
    s = get_scenario(scenario_id)
    fx = get_effects(scenario_id)
    return {"scenario_id": s["id"], "scenario_title": s["title"], "tags": s["tags"],
            "emergencies": fx["emergencies"], "hazards": [h["label"] for h in fx["hazards"]],
            "timeline": fx["timeline"]}


def catalogue_with_effects():
    """Full machine-readable catalogue (this is what scenario_catalogue.json contains)."""
    return [{**s, "effects": get_effects(s["id"])} for s in SCENARIOS]
