"""Live aircraft tab (OpenSky snapshot + ADSBdb metadata lookup)."""
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from simulator.live_data import fetch_opensky, lookup_aircraft_type

from .map_view import add_live_aircraft

LABELS = {"callsign": "Callsign / flight ID", "icao24": "ICAO24", "origin_country": "Origin country",
          "aircraft_type": "Aircraft type", "latitude": "Latitude", "longitude": "Longitude",
          "altitude_ft": "Barometric altitude (ft)", "speed_kt": "Ground speed (kt)", "heading_deg": "Heading (°)",
          "vertical_rate_fpm": "Vertical rate (ft/min)", "on_ground": "On ground", "squawk": "Squawk",
          "last_contact": "Last contact (Unix)"}


def render(airport):
    st.subheader("Real-time aircraft tracking")
    st.write("Real aircraft state-vector observations from OpenSky for a bounding box. Separate from the synthetic A* simulation.")
    st.info("Live feeds can omit fields or return no aircraft when coverage or access is limited. Aircraft type and "
            "registration are queried separately. This is not an authoritative schedule, flight plan or emergency feed.")
    c1, c2, c3 = st.columns(3)
    lat = c1.number_input("Center latitude", value=float(airport["latitude_deg"]), format="%.4f", key="live_lat")
    lon = c2.number_input("Center longitude", value=float(airport["longitude_deg"]), format="%.4f", key="live_lon")
    radius = c3.slider("Bounding-box half-width (degrees)", 0.05, 1.0, 0.3, 0.05, key="live_radius")
    if st.button("↻ Fetch real aircraft now", type="primary"):
        with st.spinner("Fetching live aircraft state vectors…"):
            st.session_state.live_result = fetch_opensky(lat, lon, radius)
    live = st.session_state.get("live_result")
    if not live:
        st.caption("No live snapshot fetched yet.")
        return
    if live.get("error"):
        st.error(live["error"])
        st.caption("OpenSky may require an API client/token depending on current access limits. Try again later.")
        return
    rows = live.get("aircraft", [])
    st.success(f'Snapshot fetched at {live.get("fetched_at", "unknown time")} · {len(rows)} aircraft in the returned area')
    if not rows:
        st.warning("No aircraft returned for this box. Increase the half-width, pick another area, or retry later.")
        return
    df = pd.DataFrame(rows)
    df["altitude_ft"] = (pd.to_numeric(df["baro_altitude_m"], errors="coerce") * 3.28084).round(0)
    df["speed_kt"] = (pd.to_numeric(df["velocity_mps"], errors="coerce") * 1.94384).round(1)
    df["vertical_rate_fpm"] = (pd.to_numeric(df["vertical_rate_mps"], errors="coerce") * 196.8504).round(0)
    df["aircraft_type"] = "Lookup by ICAO24 below"
    cols = [c for c in LABELS if c in df.columns]
    st.dataframe(df[cols].rename(columns=LABELS), width="stretch", hide_index=True, height=350)

    st.markdown("#### Live aircraft map")
    fmap = folium.Map(location=[lat, lon], zoom_start=7, tiles="OpenStreetMap", control_scale=True)
    folium.Marker([lat, lon], tooltip="Selected search center",
                  icon=folium.Icon(color="blue", icon="crosshairs", prefix="fa")).add_to(fmap)
    add_live_aircraft(fmap, live, radius=5)
    st_folium(fmap, height=520, use_container_width=True, returned_objects=[])

    st.markdown("#### Aircraft type / registration lookup")
    default_hex = next((a.get("icao24") for a in rows if a.get("icao24")), "")
    hex_code = st.text_input("ICAO24 hex address", value=default_hex or "", max_chars=6, key="metadata_hex",
                             help="Copy a six-character ICAO24 value from the table above.")
    if st.button("Look up aircraft type and registration"):
        with st.spinner("Looking up aircraft metadata…"):
            st.session_state.aircraft_metadata_result = lookup_aircraft_type(hex_code)
    meta = st.session_state.get("aircraft_metadata_result")
    if meta:
        if meta.get("error"):
            st.warning(meta["error"])
        else:
            for col, key, label in zip(st.columns(3), ("type", "icao_type", "registration"),
                                       ("Aircraft type / model", "ICAO type code", "Registration")):
                col.metric(label, meta.get(key) or "Not supplied")
            st.write({"Manufacturer": meta.get("manufacturer"), "Operator": meta.get("operator"),
                      "Registered owner": meta.get("registered_owner"), "ICAO24": meta.get("icao24")})
            st.caption("Source: ADSBdb. Metadata can be missing or outdated and does not prove a flight number or route.")
    st.caption("OpenSky observations are a point-in-time snapshot. Source: OpenSky Network.")
