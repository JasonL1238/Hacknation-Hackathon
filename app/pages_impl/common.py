"""Shared rendering helpers used across pages (clickable list rows, chips)."""

from __future__ import annotations

import streamlit as st

from app.icons import icon
from app.services.schemas import Analysis, Case, CasePriority, Patient
from app.ui import components as C
from app.ui.shell import nav_to


def priority_badge(priority: str) -> str:
    m = {
        CasePriority.CRITICAL.value: ("Critical", "fail"),
        CasePriority.URGENT.value: ("Urgent", "nocall"),
        CasePriority.ROUTINE.value: ("Routine", "neutral"),
    }
    label, tone = m.get(priority, ("Routine", "neutral"))
    return C.badge(label, tone, small=True)


def patient_row(store, p: Patient, *, key: str) -> None:
    """A clickable patient row: avatar, name, MRN, demographics, latest case."""
    cases = store.list_cases(p.id)
    latest = cases[0] if cases else None
    analyses = store.list_analyses(patient_id=p.id)
    latest_a = analyses[0] if analyses else None

    c_main, c_case, c_status, c_act = st.columns([3.6, 3, 2.2, 1.5])
    with c_main:
        age = f"{p.age}y" if p.age is not None else "—"
        sex = p.sex or "—"
        st.markdown(
            f'<div style="display:flex;gap:11px;align-items:center">'
            f'<div class="gf-avatar">{C.initials(p.full_name)}</div>'
            f'<div><div class="gf-name">{C.esc(p.full_name)}</div>'
            f'<div class="gf-sub"><span class="gf-mono">{C.esc(p.mrn or "—")}</span> · {age} · {sex}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    with c_case:
        if latest:
            organism = latest.isolate.species if latest.isolate else "—"
            st.markdown(
                f'<div class="gf-name" style="font-size:.86rem">{C.esc(latest.title)}</div>'
                f'<div class="gf-sub"><em>{C.esc(organism)}</em></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="gf-sub">No cases yet</div>', unsafe_allow_html=True)
    with c_status:
        if latest_a:
            st.markdown(C.status_badge(latest_a.status, small=True)
                        + f'<div class="gf-sub" style="margin-top:3px">{C.relative_time(p.updated_at)}</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<div class="gf-sub">—</div>', unsafe_allow_html=True)
    with c_act:
        st.write("")
        if st.button("Open", key=key, use_container_width=True):
            nav_to("patient", patient_id=p.id)


def case_row(store, c: Case, *, key: str, show_patient: bool = True) -> None:
    p = store.get_patient(c.patient_id)
    latest_a = c.latest_analysis
    c_main, c_org, c_status, c_act = st.columns([3.6, 2.8, 2.4, 1.5])
    with c_main:
        who = f'<div class="gf-sub">{C.esc(p.full_name) if p else "—"}</div>' if show_patient else ""
        st.markdown(
            f'<div style="display:flex;gap:11px;align-items:center">'
            f'<div class="gf-avatar" style="color:var(--gf-info);background:var(--gf-info-soft);'
            f'border-color:var(--gf-info-border)">{icon("folder", 16)}</div>'
            f'<div><div class="gf-name" style="font-size:.9rem">{C.esc(c.title)}</div>{who}</div></div>',
            unsafe_allow_html=True,
        )
    with c_org:
        organism = c.isolate.species if c.isolate else "—"
        site = c.infection_site or "—"
        st.markdown(
            f'<div class="gf-sub"><em>{C.esc(organism)}</em></div>'
            f'<div class="gf-sub">{C.esc(site)}</div>',
            unsafe_allow_html=True,
        )
    with c_status:
        badge = C.status_badge(latest_a.status, small=True) if latest_a else C.badge("No analysis", "neutral", small=True)
        st.markdown(badge + " " + priority_badge(c.priority), unsafe_allow_html=True)
    with c_act:
        st.write("")
        if st.button("Open", key=key, use_container_width=True):
            nav_to("case", case_id=c.id)


def analysis_row(store, a: Analysis, *, key: str) -> None:
    p = store.get_patient(a.patient_id)
    case = store.case_of_analysis(a.id)
    counts = a.counts()
    c_main, c_counts, c_status, c_act = st.columns([3, 2.8, 2.2, 1.7])
    with c_main:
        fname = a.genome.filename if a.genome else "—"
        st.markdown(
            f'<div class="gf-name" style="font-size:.86rem"><span class="gf-mono">{C.esc(a.id)}</span></div>'
            f'<div class="gf-sub">{C.esc(p.full_name) if p else "—"} · '
            f'<span class="gf-mono">{C.esc(fname)}</span></div>',
            unsafe_allow_html=True,
        )
    with c_counts:
        if a.is_complete:
            st.markdown(
                C.badge(f'{counts["likely_to_fail"]} fail', "fail", "x-circle", small=True) + " "
                + C.badge(f'{counts["likely_to_work"]} work', "work", "check-circle", small=True) + " "
                + C.badge(f'{counts["no_call"]} no-call', "nocall", "minus-circle", small=True),
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="gf-sub">—</div>', unsafe_allow_html=True)
    with c_status:
        st.markdown(C.status_badge(a.status, small=True)
                    + f'<div class="gf-sub" style="margin-top:3px">{C.relative_time(a.created_at)}</div>',
                    unsafe_allow_html=True)
    with c_act:
        st.write("")
        label = "Report" if a.is_complete else "Open"
        target = "report" if a.is_complete else "analysis"
        if st.button(label, key=key, use_container_width=True):
            nav_to(target, analysis_id=a.id)


def list_header(cols_labels: list[tuple[str, float]]) -> None:
    """Render a lightweight column header line above rows."""
    cols = st.columns([w for _, w in cols_labels])
    for (label, _), col in zip(cols_labels, cols):
        col.markdown(f'<div class="gf-listhead" style="border:none;padding:2px 0">{C.esc(label)}</div>',
                     unsafe_allow_html=True)
