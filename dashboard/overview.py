"""Operations view: metrics, map with a time slider, planner outcomes, landing cases, safety gate."""
from datetime import datetime

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from simulator.benchmark import PLANNER_LABEL
from simulator.grid import STEP_MINUTES

from .map_view import build_ops_map, live_rows


def render_weather(weather):
    with st.expander("🌦️ Live weather at selected airport", expanded=bool(weather)):
        if not weather:
            st.caption("No weather snapshot for this airport yet. Use **Refresh live weather** in the sidebar.")
        elif weather.get("error"):
            st.error(weather["error"])
        else:
            cur, units = weather.get("current", {}), weather.get("units", {})
            fields = [("Temperature", "temperature_2m"), ("Wind", "wind_speed_10m"), ("Wind gusts", "wind_gusts_10m"),
                      ("Wind direction", "wind_direction_10m"), ("Precipitation", "precipitation")]
            for col, (label, key) in zip(st.columns(5), fields):
                value = cur.get(key)
                col.metric(label, f"{value} {units.get(key, '')}".strip() if value is not None else "Unavailable")
            st.caption(f"Observation time: {weather.get('time', 'not supplied')} · fetched "
                       f"{weather.get('fetched_at', 'time unavailable')} · Source: Open-Meteo. "
                       "Contextual only, not an official aviation weather feed.")


def _metrics(m):
    cols = st.columns(7)
    cols[0].metric("Aircraft agents", m["aircraft"])
    cols[1].metric("Rerouted", m["rerouted"], help="Flight path differs from its unimpeded shortest path (hazards, deconfliction or diversion).")
    cols[2].metric("Delayed / holding", m["delayed"])
    cols[3].metric("Diverted", m["diverted"])
    cols[4].metric("Not flyable", m["infeasible"], help="No legal plan exists under the modelled constraints.")
    cols[5].metric("Conflicts", m["conflicts"], help="Same-cell, swap and runway-overload events in the final plan.")
    cols[6].metric("Planning time", f'{m["planning_ms"]:.0f} ms')


def _outcome_rows(result):
    base = datetime.now().astimezone()
    rows = []
    for a in result["aircraft"]:
        fmt = lambda steps: (base + pd.to_timedelta(steps * STEP_MINUTES, unit="m")).strftime("%H:%M")
        rows.append({
            "Aircraft": a["callsign"], "Type": a["profile"], "Role": a["kind"], "Event": a["event"],
            "Plan": a["status"], "Destination": a["destination"] or "—",
            # Text columns throughout: an aircraft that never flew shows "—", not the stub of an unflown track.
            "Original km": f'{a["original_distance_km"]:.1f}',
            "Revised km": "—" if a["failed"] else f'{a["distance_km"]:.1f}',
            "Original ETA": fmt(a["original_arrival_step"]),
            "New ETA": "—" if a["failed"] else fmt(a["arrival_step"]),
            "Delay (min)": "—" if a["failed"] else f'{a["delay_steps"] * STEP_MINUTES:g}',
            "Holding steps": "—" if a["failed"] else str(a["wait_steps"]),
            "Plan revisions": str(a["revisions"]),
            "Position data": "uncertain" if a["uncertain_position"] else "nominal",
        })
    if not any(a["uncertain_position"] for a in result["aircraft"]):
        for r in rows:
            del r["Position data"]
    return rows


def _landing_cases(result):
    cases = [a for a in result["aircraft"] if a["landing_case"]]
    if not cases:
        return
    st.markdown("#### Overweight landing decisions: land now, hold or divert (illustrative)")
    st.caption("Seeded cases. For each aircraft the planner plans land-now and hold at both airports (traffic, hazards, "
               "runway slots and fuel all apply), discards options the runway cannot support at that mass, then applies an "
               "explicit rule: a time-critical emergency lands at the earliest feasible slot (an overweight landing is "
               "accepted and flagged for inspection); otherwise an option that reaches the limit before touchdown is "
               "preferred. Mass limits and rates are class-level illustrations, not aircraft data, and this is not an "
               "operational procedure - the decision belongs to the crew and ATC.")
    rows = []
    for a in cases:
        c, d = a["landing_case"], a["landing_decision"] or {}
        touchdown = d.get("excess_at_touchdown_t")
        rows.append({"Aircraft": a["callsign"], "Type": a["profile"], "Event": a["event"],
                     "Mass (t)": str(c["predicted_landing_mass_t"]), "Limit (t)": str(c["landing_mass_limit_t"]),
                     "Excess (t)": str(c["excess_t"]), "Reduction": c["method"],
                     "Decision": (d.get("mode") or "none").replace("_", " ") + (f" at {d['airport']}" if d.get("airport") else ""),
                     "Excess at touchdown (t)": "—" if touchdown is None else f"{touchdown:g}",
                     "Why": d.get("rationale", "")})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                 column_config={"Why": st.column_config.TextColumn(width="large"),
                                "Decision": st.column_config.TextColumn(width="medium"),
                                "Event": st.column_config.TextColumn(width="medium"),
                                "Reduction": st.column_config.TextColumn(width="medium"),
                                **{c: st.column_config.Column(width="small") for c in (
                                    "Aircraft", "Type", "Mass (t)", "Limit (t)", "Excess (t)", "Excess at touchdown (t)")}})
    with st.expander("Options considered for each aircraft", expanded=True):
        for a in cases:
            d = a["landing_decision"]
            if not d:
                continue
            st.markdown(f"**{a['callsign']}** ({a['profile']}, {a['event']})")
            st.dataframe(pd.DataFrame([{
                "Airport": o["airport"], "Option": o["mode"].replace("_", " "), "Touchdown step": o["arrival"],
                "Feasible": o["feasible"], "Overweight at touchdown": o["overweight_landing"],
                "Excess at touchdown (t)": o["excess_at_touchdown_t"], "Reason if not feasible": o["reason"] or "",
            } for o in d["options"]]), width="stretch", hide_index=True)


def render(result, selected, settings):
    m = result["metrics"]
    st.subheader(selected["title"])
    st.caption(selected["description"])
    if m["data_status"] != "LIVE":
        st.warning(f"Data status: {m['data_status']}. Affected aircraft keep a widened safety footprint and no identity is invented.")
    _metrics(m)
    st.caption(f"Planner: {PLANNER_LABEL[m['planner']]} · crosswind on runway 09/27 ≈ {m['crosswind_kt']} kt "
               f"(wind {m['wind_speed']:.0f} / gusts {m['gust_speed']:.0f} kt from {m['wind_direction']:.0f}°) · "
               f"1 step = {STEP_MINUTES:g} min = 1 grid cell")
    if "route_revisions_undamped" in m:
        st.info(f"Damped replanning changed plans {m['route_revisions']} time(s); replanning every aircraft at every "
                f"change (no damping) would have changed them {m['route_revisions_undamped']} times.")

    airport = settings["airport"]
    live = st.session_state.get("ops_live_result")
    center = (float(airport["latitude_deg"]), float(airport["longitude_deg"]))
    live_here = live if live and st.session_state.get("ops_live_center") == center else None

    left, right = st.columns([1.7, 1])
    with left:
        st.markdown("#### Airspace and route visualization")
        step = st.slider("Time step (minutes into the run)", 0, result["max_step"], 0)
        st_folium(build_ops_map(result, airport, step, live_here), height=560, use_container_width=True, returned_objects=[])
        st.caption("Dashed grey = original (unimpeded) route. Solid = planned route (red = emergency). Red squares = closed "
                   "sectors at the chosen step. Dots = aircraft position at that step. Blue dots = real OpenSky snapshot "
                   "(position only; routes/runways are simulated).")
        if live_here:
            if live_here.get("error"):
                st.error(live_here["error"])
            else:
                st.caption(f"Live snapshot fetched: {live_here.get('fetched_at', 'time unavailable')} · "
                           f"{len(live_here.get('aircraft', []))} aircraft returned")
    with right:
        st.markdown("#### Active event")
        fx = result["effects"]
        bits = []
        if fx["emergencies"]:
            bits.append("Emergencies: " + ", ".join(fx["emergencies"]))
        if fx["hazards"]:
            bits.append("Hazards: " + ", ".join(sorted({h["label"] for h in fx["hazards"]})))
        if fx["timeline"]:
            bits.append("Timed events at step(s) " + ", ".join(str(e["t"]) for e in fx["timeline"]))
        if not result["airport_status"]["PRIMARY"]:
            bits.append("Primary airport closed")
        if not result["airport_status"]["ALT"]:
            bits.append("Alternate airport closed")
        st.info(f'**{selected["title"]}**\n\n{selected["description"]}\n\n' + ("\n\n".join(bits) if bits else "No modelled disruption beyond normal traffic."))
        st.markdown("#### Safety gate")
        problems = []
        if m["conflicts"]:
            problems.append(f"{m['conflicts']} conflict(s) in the final plan")
        if m["infeasible"]:
            reasons = sorted({a["fail_reason"] or "NO FEASIBLE PLAN" for a in result["aircraft"] if a["failed"]})
            problems.append(f"{m['infeasible']} aircraft without a legal plan ({', '.join(reasons)})")
        if problems:
            st.warning("Needs review: " + "; ".join(problems) + ". A prototype pass is not a real-world safety certification.")
        else:
            st.success("All simulated paths passed the prototype's configured checks.")

        if live_here and not live_here.get("error"):
            st.markdown("#### Live aircraft details · real observations")
            rows = live_rows(live_here)
            if rows:
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=300)
            else:
                st.info("The live feed returned no aircraft with position data in this area.")
        else:
            st.info("Click **Fetch live flights for operations map** in the sidebar to overlay real aircraft positions.")
    st.markdown("#### Planner outcomes")
    st.dataframe(pd.DataFrame(_outcome_rows(result)), width="stretch", hide_index=True,
                 height=min(560, 38 + 35 * len(result["aircraft"])),
                 column_config={"Plan": st.column_config.TextColumn(width="large"),
                                "Event": st.column_config.TextColumn(width="medium"),
                                **{c: st.column_config.Column(width="small") for c in (
                                    "Aircraft", "Type", "Role", "Destination", "Original km", "Revised km",
                                    "Original ETA", "New ETA", "Delay (min)", "Holding steps", "Plan revisions",
                                    "Position data")}})
    _landing_cases(result)
