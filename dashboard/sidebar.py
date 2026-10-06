import streamlit as st

from simulator.airport_context import FEATURED_AIRPORTS, fetch_weather, search_airports
from simulator.benchmark import PLANNER_LABEL
from simulator.engine import PLANNERS
from simulator.live_data import fetch_opensky
from simulator.scenarios import SCENARIOS

KT_PER_KMH = 0.539957
CATEGORIES = ["All", "Emergency", "Security & airspace", "Weather", "Airport & runway", "Multi-agent",
              "Data resilience", "Combined"]


def _label(a):
    return f"{a.get('name', 'Airport')} · {a.get('iata') or '—'} / {a.get('icao') or '—'} · {a.get('municipality') or ''}"


def init_state():
    st.session_state.setdefault("airport_options", FEATURED_AIRPORTS)
    st.session_state.setdefault("selected_airport", FEATURED_AIRPORTS[0])
    st.session_state.setdefault("last_run", None)


def render():
    """Draw the sidebar and return the chosen settings."""
    s = {}
    with st.sidebar:
        st.markdown("## ✈️ AeroRescue")
        st.caption("Research-grade airspace disruption simulator")
        st.divider()
        st.markdown("### Airport & airspace")
        query = st.text_input("Find airport by name or code", value="Bengaluru",
                              placeholder="e.g. BLR, VOBL, Heathrow, JFK")
        if st.button("Search airport directory", width="stretch"):
            with st.spinner("Searching airport directory…"):
                found = search_airports(query)
            if found:
                st.session_state.airport_options = found
                st.session_state.airport_search_message = f"Found {len(found)} matching airport(s)."
            else:
                st.session_state.airport_search_message = "No match found. Try an ICAO/IATA code or a shorter name."
        if st.session_state.get("airport_search_message"):
            st.caption(st.session_state.airport_search_message)
        options = st.session_state.airport_options
        labels = [_label(a) for a in options]
        prior = _label(st.session_state.selected_airport)
        chosen = st.selectbox("Simulation airport", labels, index=labels.index(prior) if prior in labels else 0)
        airport = options[labels.index(chosen)]
        st.session_state.selected_airport = airport
        s["airport"] = airport
        st.caption(f"Center: {airport['latitude_deg']:.4f}, {airport['longitude_deg']:.4f}")

        st.markdown("### Scenario controls")
        category = st.selectbox("Scenario category", CATEGORIES)
        pool = [x for x in SCENARIOS if category == "All" or x["category"] == category]
        default_idx = next((i for i, x in enumerate(pool) if x["id"] == 10), 0)
        title = st.selectbox("Scenario", [x["title"] for x in pool], index=default_idx)
        s["scenario"] = next(x for x in pool if x["title"] == title)
        s["aircraft_count"] = st.slider("Simulated aircraft", 3, 24, 8)
        s["seed"] = int(st.number_input("Random seed", 0, 9999, 7, help="Same seed + settings = identical run."))
        s["planner"] = st.selectbox("Planner", list(PLANNERS), format_func=PLANNER_LABEL.get)
        wind = st.slider("Wind speed (kt)", 0, 45, 12)
        gust = st.slider("Gusts (kt)", 0, 60, 18)
        wdir = st.slider("Wind direction (°, from)", 0, 359, 240)
        st.caption("Manual weather drives the synthetic scenario; some scenarios raise it (e.g. severe crosswind). "
                   "Live observations are shown separately.")
        if st.button("Refresh live weather", width="stretch"):
            with st.spinner("Fetching current weather…"):
                st.session_state.weather_result = fetch_weather(airport["latitude_deg"], airport["longitude_deg"])
                st.session_state.weather_airport = (airport["latitude_deg"], airport["longitude_deg"])
        use_live = st.checkbox("Use live wind/gusts as simulation inputs", value=False,
                               help="Uses the fetched weather as planner inputs. Not official aviation weather.")

        st.markdown("### Live aircraft overlay")
        radius = st.slider("Live aircraft search radius (degrees)", 0.05, 1.0, 0.30, 0.05, key="ops_live_radius")
        if st.button("↻ Fetch live flights for operations map", width="stretch"):
            with st.spinner("Fetching real aircraft observations…"):
                st.session_state.ops_live_result = fetch_opensky(
                    float(airport["latitude_deg"]), float(airport["longitude_deg"]), float(radius))
                st.session_state.ops_live_center = (float(airport["latitude_deg"]), float(airport["longitude_deg"]))
        st.caption("Real aircraft appear on the Operations map when fetched. Observed positions are real; "
                   "routes and runway outcomes remain simulated.")
        s["reset"] = st.button("↺ Reset scenario", width="stretch")
        st.divider()
        st.caption("SIMULATION ONLY · Not an operational ATC tool")

    key = (airport["latitude_deg"], airport["longitude_deg"])
    weather = st.session_state.get("weather_result") if st.session_state.get("weather_airport") == key else None
    s["weather"] = weather
    if use_live and weather and not weather.get("error"):
        cur = weather.get("current", {})
        # Open-Meteo reports km/h; the simulation works in knots.
        wind = max(0, min(45, round(float(cur.get("wind_speed_10m", wind)) * KT_PER_KMH)))
        gust = max(0, min(60, round(float(cur.get("wind_gusts_10m", gust)) * KT_PER_KMH)))
        wdir = int(cur.get("wind_direction_10m", wdir)) % 360
    s["wind"], s["gust"], s["wdir"] = wind, gust, wdir
    return s
