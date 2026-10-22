"""FoodShare Tracker (Streamlit). Start it with:  python run.py"""

import streamlit as st

from foodshare import domain as d
from foodshare.views import common as c
from foodshare.views import nav

st.set_page_config(page_title="FoodShare Tracker", page_icon="🥫", layout="wide")

from foodshare.services import run_maintenance
run_maintenance(c.store())
user = c.me()
c.write_cookie()  # keeps the sign-in across a browser refresh
page = st.navigation(nav.pages_for(user), expanded=True)
if st.session_state.pop("_go_home", False):
    st.switch_page(nav.page("welcome", default=True))

with st.sidebar:
    if user:
        st.markdown(f"**{c.esc(user['display_name'])}**  \n{d.ROLE_LABELS[user['role']]}")
        if st.button("Sign out", icon=":material/logout:", width="stretch"):
            c.sign_out()
            st.session_state["_go_home"] = True
            st.rerun()
    else:
        st.caption("Signed out. Donating and feedback need no account.")
    st.caption("FoodShare Tracker · FIT1056 Team04 prototype")

c.forget_snapshots_when_page_changes(page)
page.run()
