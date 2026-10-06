"""AeroRescue dashboard entry point. UI lives in the dashboard/ package, logic in simulator/."""
import streamlit as st

from dashboard import live, overview, sidebar, static_tabs, style
from simulator.engine import SimulationEngine

st.set_page_config(page_title="AeroRescue | Airspace Simulator", page_icon="✈️", layout="wide")
style.apply()
sidebar.init_state()
settings = sidebar.render()
selected, airport = settings["scenario"], settings["airport"]
center = (airport["latitude_deg"], airport["longitude_deg"])

if settings["reset"]:
    st.session_state.last_run = None
    st.session_state.pop("benchmark", None)
    st.rerun()


@st.cache_data(show_spinner=False)
def simulate(scenario_id, aircraft, wind, gust, wdir, seed, planner, center):
    """Pure function of its inputs, so identical settings never recompute."""
    return SimulationEngine().run(scenario_id, aircraft, wind, gust, wdir, seed=seed, planner=planner, center=center)


# Results are recomputed (or served from cache) whenever any input changes.
result = simulate(selected["id"], settings["aircraft_count"], settings["wind"], settings["gust"], settings["wdir"],
                  settings["seed"], settings["planner"], center)

style.hero()
overview.render_weather(settings["weather"])
tab_overview, tab_scenarios, tab_live, tab_engine, tab_eval = st.tabs(
    ["🌐 Operations view", "🧩 Scenario library", "📡 Live aircraft data", "🧠 Planning engine", "📊 Evaluation"])
with tab_overview:
    overview.render(result, selected, settings)
with tab_scenarios:
    static_tabs.render_library()
with tab_live:
    live.render(airport)
with tab_engine:
    static_tabs.render_engine()
with tab_eval:
    static_tabs.render_evaluation(selected, settings)
