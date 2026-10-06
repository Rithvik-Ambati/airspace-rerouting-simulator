"""Scenario library, planning-engine description and evaluation tabs."""
import json

import pandas as pd
import streamlit as st

from simulator.benchmark import run_benchmark, summarize_benchmark
from simulator.scenarios import SCENARIOS, catalogue_with_effects


def render_library():
    st.subheader("Scenario library")
    st.write("49 individual scenarios and five compound demonstrations. Each one carries machine-readable effects "
             "(hazards, emergencies, runway state, data quality) that the engine executes.")
    query = st.text_input("Search scenarios", placeholder="Try MAYDAY, runway closure, stale data…")
    q = query.lower()
    filtered = [s for s in SCENARIOS if q in (s["title"] + " " + s["description"] + " " + s["category"]).lower()]
    st.caption(f"{len(filtered)} scenarios shown")
    for start in range(0, len(filtered), 3):
        for col, scenario in zip(st.columns(3), filtered[start:start + 3]):
            with col, st.container(border=True):
                st.markdown(f"**{scenario['id']:02d} · {scenario['title']}**")
                st.caption(scenario["category"])
                st.write(scenario["description"])
                st.caption("Event tags: " + ", ".join(scenario["tags"][:3]))
    st.download_button("⬇ Export scenario catalogue with effects (JSON)",
                       json.dumps(catalogue_with_effects(), indent=2), "scenario_catalogue.json", "application/json")


def render_engine():
    st.subheader("Planning engine")
    st.markdown("""
**Pipeline**
1. Build a fleet from the scenario: arrivals (to the primary airport) and overflights (edge to edge), types, endurance, data quality.
2. Plan every aircraft with **time-expanded A\\*** over (cell, minute): 8 moves plus *hold*, closed sectors, wind-dependent cost.
3. Reserve each plan in a space-time table (same-cell and swap conflicts) and a runway-slot book (capacity, occupancy time).
4. **Emergencies are planned first** (priority planner), then by remaining endurance.
5. When something changes mid-run (restriction announced, emergency declared/escalated/cleared, runway closes) the
   engine **replans from every aircraft's current position**. Plans that are still legal are kept (damping), so routes do not flap.
6. An aircraft that cannot land at the primary airport (closed, no runway slot, runway too short, crosswind over its limit, no
   emergency services) is offered the alternate airport; if that fails too it is reported as not flyable instead of being given an invented route.

**Modelled constraints:** closed/moving sectors, runway count and closure, runway length per type, crosswind limits per type,
fuel endurance, overweight landing hold, stale/uncertain positions (widened footprint), missing identity.

**Not modelled:** real airspace geometry, altitude, speed differences between types, separation minima beyond cell exclusivity,
real aircraft performance, ATC procedures. One grid cell = 8 km, one step = 1 minute.
""")
    st.code("python -m simulator.cli --scenario 50 --aircraft 8 --planner priority", language="bash")


def render_evaluation(selected, settings):
    st.subheader("Research evaluation")
    st.write("Compares three planners on **identical seeded fleets** and scores them with the same post-hoc conflict check. "
             "Independent A* ignores other aircraft and runway capacity, so its conflict count shows what coordination buys.")
    seeds = st.slider("Seeds", 3, 30, 10)
    if st.button("Run planner comparison"):
        with st.spinner("Running benchmark…"):
            st.session_state.benchmark = run_benchmark(selected["id"], settings["aircraft_count"], settings["wind"],
                                                       settings["gust"], settings["wdir"], seeds=seeds)
            st.session_state.benchmark_meta = f"Scenario {selected['id']} · {selected['title']} · {settings['aircraft_count']} aircraft"
    rows = st.session_state.get("benchmark")
    if not rows:
        st.markdown("- Conflicts, infeasible aircraft, delay and extra distance per planner\n"
                    "- Emergency delay and unserved emergencies\n- Mean ± 95% interval over seeds")
        return
    st.caption(st.session_state.get("benchmark_meta", ""))
    st.markdown("**Mean ± 95% interval across seeds**")
    st.dataframe(pd.DataFrame(summarize_benchmark(rows)), width="stretch", hide_index=True)
    with st.expander("Per-seed rows"):
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch", hide_index=True)
    st.download_button("Download benchmark CSV", pd.DataFrame(rows).to_csv(index=False), "benchmark_results.csv", "text/csv")
    st.caption("Synthetic benchmark. Results describe this model's behaviour, not real-world aviation safety.")
