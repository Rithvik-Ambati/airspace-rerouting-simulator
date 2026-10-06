import streamlit as st

CSS = """
<style>
:root { --ink:#eaf1ff; --muted:#a7b6cf; --panel:#111c31; --line:#263652; }
.block-container {padding-top:1.25rem; padding-bottom:2rem; max-width:1600px;}
[data-testid="stAppViewContainer"] {background:linear-gradient(145deg,#07101f 0%,#0a1528 55%,#0b1a2e 100%);}
[data-testid="stHeader"] {background:rgba(0,0,0,0);}
h1,h2,h3,p,li,label {color:var(--ink);}
small,.muted {color:var(--muted);}
div[data-testid="stMetric"] {background:#111c31;border:1px solid #263652;padding:14px 16px;border-radius:14px;}
div[data-testid="stMetricLabel"] p {color:#a7b6cf;}
div[data-testid="stMetricValue"] {color:#f5f8ff;}
section[data-testid="stSidebar"] {background:#0b1527;border-right:1px solid #263652;}
div.stButton > button {border-radius:10px;border:1px solid #345078;}
.hero {padding:1.2rem 1.4rem;border:1px solid #263652;border-radius:18px;background:linear-gradient(110deg,#122641,#101a2e);margin-bottom:1rem;}
.pill {display:inline-block;border:1px solid #36557b;border-radius:999px;padding:4px 10px;color:#bcd4ff;font-size:12px;margin-right:6px;}
</style>
"""

HERO = """
<div class="hero">
  <span class="pill">TIME-EXPANDED MULTI-AGENT A*</span><span class="pill">SCENARIO-DRIVEN</span><span class="pill">LIVE AIRCRAFT CONNECTOR</span><span class="pill">54 SCENARIOS</span>
  <h1 style="margin:.6rem 0 .25rem 0;">Dynamic Flight Re-Routing</h1>
  <p style="margin:0;color:#a7b6cf;">Airport-selectable simulation · synthetic emergencies · live context · planner comparison</p>
</div>
"""


def apply():
    st.markdown(CSS, unsafe_allow_html=True)


def hero():
    st.markdown(HERO, unsafe_allow_html=True)
    st.warning("Research simulation only. Aircraft routes, emergencies, weather disruptions and runway assignments "
               "shown here are simulated. Never use this dashboard to direct real aircraft or replace certified ATC procedures.")
