"""New Analysis — guided clinical submission stepper.

Steps: Patient → Clinical context → Specimen & isolate → Genome upload →
Review → Submit. State lives in st.session_state["wizard"] so a draft survives
reruns and the user can move back and forth without losing input.
"""

from __future__ import annotations

import streamlit as st

from app.icons import icon
from app.services.analysis_service import get_provider
from app.services.schemas import (
    Case, CasePriority, GenomeSubmission, Isolate, QcStatus,
)
from app.ui import components as C
from app.ui.shell import nav_to
from app.pages_impl.patients import create_patient_dialog

STEPS = ["Patient", "Clinical context", "Specimen & isolate", "Genome upload",
         "Review", "Analysis"]

_WIZ_CSS = r"""
<style>
.gf-stepper { display:flex; align-items:center; gap:0; margin:2px 0 20px; overflow-x:auto; }
.gf-stepper .st { display:flex; align-items:center; gap:9px; flex:none; }
.gf-stepper .num { width:26px; height:26px; border-radius:99px; display:grid; place-items:center;
  font-size:.8rem; font-weight:700; border:2px solid var(--gf-border-strong); color:var(--gf-faint);
  background:var(--gf-surface); flex:none; }
.gf-stepper .lb { font-size:.85rem; font-weight:600; color:var(--gf-faint); white-space:nowrap; }
.gf-stepper .st.done .num { background:var(--gf-work); border-color:var(--gf-work); color:#fff; }
.gf-stepper .st.done .lb { color:var(--gf-ink-2); }
.gf-stepper .st.active .num { border-color:var(--gf-brand-2); color:var(--gf-brand-2); box-shadow:0 0 0 4px var(--gf-brand-soft); }
.gf-stepper .st.active .lb { color:var(--gf-brand); }
.gf-stepper .bar { flex:1; min-width:22px; height:2px; background:var(--gf-border); margin:0 12px; }
.gf-stepper .bar.done { background:var(--gf-work-border); }
</style>
"""


def _wiz() -> dict:
    return st.session_state.setdefault("wizard", {"step": 1})


def _stepper(cur: int) -> None:
    st.markdown(_WIZ_CSS, unsafe_allow_html=True)
    out = ['<div class="gf-stepper">']
    for i, label in enumerate(STEPS, 1):
        state = "done" if i < cur else ("active" if i == cur else "")
        glyph = icon("check", 13) if i < cur else str(i)
        out.append(f'<div class="st {state}"><div class="num">{glyph}</div>'
                   f'<div class="lb">{C.esc(label)}</div></div>')
        if i < len(STEPS):
            out.append(f'<div class="bar {"done" if i < cur else ""}"></div>')
    out.append("</div>")
    st.markdown("".join(out), unsafe_allow_html=True)


def _nav(cur: int, *, can_next: bool = True, next_label: str = "Continue",
         on_next=None) -> None:
    st.write("")
    b1, spacer, b2 = st.columns([1.2, 3, 1.4])
    with b1:
        if cur > 1 and st.button("Back", use_container_width=True,
                                 icon=":material/arrow_back:"):
            _wiz()["step"] = cur - 1
            st.rerun()
    with b2:
        if st.button(next_label, type="primary", use_container_width=True,
                     disabled=not can_next, icon=":material/arrow_forward:"):
            if on_next:
                on_next()
            _wiz()["step"] = cur + 1
            st.rerun()


def render(store, user) -> None:
    w = _wiz()
    cur = w.get("step", 1)

    C.page_header(
        "New analysis",
        subtitle="A controlled clinical submission. Species identification and genome "
                 "reconstruction are performed outside Genome Firewall — this begins after QC.",
        icon_name="plus-square",
        crumbs=[("Analysis", None), ("New analysis", None)],
    )
    _stepper(cur)

    if cur == 1:
        _step_patient(store, w)
    elif cur == 2:
        _step_context(store, w)
    elif cur == 3:
        _step_specimen(store, w)
    elif cur == 4:
        _step_genome(store, w)
    elif cur == 5:
        _step_review(store, w)
    else:
        _step_submit(store, w)


# ── Step 1: Patient ──────────────────────────────────────────────────────────
def _step_patient(store, w) -> None:
    C.panel_open("Select patient", eyebrow="Step 1 of 6", icon_name="user")
    patients = store.list_patients()
    q = st.text_input("Search patients", placeholder="Name or MRN…")
    matches = [p for p in patients
               if not q or q.lower() in (p.full_name + " " + (p.mrn or "")).lower()]

    if w.get("patient_id"):
        sel = store.get_patient(w["patient_id"])
        if sel:
            st.markdown(
                f'<div style="display:flex;gap:11px;align-items:center;padding:10px 12px;'
                f'background:var(--gf-brand-soft);border:1px solid var(--gf-brand-border);'
                f'border-radius:var(--gf-r)"><div class="gf-avatar">{C.initials(sel.full_name)}</div>'
                f'<div><div class="gf-name">{C.esc(sel.full_name)}</div>'
                f'<div class="gf-sub">Selected · <span class="gf-mono">{C.esc(sel.mrn or "—")}</span></div></div></div>',
                unsafe_allow_html=True)

    st.markdown('<div class="gf-sub" style="margin-top:8px">Choose an existing patient:</div>',
                unsafe_allow_html=True)
    options = {f"{p.full_name} · {p.mrn or p.id}": p.id for p in matches[:30]}
    if options:
        choice = st.radio("patients_radio", list(options.keys()),
                          label_visibility="collapsed",
                          index=None)
        if choice:
            w["patient_id"] = options[choice]
    else:
        st.markdown('<div class="gf-sub">No matches.</div>', unsafe_allow_html=True)

    st.write("")
    if st.button("＋ Create a new patient", icon=":material/person_add:"):
        create_patient_dialog(store, on_created_go_case=True)

    C.panel_close()
    _nav(1, can_next=bool(w.get("patient_id")))


# ── Step 2: Clinical context ───────────────────────────────────────────────
def _step_context(store, w) -> None:
    C.panel_open("Clinical context", eyebrow="Step 2 of 6", icon_name="clipboard-list")
    st.caption("These fields document the episode. They are not consumed by the model "
               "unless explicitly stated on the Model Information page.")
    ctx = w.setdefault("context", {})
    ctx["title"] = st.text_input("Case title *", value=ctx.get("title", ""),
                                 placeholder="e.g. MRSA bloodstream infection")
    c1, c2 = st.columns(2)
    ctx["encounter_date"] = c1.date_input("Encounter date", value=None,
                                          format="YYYY-MM-DD")
    ctx["priority"] = c2.selectbox("Case priority",
                                   [CasePriority.ROUTINE.value, CasePriority.URGENT.value,
                                    CasePriority.CRITICAL.value],
                                   format_func=lambda x: x.capitalize(),
                                   index=[CasePriority.ROUTINE.value, CasePriority.URGENT.value,
                                          CasePriority.CRITICAL.value].index(
                                              ctx.get("priority", CasePriority.ROUTINE.value)))
    c3, c4 = st.columns(2)
    ctx["site"] = c3.text_input("Suspected infection site", value=ctx.get("site", ""),
                                placeholder="e.g. Bloodstream")
    ctx["syndrome"] = c4.text_input("Clinical syndrome", value=ctx.get("syndrome", ""),
                                    placeholder="e.g. Bacteremia")
    ctx["exposure"] = st.text_input("Current / recent antibiotic exposure (optional)",
                                    value=ctx.get("exposure", ""))
    ctx["notes"] = st.text_area("Relevant notes (optional)", value=ctx.get("notes", ""),
                                height=80)
    C.panel_close()
    _nav(2, can_next=bool(ctx.get("title", "").strip()))


# ── Step 3: Specimen & isolate ───────────────────────────────────────────────
def _step_specimen(store, w) -> None:
    C.panel_open("Specimen & isolate", eyebrow="Step 3 of 6", icon_name="microscope")
    st.markdown(
        '<div class="gf-safety" style="margin-bottom:12px"><span class="ico">'
        + icon("info", 16) +
        '</span><div><b>Species identification and genome reconstruction occur outside '
        'Genome Firewall.</b> Enter the species from confirmed laboratory identification — '
        'the model does not identify organisms from raw samples.</div></div>',
        unsafe_allow_html=True)
    iso = w.setdefault("isolate", {})
    c1, c2 = st.columns(2)
    iso["specimen_type"] = c1.text_input("Specimen type", value=iso.get("specimen_type", ""),
                                         placeholder="e.g. Blood culture")
    iso["specimen_date"] = c2.date_input("Specimen collection date", value=None,
                                         format="YYYY-MM-DD")
    c3, c4 = st.columns(2)
    iso["lab_id"] = c3.text_input("Laboratory identifier", value=iso.get("lab_id", ""),
                                  placeholder="LAB-0000")
    iso["culture_source"] = c4.text_input("Culture source", value=iso.get("culture_source", ""))
    c5, c6 = st.columns(2)
    iso["species"] = c5.selectbox("Confirmed bacterial species",
                                  ["Staphylococcus aureus", "Other (out of scope)"],
                                  index=0,
                                  help="From confirmed laboratory identification.")
    iso["gram_stain"] = c6.selectbox("Gram-stain classification",
                                     ["Gram-positive", "Gram-negative", "Indeterminate"],
                                     index=0)
    c7, c8 = st.columns(2)
    iso["assembly_id"] = c7.text_input("Genome assembly identifier",
                                       value=iso.get("assembly_id", ""), placeholder="ASM-…")
    iso["platform"] = c8.text_input("Sequencing platform", value=iso.get("platform", ""),
                                    placeholder="e.g. Illumina NovaSeq")
    iso["assembly_quality"] = st.selectbox("Assembly quality status",
                                           ["Passed QC (external)", "Passed with warnings (external)",
                                            "Failed QC (external)"], index=0)
    iso["lab_notes"] = st.text_area("Laboratory notes (optional)",
                                    value=iso.get("lab_notes", ""), height=70)

    if iso.get("species") == "Other (out of scope)":
        st.warning("This model covers *Staphylococcus aureus* only. Other species are "
                   "out of scope and will not be analyzed.")
    C.panel_close()
    _nav(3, can_next=(iso.get("species") == "Staphylococcus aureus"))


# ── Step 4: Genome upload ───────────────────────────────────────────────────
def _step_genome(store, w) -> None:
    C.panel_open("Genome upload", eyebrow="Step 4 of 6", icon_name="upload-cloud")
    st.caption("Upload a reconstructed, quality-checked assembly (FASTA: .fasta / .fna / .fa). "
               "Genome Firewall never reads DNA from a patient sample — only an assembled file.")

    up = st.file_uploader("Genome FASTA", type=["fasta", "fna", "fa", "txt"],
                          label_visibility="collapsed")
    prov = get_provider()

    if up is not None:
        data = up.getvalue()
        # Validate through the service seam (real lightweight parsing).
        if w.get("_genome_name") != up.name:
            tmp = prov.create_analysis(patient_id="", case_id="", isolate_id="",
                                       species="Staphylococcus aureus",
                                       model_version="genome-firewall-v0.1")
            sub = prov.validate_genome(tmp, filename=up.name, data=data)
            w["genome"] = {
                "filename": sub.filename, "size_bytes": sub.size_bytes,
                "checksum": sub.checksum, "sequence_count": sub.sequence_count,
                "total_length_bp": sub.total_length_bp, "n50": sub.n50,
                "gc_content": sub.gc_content, "qc_status": sub.qc_status,
                "qc_warnings": sub.qc_warnings,
            }
            w["_genome_name"] = up.name

    g = w.get("genome")
    if g:
        _render_genome_summary(g)
    else:
        st.markdown('<div class="gf-sub" style="margin-top:8px">Waiting for a file. You can '
                    'also continue without one only after a valid upload.</div>',
                    unsafe_allow_html=True)

    C.panel_close()
    can_next = bool(g and g["qc_status"] != QcStatus.FAILED.value)
    _nav(4, can_next=can_next)


def _render_genome_summary(g: dict) -> None:
    st.write("")
    st.markdown(
        f'<div class="gf-meta"><div><div class="k">File</div>'
        f'<div class="v mono">{C.esc(g["filename"])}</div></div>'
        f'<div><div class="k">Size</div><div class="v gf-tnum">{g["size_bytes"]/1e6:.2f} MB</div></div>'
        f'<div><div class="k">Submission ID</div><div class="v mono">{C.esc(g["checksum"])}</div></div>'
        f'</div>', unsafe_allow_html=True)
    st.write("")
    qc = g["qc_status"]
    st.markdown(C.qc_badge(qc), unsafe_allow_html=True)
    st.write("")
    if qc == QcStatus.FAILED.value:
        st.error("**Validation failed.** " + " ".join(g["qc_warnings"])
                 + " Re-upload a corrected FASTA assembly.")
        return
    st.markdown(
        f'<div class="gf-meta"><div><div class="k">Sequences (contigs)</div>'
        f'<div class="v gf-tnum">{g["sequence_count"]:,}</div></div>'
        f'<div><div class="k">Total length</div><div class="v gf-tnum">{g["total_length_bp"]:,} bp</div></div>'
        f'<div><div class="k">N50</div><div class="v gf-tnum">{g["n50"]:,} bp</div></div>'
        f'<div><div class="k">GC content</div><div class="v gf-tnum">{g["gc_content"]*100:.1f}%</div></div>'
        f'</div>', unsafe_allow_html=True)
    if g["qc_warnings"]:
        st.write("")
        for wmsg in g["qc_warnings"]:
            st.warning(wmsg)
    else:
        st.success("Format validated — the assembly is within expected parameters for S. aureus.")


# ── Step 5: Review ───────────────────────────────────────────────────────────
def _step_review(store, w) -> None:
    p = store.get_patient(w.get("patient_id"))
    ctx = w.get("context", {})
    iso = w.get("isolate", {})
    g = w.get("genome", {})
    from app.services.analysis_service import _DRUGS

    C.panel_open("Review submission", eyebrow="Step 5 of 6", icon_name="eye")
    grid = st.columns(2)
    with grid[0]:
        _review_block("Patient", [
            ("Name", p.full_name if p else "—"),
            ("MRN", p.mrn if p and p.mrn else "—"),
            ("Case", ctx.get("title", "—")),
            ("Priority", ctx.get("priority", "routine").capitalize()),
            ("Site / syndrome", f'{ctx.get("site","—")} · {ctx.get("syndrome","—")}'),
        ])
        _review_block("Specimen & isolate", [
            ("Species", iso.get("species", "—")),
            ("Specimen", iso.get("specimen_type", "—")),
            ("Lab ID", iso.get("lab_id", "—")),
            ("Platform", iso.get("platform", "—")),
            ("Assembly QC", iso.get("assembly_quality", "—")),
        ])
    with grid[1]:
        _review_block("Genome file", [
            ("File", g.get("filename", "—")),
            ("Submission ID", g.get("checksum", "—")),
            ("Contigs", f'{g.get("sequence_count",0):,}'),
            ("Length", f'{g.get("total_length_bp",0):,} bp'),
            ("Quality", g.get("qc_status", "—")),
        ])
        _review_block("Model", [
            ("Model version", "genome-firewall-v0.1"),
            ("Species scope", "S. aureus"),
            ("Antibiotics", str(len(_DRUGS))),
            ("Outputs", "Per-drug verdict + confidence + evidence"),
        ])
    C.panel_close()
    st.write("")

    C.safety_banner()
    st.write("")
    C.panel_open("Required acknowledgments", eyebrow="Responsible use", icon_name="shield-check")
    a1 = st.checkbox("The uploaded file is a reconstructed, quality-checked genome assembly.")
    a2 = st.checkbox("The bacterial species was already identified by the laboratory.")
    a3 = st.checkbox("I understand this is decision support and standard laboratory testing remains required.")
    C.panel_close()

    def _create_analysis():
        # Persist the case + isolate + a draft analysis into the store.
        ed = ctx.get("encounter_date")
        sd = iso.get("specimen_date")
        case = Case(
            patient_id=p.id, title=ctx.get("title", "Untitled case"),
            encounter_date=ed.isoformat() if ed else None,
            infection_site=ctx.get("site", ""), syndrome=ctx.get("syndrome", ""),
            priority=ctx.get("priority", CasePriority.ROUTINE.value),
            antibiotic_exposure=ctx.get("exposure", ""), notes=ctx.get("notes", ""),
            institution=p.institution, clinician=p.clinician,
        )
        case.isolate = Isolate(
            lab_id=iso.get("lab_id", ""), species=iso.get("species", "Staphylococcus aureus"),
            gram_stain=iso.get("gram_stain", "Gram-positive"),
            specimen_type=iso.get("specimen_type", ""),
            specimen_date=sd.isoformat() if sd else None,
            culture_source=iso.get("culture_source", ""),
            assembly_id=iso.get("assembly_id", ""),
            sequencing_platform=iso.get("platform", ""),
            assembly_quality=iso.get("assembly_quality", ""),
            lab_notes=iso.get("lab_notes", ""),
        )
        store.create_case(case)
        prov = get_provider()
        analysis = prov.create_analysis(
            patient_id=p.id, case_id=case.id, isolate_id=case.isolate.id,
            species=case.isolate.species, model_version="genome-firewall-v0.1")
        analysis.genome = GenomeSubmission(
            filename=g.get("filename", ""), size_bytes=g.get("size_bytes", 0),
            checksum=g.get("checksum", ""), sequence_count=g.get("sequence_count", 0),
            total_length_bp=g.get("total_length_bp", 0), n50=g.get("n50", 0),
            gc_content=g.get("gc_content", 0.0), qc_status=g.get("qc_status", "passed"),
            qc_warnings=g.get("qc_warnings", []),
        )
        store.add_analysis(case, analysis)
        w["analysis_id"] = analysis.id

    _nav(5, can_next=(a1 and a2 and a3), next_label="Run Genome Firewall Analysis",
         on_next=_create_analysis)


def _review_block(title: str, rows: list[tuple[str, str]]) -> None:
    inner = "".join(
        f'<div class="gf-kv"><span class="k">{C.esc(k)}</span>'
        f'<span class="v">{C.esc(v)}</span></div>' for k, v in rows)
    st.markdown(
        f'<div style="margin-bottom:14px"><div class="gf-eyebrow" style="margin-bottom:7px">'
        f'{C.esc(title)}</div>{inner}</div>', unsafe_allow_html=True)


# ── Step 6: Submit / handoff to processing ───────────────────────────────────
def _step_submit(store, w) -> None:
    aid = w.get("analysis_id")
    analysis = store.get_analysis(aid) if aid else None
    if not analysis:
        st.error("Submission could not be created. Please review the previous steps.")
        if st.button("Back to review"):
            w["step"] = 5
            st.rerun()
        return
    prov = get_provider()
    if analysis.status == "draft":
        prov.start_analysis(analysis)

    st.session_state["_toast"] = f"Analysis {analysis.id} submitted."
    # Clear the wizard so a new submission starts fresh, then hand off.
    st.session_state.pop("wizard", None)
    nav_to("analysis", analysis_id=analysis.id)
