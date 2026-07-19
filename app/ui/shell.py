"""
BioShield AI — application shell & router.

Provides the persistent desktop chrome (deep-navy sidebar nav rail + top bar
with global search / workspace / notifications / profile) and a lightweight
session-state router so every page renders inside one coherent shell.

Routing model:
  st.session_state["route"]        -> page key (e.g. "patients")
  st.session_state["route_params"] -> dict of params (e.g. {"patient_id": ...})

Call `nav_to(route, **params)` to navigate (sets state + reruns).
"""

from __future__ import annotations

import streamlit as st

from app.icons import icon

# Sidebar sections: (route_key, label, material_icon, section_group)
NAV = [
    ("overview", "Overview", ":material/space_dashboard:", "Workspace"),
    ("patients", "Patients", ":material/groups:", "Workspace"),
    ("cases", "Cases", ":material/folder_open:", "Workspace"),
    ("new_analysis", "New Analysis", ":material/note_add:", "Analysis"),
    ("queue", "Analysis Queue", ":material/lab_profile:", "Analysis"),
    ("reports", "Reports", ":material/description:", "Analysis"),
    ("model", "Model Information", ":material/neurology:", "System"),
    ("settings", "Settings", ":material/settings:", "System"),
]

# Sub-routes that highlight a parent nav item.
_PARENT = {
    "patient": "patients",
    "case": "cases",
    "analysis": "queue",
    "report": "reports",
}

_SHELL_CSS = r"""
<style>
/* Sidebar brand */
.gf-brandmark { display:flex; align-items:center; gap:11px; padding:4px 8px 14px; }
.gf-brandmark .m { width:36px; height:36px; border-radius:10px; display:grid; place-items:center;
  color:#fff; background:linear-gradient(150deg,var(--gf-brand-2),var(--gf-brand-3));
  box-shadow:0 4px 14px rgba(37,99,235,.4); flex:none; }
.gf-brandmark .t { line-height:1.1; }
.gf-brandmark .t b { color:#fff; font-size:1.02rem; font-weight:700; letter-spacing:-.01em; display:block; }
.gf-brandmark .t span { color:var(--gf-nav-muted); font-size:.68rem; font-weight:600; letter-spacing:.06em; text-transform:uppercase; }
.gf-navgroup { color:var(--gf-nav-muted) !important; font-size:.66rem !important; font-weight:700 !important;
  letter-spacing:.09em; text-transform:uppercase; padding:14px 11px 4px; margin:0; }
.gf-userbox { display:flex; align-items:center; gap:10px; padding:10px; border-radius:var(--gf-r);
  background:var(--gf-nav-2); border:1px solid var(--gf-nav-line); margin-top:6px; }
.gf-userbox .av { width:32px; height:32px; border-radius:8px; flex:none; display:grid; place-items:center;
  font-weight:700; font-size:.78rem; color:#fff; background:linear-gradient(150deg,#334155,#1e293b); border:1px solid #33415577; }
.gf-userbox .nm { color:#fff !important; font-size:.85rem; font-weight:600; line-height:1.15; }
.gf-userbox .rl { color:var(--gf-nav-muted) !important; font-size:.72rem; }

/* Top bar */
.gf-topbar-wrap { position:sticky; top:0; z-index:50; margin:-28px -40px 20px; padding:11px 40px;
  background:rgba(255,255,255,.86); backdrop-filter:saturate(1.4) blur(10px);
  border-bottom:1px solid var(--gf-border); }
.gf-tb-ws { display:flex; align-items:center; gap:9px; font-size:.84rem; color:var(--gf-ink-2); font-weight:600; }
.gf-tb-ws .dot { width:8px; height:8px; border-radius:99px; background:var(--gf-work-2); box-shadow:0 0 0 3px var(--gf-work-soft); }
.gf-tb-ws .env { font-size:.66rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
  color:var(--gf-nocall); background:var(--gf-nocall-soft); border:1px solid var(--gf-nocall-border);
  border-radius:99px; padding:2px 8px; }
.gf-iconbtn { position:relative; display:inline-grid; place-items:center; }
.gf-badge-dot { position:absolute; top:-2px; right:-2px; width:8px; height:8px; border-radius:99px;
  background:var(--gf-fail-2); border:2px solid #fff; }

/* Make the topbar search input compact */
.gf-topbar-wrap [data-testid="stTextInput"] input { padding:8px 12px !important; font-size:.88rem !important;
  background:var(--gf-surface-2) !important; }
.gf-topbar-wrap .stButton > button { padding:6px 10px; box-shadow:none; }
@media (max-width:1000px) { .gf-topbar-wrap { margin:-20px -18px 16px; padding:10px 18px; } }
</style>
"""


# ── router ───────────────────────────────────────────────────────────────────
def current_route() -> str:
    return st.session_state.get("route", "overview")


def param(key: str, default=None):
    return st.session_state.get("route_params", {}).get(key, default)


def nav_to(route: str, **params) -> None:
    st.session_state["route"] = route
    st.session_state["route_params"] = params
    st.rerun()


def _nav_button(route_key: str, label: str, material_icon: str) -> None:
    active_parent = _PARENT.get(current_route(), current_route())
    is_active = active_parent == route_key
    clicked = st.button(
        label, key=f"nav_{route_key}", icon=material_icon,
        type="primary" if is_active else "secondary",
        use_container_width=True,
    )
    if clicked and not is_active:
        nav_to(route_key)


def render_sidebar(user: dict) -> None:
    st.markdown(_SHELL_CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown(
            f'<div class="gf-brandmark"><div class="m">{icon("shield-check", 20)}</div>'
            f'<div class="t"><b>BioShield AI</b><span>Clinical AMR Intelligence</span></div></div>',
            unsafe_allow_html=True,
        )

        last_group = None
        for route_key, label, icon_name, group in NAV:
            if group != last_group:
                st.markdown(f'<p class="gf-navgroup">{group}</p>', unsafe_allow_html=True)
                last_group = group
            _nav_button(route_key, label, icon_name)

        st.markdown('<div style="flex:1"></div>', unsafe_allow_html=True)
        st.markdown("<hr/>", unsafe_allow_html=True)

        meta = user.get("user_metadata", {})
        name = meta.get("full_name") or user.get("email", "Clinician")
        from app.ui.components import initials
        st.markdown(
            f'<div class="gf-userbox"><div class="av">{initials(name)}</div>'
            f'<div><div class="nm">{name}</div><div class="rl">Clinician</div></div></div>',
            unsafe_allow_html=True,
        )
        if st.button("Sign out", key="btn_signout", use_container_width=True,
                     icon=":material/logout:"):
            from app.auth import sign_out
            sign_out()
            st.session_state.pop("route", None)
            st.rerun()


def render_topbar(user: dict, store) -> None:
    st.markdown('<div class="gf-topbar-wrap">', unsafe_allow_html=True)
    # The New Analysis shortcut is shown on every tab except Settings.
    show_new = current_route() != "settings"
    if show_new:
        c_search, c_ws, c_new, c_notif, c_help = st.columns([6, 3, 2.4, 0.9, 0.9])
    else:
        c_search, c_ws, c_notif, c_help = st.columns([6, 5.4, 0.9, 0.9])
        c_new = None

    with c_search:
        q = st.text_input(
            "search", key="global_search", label_visibility="collapsed",
            placeholder="Search patients, MRN, case, or analysis ID…",
        )
        if q and q != st.session_state.get("_last_search"):
            st.session_state["_last_search"] = q
            nav_to("patients", q=q)

    with c_ws:
        st.markdown(
            '<div class="gf-tb-ws" style="justify-content:flex-end;padding-top:7px">'
            '<span class="dot"></span> Demo General Hospital '
            '<span class="env">Demo env</span></div>',
            unsafe_allow_html=True,
        )

    if c_new is not None:
        with c_new:
            if st.button("New Analysis", key="tb_new", type="primary",
                         use_container_width=True, icon=":material/add:"):
                nav_to("new_analysis")

    unread = sum(1 for n in store.notifications if n.get("unread"))
    with c_notif:
        bell = ":material/notifications_unread:" if unread else ":material/notifications:"
        if st.button("", key="tb_notif", use_container_width=True,
                     icon=bell, help=f"{unread} notification(s) — open the queue"):
            nav_to("queue")

    with c_help:
        if st.button("", key="tb_help", use_container_width=True,
                     icon=":material/help:", help="Help & model information"):
            nav_to("model")

    st.markdown("</div>", unsafe_allow_html=True)
