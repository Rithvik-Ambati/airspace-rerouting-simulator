"""Illustrative landing-mass model and the land-now / hold / divert decision.

An aircraft above its normal maximum landing mass (MLM) has options, and none of them is
always right:
  * LAND NOW   - land at the earliest feasible slot, overweight. Allowed only if the
                 runway still covers the (longer) landing distance; flagged for
                 post-landing inspection. Often the safest choice in a time-critical emergency.
  * HOLD       - burn fuel (or jettison, where the type can) until mass is at the limit,
                 then land. Costs time and endurance.
  * DIVERT     - the same two options evaluated at the alternate airport.
Every option is planned by the real planner (so traffic, hazards, runway slots and fuel
all count), then ranked by an explicit, documented rule (choose_option). The rule is a
decision-support illustration, NOT an operational procedure: real decisions belong to the
crew and ATC using approved aircraft data.

Numbers are generic class-level assumptions, not aircraft-specific data.
"""
import math

from .grid import PRIMARY, STEP_MINUTES

MAX_HOLD_STEPS = 25   # cap so a single heavy case cannot consume the whole horizon

# Representative values per profile band.
PROFILE_MASS = {
    "Regional jet": {"mlw_t": 38.0, "excess_t": (0.3, 1.5), "jettison": False},
    "Turboprop":    {"mlw_t": 20.0, "excess_t": (0.3, 1.2), "jettison": False},
    "Narrowbody":   {"mlw_t": 66.0, "excess_t": (0.3, 1.5), "jettison": False},
    "Widebody":     {"mlw_t": 205.0, "excess_t": (2.0, 10.0), "jettison": True},
}
BURN_T_PER_MIN = 0.045      # ~2.7 t/h holding burn
JETTISON_T_PER_MIN = 1.0
# Illustrative: each 1% of excess mass adds this % to the required landing distance.
LANDING_DISTANCE_FACTOR = 1.5
# Emergencies where landing sooner outweighs the overweight penalty.
IMMEDIATE_EVENTS = {"MAYDAY", "MEDICAL", "FUEL", "7500", "7700", "TECH"}


def assign_overweight_case(profile, rng):
    """Deterministic (seeded) overweight case for one aircraft -> dict."""
    spec = PROFILE_MASS.get(profile, PROFILE_MASS["Narrowbody"])
    lo, hi = spec["excess_t"]
    excess = round(rng.uniform(lo, hi), 1)
    rate = JETTISON_T_PER_MIN if spec["jettison"] else BURN_T_PER_MIN
    needed_steps = math.ceil(excess / rate / STEP_MINUTES)
    return {
        "landing_mass_limit_t": spec["mlw_t"],
        "predicted_landing_mass_t": round(spec["mlw_t"] + excess, 1),
        "excess_t": excess,
        "method": "fuel jettison" if spec["jettison"] else "fuel burn-off (holding)",
        "reduction_rate_t_per_min": rate,
        "needed_minutes": needed_steps * STEP_MINUTES,
        "hold_steps": min(MAX_HOLD_STEPS, needed_steps),
        "capped": needed_steps > MAX_HOLD_STEPS,
    }


def excess_at_arrival(case, arrival_step):
    """Tonnes above the limit at touchdown if the aircraft reduces mass from step 0 (never negative)."""
    return max(0.0, round(case["excess_t"] - case["reduction_rate_t_per_min"] * arrival_step * STEP_MINUTES, 2))


def landing_distance_required_m(base_runway_m, case, arrival_step):
    """Illustrative required landing distance at the mass the aircraft will have on arrival."""
    frac = excess_at_arrival(case, arrival_step) / case["landing_mass_limit_t"]
    return base_runway_m * (1 + LANDING_DISTANCE_FACTOR * frac)


def choose_option(options, event):
    """Pick one option from the feasible ones. Returns (option or None, rationale).

    Each option: {airport, mode ('land_now'|'hold'), arrival (step), feasible, overweight_landing}.
      * time-critical emergency (IMMEDIATE_EVENTS): earliest arrival wins - delaying to shed mass
        is not justified when landing sooner is safer.
      * otherwise: prefer an option that lands at or under the limit; among those, earliest.
        If none exists, earliest overall.
    Ties go to the primary airport, then to land-now.
    """
    feasible = [o for o in options if o["feasible"]]
    if not feasible:
        return None, "No option is feasible (see per-option reasons)."
    rank = lambda o: (o["arrival"], o["airport"] != PRIMARY, o["mode"] != "land_now")
    if event in IMMEDIATE_EVENTS:
        best = min(feasible, key=rank)
        return best, ("Time-critical emergency: earliest feasible landing preferred"
                      + (" (overweight landing accepted; inspection required)." if best["overweight_landing"] else "."))
    within = [o for o in feasible if not o["overweight_landing"]]
    if within:
        best = min(within, key=rank)
        return best, "Not time-critical: option that reaches the landing-mass limit before touchdown preferred."
    best = min(feasible, key=rank)
    return best, "No option reaches the limit in time: earliest feasible landing chosen (overweight; inspection required)."
