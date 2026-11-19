"""Application router for The Biotech Foundry simulators."""
import streamlit as st

st.set_page_config(page_title="The Biotech Foundry", layout="wide")

# Keep the legacy Batch_Reactor pathname while giving the root page a useful
# operator-facing label in the sidebar.
page = st.navigation([
    st.Page("pages/01_Tank_Transfer_Simulator.py", title="Tank Transfer Simulator", default=True),
    st.Page("pages/02_Batch_Reactor.py", title="Batch Reactor", url_path="Batch_Reactor"),
    st.Page("pages/03_Jacketed_Batch_Reactor.py", title="Jacketed Batch Reactor", url_path="Jacketed_Batch_Reactor"),
])
page.run()
