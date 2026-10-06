"""Illustrative landing-mass model for aircraft that must reduce weight before landing.

An overweight arrival has to burn fuel (or jettison, where the type can) before it
may land, which becomes a *minimum landing time* in the planner: it holds, with the
rest of the traffic planned around it. Numbers are generic class-level
assumptions, NOT aircraft-specific data - real landing-mass limits, jettison
capability and procedures come from the aircraft manual and the crew/ATC.
"""
import math

from .grid import STEP_MINUTES

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


def assign_overweight_case(profile, rng):
    """Deterministic (seeded) overweight case for one aircraft -> dict."""
    spec = PROFILE_MASS.get(profile, PROFILE_MASS["Narrowbody"])
    lo, hi = spec["excess_t"]
    excess = round(rng.uniform(lo, hi), 1)
    rate = JETTISON_T_PER_MIN if spec["jettison"] else BURN_T_PER_MIN
    needed_steps = math.ceil(excess / rate / STEP_MINUTES)
    hold_steps = min(MAX_HOLD_STEPS, needed_steps)
    return {
        "landing_mass_limit_t": spec["mlw_t"],
        "predicted_landing_mass_t": round(spec["mlw_t"] + excess, 1),
        "excess_t": excess,
        "method": "fuel jettison" if spec["jettison"] else "fuel burn-off (holding)",
        "reduction_rate_t_per_min": rate,
        "needed_minutes": needed_steps * STEP_MINUTES,
        "hold_steps": hold_steps,
        "capped": needed_steps > MAX_HOLD_STEPS,
    }
