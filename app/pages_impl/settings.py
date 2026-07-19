"""Settings — session, roles, data handling, and demo-environment posture."""

from __future__ import annotations

import os

import streamlit as st

from app.icons import icon
from app.ui import components as C


def render(store, user) -> None:
    C.page_header(
        "Settings",
        subtitle="Session, access, and data-handling posture for this workspace.",
        icon_name="settings",
        crumbs=[("System", None), ("Settings", None)],
    )

    meta = user.get("user_metadata", {})
    name = meta.get("full_name") or user.get("email", "Clinician")
    is_guest = user.get("is_guest")

    left, right = st.columns([1, 1])
    with left:
        C.panel_open("Profile & session", eyebrow="Account", icon_name="user")
        st.markdown(
            f'<div class="gf-meta"><div><div class="k">Name</div><div class="v">{C.esc(name)}</div></div>'
            f'<div><div class="k">Email</div><div class="v mono">{C.esc(user.get("email","—"))}</div></div>'
            f'<div><div class="k">Role</div><div class="v">{"Guest (demo)" if is_guest else "Clinician"}</div></div>'
            f'</div>', unsafe_allow_html=True)
        st.write("")
        st.markdown(
            C.badge("Row-level isolation", "work", "lock", small=True) + " "
            + C.badge("Session active", "info", "activity", small=True),
            unsafe_allow_html=True)
        st.write("")
        if st.button("Secure sign out", icon=":material/logout:"):
            from app.auth import sign_out
            sign_out()
            st.rerun()
        C.panel_close()
        st.write("")

        C.panel_open("Model integration", eyebrow="Configuration", icon_name="cpu")
        api_base = os.environ.get("GENOME_FIREWALL_API_BASE", "")
        st.markdown(
            f'<div class="gf-meta"><div><div class="k">Analysis provider</div>'
            f'<div class="v">{"Real API" if api_base else "Mock (demo)"}</div></div>'
            f'<div><div class="k">API base</div><div class="v mono">{C.esc(api_base or "not set")}</div></div>'
            f'</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="gf-sub" style="margin-top:8px">Set <span class="gf-mono">'
            'GENOME_FIREWALL_API_BASE</span> to route analyses to a real asynchronous '
            'backend — no UI changes required. The frontend already speaks the analysis '
            'service contract.</div>', unsafe_allow_html=True)
        C.panel_close()

    with right:
        C.panel_open("Data handling", eyebrow="Privacy", icon_name="shield-check")
        for text in [
            "This is a demonstration environment. Enter synthetic data only — never real "
            "protected health information.",
            "In a persistent deployment, patient data is single-tenant with row-level "
            "isolation and genome files live in a private, per-user bucket.",
            "No regulatory clearance or HIPAA compliance is claimed for this prototype.",
        ]:
            st.markdown(f'<div style="display:flex;gap:9px;padding:5px 0">'
                        f'<span style="color:var(--gf-info);flex:none">{icon("shield-check",15)}</span>'
                        f'<span class="gf-sub">{C.esc(text)}</span></div>', unsafe_allow_html=True)
        C.panel_close()
        st.write("")

        C.panel_open("Audit & access", eyebrow="Governance", icon_name="history")
        st.markdown(
            f'<div class="gf-meta"><div><div class="k">Activity events</div>'
            f'<div class="v gf-tnum">{len(store.activity)}</div></div>'
            f'<div><div class="k">Access model</div><div class="v">Owner-scoped</div></div>'
            f'</div>', unsafe_allow_html=True)
        st.markdown('<div class="gf-sub" style="margin-top:8px">Every case, isolate, upload, '
                    'and analysis is recorded in an activity log tied to the patient and case.</div>',
                    unsafe_allow_html=True)
        C.panel_close()
        st.write("")

        C.panel_open("Demo data", eyebrow="Workspace", icon_name="database")
        st.markdown('<div class="gf-sub">Reset the demonstration workspace to its seeded '
                    'synthetic patients and analyses.</div>', unsafe_allow_html=True)
        st.write("")
        if st.button("Reset demo workspace", icon=":material/restart_alt:"):
            st.session_state.pop("gf_store", None)
            st.session_state["_toast"] = "Demo workspace reset."
            st.rerun()
        C.panel_close()
