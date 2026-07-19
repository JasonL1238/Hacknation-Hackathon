"""
BioShield AI — clinical AMR decision-support platform (Streamlit).

Entry point: page config → design system → auth gate → application shell →
session-state router that dispatches to the page modules in app/pages_impl.

The analysis pipeline reaches the UI only through app/services/analysis_service
(a swappable provider), so a real asynchronous model backend can replace the
mock without touching any page.

IMPORTANT: Research prototype — every result must be confirmed by standard
laboratory testing. Decision support only; a trained professional decides. This
tool predicts and explains resistance that already exists in a sequenced genome —
it never designs, modifies, or optimizes any organism.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# ─── path setup (keep src/ importable for the real pipeline) ─────────────────
ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


# ─── secrets → environment ───────────────────────────────────────────────────
# Streamlit does not automatically expose secrets.toml (or a .env) as environment
# variables, so os.environ-based config such as OPENAI_API_KEY wouldn't be seen.
# Bridge them here, once, regardless of the launch working directory.
def _bridge_secrets_to_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    try:
        for _k, _v in st.secrets.items():
            if isinstance(_v, str):
                os.environ.setdefault(_k, _v)
    except Exception:
        pass


_bridge_secrets_to_env()

st.set_page_config(
    page_title="BioShield AI — Clinical AMR Intelligence",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

from app.ui.theme import inject as inject_theme  # noqa: E402
from app.auth import (  # noqa: E402
    is_authenticated, handle_oauth_code, render_login_page, get_current_user,
)

inject_theme()

# ─── OAuth redirect handling (?code=…) ───────────────────────────────────────
_params = st.query_params
if "code" in _params and not is_authenticated():
    ok, msg = handle_oauth_code(_params["code"])
    if ok:
        st.query_params.clear()
        st.rerun()
    else:
        st.error(f"Sign-in failed: {msg}")

# ─── demo deep-link (?demo=1 enters the synthetic demo workspace) ────────────
if "demo" in _params and not is_authenticated():
    from app.auth import enter_guest_mode
    enter_guest_mode()
    _goto = _params.get("goto")
    st.query_params.clear()
    if _goto:
        st.session_state["_pending_goto"] = _goto
    st.rerun()

# ─── auth gate ────────────────────────────────────────────────────────────────
if not is_authenticated():
    render_login_page()
    st.stop()

user = get_current_user()

# ─── shell + store ────────────────────────────────────────────────────────────
from app.services.store import get_store  # noqa: E402
from app.ui.shell import render_sidebar, render_topbar, current_route  # noqa: E402

store = get_store()

# default landing route
if "route" not in st.session_state:
    st.session_state["route"] = "overview"

# Resolve a pending demo deep-link now that the store exists. Special targets
# (report/processing/patient/case) resolve against seeded records; anything else
# is treated as a plain top-level route.
_pending = st.session_state.pop("_pending_goto", None)
if _pending:
    _analyses = store.list_analyses()
    if _pending == "report":
        _hit = next((a for a in _analyses if a.is_complete), None)
        if _hit:
            st.session_state["route"] = "report"
            st.session_state["route_params"] = {"analysis_id": _hit.id}
    elif _pending == "processing":
        _hit = next((a for a in _analyses if a.status == "processing"), None)
        if _hit:
            st.session_state["route"] = "analysis"
            st.session_state["route_params"] = {"analysis_id": _hit.id}
    elif _pending == "patient":
        _ps = store.list_patients()
        if _ps:
            st.session_state["route"] = "patient"
            st.session_state["route_params"] = {"patient_id": _ps[0].id}
    elif _pending == "case":
        _cs = store.list_cases()
        if _cs:
            st.session_state["route"] = "case"
            st.session_state["route_params"] = {"case_id": _cs[0].id}
    else:
        st.session_state["route"] = _pending

render_sidebar(user)
render_topbar(user, store)

# queued toast (set by a page before nav_to)
_toast = st.session_state.pop("_toast", None)
if _toast:
    st.toast(_toast, icon=":material/check_circle:")

# ─── router dispatch ──────────────────────────────────────────────────────────
from app.pages_impl import (  # noqa: E402
    overview, patients, patient_workspace, new_analysis, queue as queue_page,
    cases as cases_page, analysis_view, report_view, reports, model_info, settings,
)

route = current_route()

if route == "overview":
    overview.render(store, user)
elif route == "patients":
    patients.render(store, user)
elif route == "patient":
    patient_workspace.render(store, user)
elif route == "cases":
    cases_page.render_list(store, user)
elif route == "case":
    cases_page.render_detail(store, user)
elif route == "new_analysis":
    new_analysis.render(store, user)
elif route == "queue":
    queue_page.render(store, user)
elif route == "analysis":
    analysis_view.render(store, user)
elif route == "report":
    report_view.render(store, user)
elif route == "reports":
    reports.render(store, user)
elif route == "model":
    model_info.render(store, user)
elif route == "settings":
    settings.render(store, user)
else:
    overview.render(store, user)
