"""Settings — authenticated session, model, and data-handling posture."""

from __future__ import annotations

import streamlit as st

from app.icons import icon
from app.services.analysis_service import get_provider
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

    left, right = st.columns([1, 1])
    with left:
        C.panel_open("Profile & session", eyebrow="Account", icon_name="user")
        st.markdown(
            f'<div class="gf-meta"><div><div class="k">Name</div><div class="v">{C.esc(name)}</div></div>'
            f'<div><div class="k">Email</div><div class="v mono">{C.esc(user.get("email","—"))}</div></div>'
            f'<div><div class="k">Role</div><div class="v">Clinician</div></div>'
            f'</div>', unsafe_allow_html=True)
        st.write("")
        st.markdown(
            C.badge("Session-isolated", "work", "lock", small=True) + " "
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
        provider = get_provider()
        provider_label = {
            "local": "Local calibrated XGBoost",
            "api": "Remote model API",
            "mock": "Synthetic demo provider",
        }.get(provider.name, provider.name)
        st.markdown(
            f'<div class="gf-meta"><div><div class="k">Analysis provider</div>'
            f'<div class="v">{C.esc(provider_label)}</div></div>'
            f'<div><div class="k">Inference mode</div><div class="v">Synchronous, one genome</div></div>'
            f'</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="gf-sub" style="margin-top:8px">The deployed app runs the checked-in '
            'per-antibiotic XGBoost artifacts after AMRFinderPlus feature extraction. No model '
            'API key or separate inference server is required.</div>', unsafe_allow_html=True)
        C.panel_close()

    with right:
        C.panel_open("Data handling", eyebrow="Privacy", icon_name="shield-check")
        for text in [
            "This is a demonstration environment. Enter synthetic data only — never real "
            "protected health information.",
            "Patients, cases, results, and activity events exist only in this browser session; "
            "they are not written to Supabase or another database.",
            "Uploaded genome bytes and temporary AMRFinderPlus output are deleted immediately "
            "after inference succeeds or fails.",
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
            f'<div><div class="k">Access model</div><div class="v">Current session only</div></div>'
            f'</div>', unsafe_allow_html=True)
        st.markdown('<div class="gf-sub" style="margin-top:8px">Every case, isolate, upload, '
                    'and analysis is recorded in a temporary activity log tied to the patient and '
                    'case. It disappears when this Streamlit session ends.</div>',
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
