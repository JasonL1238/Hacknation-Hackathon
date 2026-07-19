"""Patient workspace — a complete per-patient profile with segmented tabs."""

from __future__ import annotations

import streamlit as st

from app.icons import icon
from app.ui import components as C
from app.ui.shell import nav_to, param
from app.pages_impl.common import case_row, analysis_row, list_header


def render(store, user) -> None:
    pid = param("patient_id")
    p = store.get_patient(pid) if pid else None
    if not p:
        C.page_header("Patient not found", icon_name="user")
        if st.button("← Back to patients"):
            nav_to("patients")
        return

    cases = store.list_cases(p.id)
    analyses = store.list_analyses(patient_id=p.id)

    C.page_header(
        p.full_name,
        icon_name="user",
        crumbs=[("Patients", None), (p.full_name, None)],
    )

    # Identity strip + primary action
    id_l, id_r = st.columns([4, 1.4])
    with id_l:
        age = f"{p.age}y" if p.age is not None else "—"
        st.markdown(
            f'<div class="gf-meta"><div><div class="k">MRN</div>'
            f'<div class="v mono">{C.esc(p.mrn or "—")}</div></div>'
            f'<div><div class="k">Age / Sex</div><div class="v">{age} · {C.esc(p.sex or "—")}</div></div>'
            f'<div><div class="k">Cases</div><div class="v gf-tnum">{len(cases)}</div></div>'
            f'<div><div class="k">Clinician</div><div class="v">{C.esc(p.clinician or "—")}</div></div>'
            f'<div><div class="k">Updated</div><div class="v">{C.relative_time(p.updated_at)}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with id_r:
        st.write("")
        if st.button("New case / analysis", type="primary", use_container_width=True,
                     icon=":material/add:"):
            st.session_state["wizard"] = {"step": 1, "patient_id": p.id}
            nav_to("new_analysis")

    st.write("")
    tabs = st.tabs(["Overview", "Cases", "Analyses", "Reports", "Activity"])

    # ── Overview ─────────────────────────────────────────────────────────────
    with tabs[0]:
        latest_case = cases[0] if cases else None
        latest_a = analyses[0] if analyses else None
        col1, col2 = st.columns([1.5, 1])
        with col1:
            C.panel_open("Active case", eyebrow="Clinical", icon_name="folder")
            if latest_case:
                organism = latest_case.isolate.species if latest_case.isolate else "—"
                st.markdown(
                    f'<div class="gf-name" style="font-size:1rem">{C.esc(latest_case.title)}</div>'
                    f'<div class="gf-sub">{C.esc(latest_case.infection_site or "—")} · '
                    f'<em>{C.esc(organism)}</em></div>',
                    unsafe_allow_html=True,
                )
                if latest_a:
                    st.write("")
                    counts = latest_a.counts()
                    if latest_a.is_complete:
                        st.markdown(
                            C.badge(f'{counts["likely_to_fail"]} likely to fail', "fail", "x-circle", small=True) + " "
                            + C.badge(f'{counts["likely_to_work"]} likely to work', "work", "check-circle", small=True) + " "
                            + C.badge(f'{counts["no_call"]} no-call', "nocall", "minus-circle", small=True),
                            unsafe_allow_html=True)
                    else:
                        st.markdown(C.status_badge(latest_a.status), unsafe_allow_html=True)
                    st.write("")
                    if st.button("Open latest analysis", key="pw_latest"):
                        nav_to("report" if latest_a.is_complete else "analysis",
                                analysis_id=latest_a.id)
            else:
                st.markdown('<div class="gf-sub">No cases yet.</div>', unsafe_allow_html=True)
            C.panel_close()
        with col2:
            C.panel_open("Uncertainty notices", eyebrow="Safety", icon_name="alert-triangle")
            notices = [a for a in analyses if a.status == "completed_with_no_call"]
            failed = [a for a in analyses if a.status == "failed"]
            if notices or failed:
                for a in notices:
                    st.markdown(C.badge("No-call heavy", "nocall", "minus-circle", small=True)
                                + f' <span class="gf-sub">{C.esc(a.id)}</span>', unsafe_allow_html=True)
                for a in failed:
                    st.markdown(C.badge("Failed", "fail", "alert-triangle", small=True)
                                + f' <span class="gf-sub">{C.esc(a.id)}</span>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="gf-sub">No open uncertainty notices.</div>',
                            unsafe_allow_html=True)
            C.panel_close()

        st.write("")
        C.panel_open("Recent activity", eyebrow="Audit", icon_name="history")
        events = [{"message": e["message"], "at": C.relative_time(e["at"]), "icon": "activity"}
                  for e in store.activity if e.get("patient_id") == p.id][:6]
        st.markdown(C.timeline(events) if events
                    else '<div class="gf-sub">No activity.</div>', unsafe_allow_html=True)
        C.panel_close()

    # ── Cases ────────────────────────────────────────────────────────────────
    with tabs[1]:
        if cases:
            C.panel_open()
            list_header([("Case", 4), ("Organism / site", 3), ("Status", 2.2), ("", 1.1)])
            st.markdown('<hr style="margin:2px 0 0"/>', unsafe_allow_html=True)
            for c in cases:
                case_row(store, c, key=f"pw_case_{c.id}", show_patient=False)
            C.panel_close()
        else:
            C.empty_state("No cases", "Create a case to attach an isolate and run an analysis.",
                          "folder")

    # ── Analyses ─────────────────────────────────────────────────────────────
    with tabs[2]:
        if analyses:
            C.panel_open()
            list_header([("Analysis", 3.4), ("Outcome", 3), ("Status", 2.2), ("", 1.2)])
            st.markdown('<hr style="margin:2px 0 0"/>', unsafe_allow_html=True)
            for a in analyses:
                analysis_row(store, a, key=f"pw_an_{a.id}")
            C.panel_close()
        else:
            C.empty_state("No analyses", "Submit a genome to generate the first report.", "cpu")

    # ── Reports ──────────────────────────────────────────────────────────────
    with tabs[3]:
        reports = [a for a in analyses if a.is_complete]
        if reports:
            C.panel_open()
            list_header([("Report", 3.4), ("Outcome", 3), ("Status", 2.2), ("", 1.2)])
            st.markdown('<hr style="margin:2px 0 0"/>', unsafe_allow_html=True)
            for a in reports:
                analysis_row(store, a, key=f"pw_rep_{a.id}")
            C.panel_close()
        else:
            C.empty_state("No completed reports", "Reports appear here once an analysis finishes.",
                          "file-text")

    # ── Activity ─────────────────────────────────────────────────────────────
    with tabs[4]:
        events = [{"message": e["message"], "at": C.relative_time(e["at"]), "icon": "activity"}
                  for e in store.activity if e.get("patient_id") == p.id]
        C.panel_open("Full activity log", eyebrow="Audit trail", icon_name="history")
        st.markdown(C.timeline(events) if events
                    else '<div class="gf-sub">No activity recorded.</div>', unsafe_allow_html=True)
        C.panel_close()
