"""Folium map construction for the operations view and the live-data tab."""
import folium

from simulator.grid import GRID_MAX, GRID_MIN, cell_bounds

COLORS = ["#38bdf8", "#fbbf24", "#a78bfa", "#34d399", "#fb7185", "#f97316", "#60a5fa", "#e879f9"]
FT_PER_M, KT_PER_MPS, FPM_PER_MPS = 3.28084, 1.94384, 196.8504


def _live_popup(ac):
    alt, spd, vr = ac.get("baro_altitude_m"), ac.get("velocity_mps"), ac.get("vertical_rate_mps")
    lines = [
        f"<b>LIVE AIRCRAFT · {ac.get('callsign') or 'Callsign unavailable'}</b>",
        f"ICAO24: {ac.get('icao24') or '—'}",
        f"Country: {ac.get('origin_country') or 'Unavailable'}",
        f"Altitude: {round(alt * FT_PER_M):,} ft" if alt is not None else "Altitude: unavailable",
        f"Ground speed: {spd * KT_PER_MPS:.1f} kt" if spd is not None else "Ground speed: unavailable",
        f"Heading: {ac['heading_deg']:.0f}°" if ac.get("heading_deg") is not None else "Heading: unavailable",
        f"Vertical rate: {vr * FPM_PER_MPS:.0f} ft/min" if vr is not None else "Vertical rate: unavailable",
        f"On ground: {ac.get('on_ground')}",
        f"Squawk: {ac.get('squawk') or 'Unavailable'}",
        "Actual route/ETA/runway: not supplied by this position feed",
    ]
    return "<br>".join(lines)


def add_live_aircraft(fmap, live, radius=6):
    for ac in live.get("aircraft", []):
        if ac.get("latitude") is None or ac.get("longitude") is None:
            continue
        html = _live_popup(ac)
        folium.CircleMarker([ac["latitude"], ac["longitude"]], radius=radius, color="#20a4f3", fill=True,
                            fill_color="#20a4f3", fill_opacity=0.95, weight=2,
                            tooltip=folium.Tooltip(html, sticky=True),
                            popup=folium.Popup(html, max_width=340)).add_to(fmap)


def live_rows(live):
    rows = []
    for ac in live.get("aircraft", []):
        alt, spd, vr = ac.get("baro_altitude_m"), ac.get("velocity_mps"), ac.get("vertical_rate_mps")
        rows.append({
            "Callsign / flight ID": ac.get("callsign") or "Unavailable", "ICAO24": ac.get("icao24") or "—",
            "Country": ac.get("origin_country") or "—", "Latitude": ac.get("latitude"),
            "Longitude": ac.get("longitude"),
            "Altitude (ft)": round(alt * FT_PER_M) if alt is not None else None,
            "Ground speed (kt)": round(spd * KT_PER_MPS, 1) if spd is not None else None,
            "Heading (°)": ac.get("heading_deg"),
            "Vertical rate (ft/min)": round(vr * FPM_PER_MPS) if vr is not None else None,
            "Squawk": ac.get("squawk") or "—", "On ground": ac.get("on_ground"),
            "Last contact (Unix)": ac.get("last_contact"),
        })
    return rows


def build_ops_map(result, airport, step, live=None):
    """Full routes, hazards and aircraft positions at `step`, both airports, optional live overlay."""
    fmap = folium.Map(location=[airport["latitude_deg"], airport["longitude_deg"]], zoom_start=8,
                      tiles="OpenStreetMap", control_scale=True, zoom_snap=0.1)
    # Frame the whole 11x11 simulated airspace (plus a margin) instead of an arbitrary zoom level.
    sw, ne = cell_bounds((GRID_MIN, GRID_MIN), result["center"])[0], cell_bounds((GRID_MAX, GRID_MAX), result["center"])[1]
    fmap.fit_bounds([sw, ne], padding=(12, 12))
    primary, alt = result["airports"]["PRIMARY"], result["airports"]["ALT"]
    status = result["airport_status"]
    folium.Marker(primary, tooltip=f"{airport['name']} · {'open' if status['PRIMARY'] else 'CLOSED'}",
                  icon=folium.Icon(color="blue" if status["PRIMARY"] else "red", icon="plane", prefix="fa")).add_to(fmap)
    folium.Marker(alt, tooltip=f"Alternate airport · {'open' if status['ALT'] else 'CLOSED'}",
                  icon=folium.Icon(color="green" if status["ALT"] else "red", icon="plane", prefix="fa")).add_to(fmap)
    if live and not live.get("error"):
        add_live_aircraft(fmap, live)

    # Hazards drawn exactly as the planner sees them: one rectangle per blocked cell at this step.
    for frame in result["hazard_frames"].get(step, []):
        for sw, ne in frame["bounds"]:
            folium.Rectangle([sw, ne], color="#ff5964", weight=1, fill=True, fill_opacity=0.28,
                             tooltip=f"{frame['label']} (step {step})").add_to(fmap)

    for i, a in enumerate(result["aircraft"]):
        color = "#ff3b5c" if a["emergency"] else COLORS[i % len(COLORS)]
        if len(a["original_route"]) >= 2:
            folium.PolyLine(a["original_route"], color="#9CA3AF", weight=2, opacity=.6, dash_array="7, 7",
                            tooltip=f'{a["callsign"]}: ORIGINAL route').add_to(fmap)
        if len(a["route"]) >= 2:
            folium.PolyLine(a["route"], color=color, weight=5 if a["emergency"] else (4 if a["route_changed"] else 2),
                            opacity=.95, tooltip=f'{a["callsign"]} · {a["profile"]} · {a["status"]}').add_to(fmap)
        nodes = a["route"]
        if nodes:
            idx = min(step, len(nodes) - 1)
            arrived = step >= len(nodes) - 1
            if a["failed"]:
                state = "not flying: " + a["status"]
            else:
                state = "arrived/landed" if arrived else "en route"
            label = f'{a["callsign"]} · {state}' + (" · uncertain position" if a["uncertain_position"] else "")
            folium.CircleMarker(nodes[idx], radius=7, color=color, fill=True, fill_opacity=0.35 if arrived else 1,
                                weight=3 if a["uncertain_position"] else 1, tooltip=label).add_to(fmap)
    return fmap
