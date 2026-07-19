"""
Genome Firewall — reusable presentation components.

Two things live here:
  • COMPONENT_CSS — component-scoped styles injected once by theme.inject().
  • render helpers — small functions returning HTML strings (composable) or
    drawing directly with st.markdown.

Rules honored throughout:
  • Status is never color alone — always icon + label + text.
  • Tabular numerals for confidence and identifiers; mono for gene/mutation/
    filename/accession tokens only.
  • Quiet motion, thin borders, controlled radii.
"""

from __future__ import annotations

import html as _html
from typing import Iterable

import streamlit as st

from app.icons import icon
from app.services.schemas import (
    EVIDENCE_META, PREDICTION_META, PIPELINE_STAGES, AnalysisStatus, QcStatus,
)

# ─────────────────────────────────────────────────────────────────────────────
COMPONENT_CSS = r"""
/* ── Page header ─────────────────────────────────────────────────────── */
.gf-crumbs { display:flex; align-items:center; gap:7px; font-size:.78rem;
  color:var(--gf-muted); margin-bottom:8px; flex-wrap:wrap; }
.gf-crumbs .sep { color:var(--gf-faint); }
.gf-crumbs b { color:var(--gf-ink-2); font-weight:600; }
.gf-ph { display:flex; align-items:flex-start; justify-content:space-between;
  gap:20px; margin:0 0 6px; }
.gf-ph-title { display:flex; align-items:center; gap:12px; }
.gf-ph-title h1 { font-size:1.7rem; }
.gf-ph-sub { color:var(--gf-muted); font-size:.95rem; margin-top:5px; max-width:70ch; }
.gf-ph-icon { width:40px; height:40px; border-radius:11px; flex:none; display:grid;
  place-items:center; color:#fff; background:linear-gradient(150deg,var(--gf-brand-2),var(--gf-brand-3));
  box-shadow:var(--gf-sh-1); }

/* ── Cards / panels ──────────────────────────────────────────────────── */
/* Panels are real Streamlit bordered containers (see components.panel_open) */
[data-testid="stVerticalBlockBorderWrapper"] {
  background:var(--gf-surface); border:1px solid var(--gf-border) !important;
  border-radius:var(--gf-r-lg) !important; box-shadow:var(--gf-sh-1); }
[data-testid="stVerticalBlockBorderWrapper"] > div { padding:2px; }
.gf-panel-mark { display:none; }
.gf-panel { background:var(--gf-surface); border:1px solid var(--gf-border);
  border-radius:var(--gf-r-lg); box-shadow:var(--gf-sh-1); padding:18px 20px; }
.gf-panel-h { display:flex; align-items:center; justify-content:space-between;
  gap:12px; margin:0 0 4px; }
.gf-panel-h h3 { font-size:.98rem; }
.gf-panel-h .gf-eyebrow { margin:0; }
.gf-eyebrow { font-size:.72rem; font-weight:700; letter-spacing:.08em;
  text-transform:uppercase; color:var(--gf-muted); display:flex; align-items:center; gap:7px; }

/* ── Badges / pills ──────────────────────────────────────────────────── */
.gf-badge { display:inline-flex; align-items:center; gap:6px; font-size:.78rem;
  font-weight:650; padding:3px 10px; border-radius:var(--gf-r-pill);
  border:1px solid transparent; white-space:nowrap; line-height:1.3; }
.gf-badge svg { flex:none; }
.gf-b-work { color:var(--gf-work); background:var(--gf-work-soft); border-color:var(--gf-work-border); }
.gf-b-fail { color:var(--gf-fail); background:var(--gf-fail-soft); border-color:var(--gf-fail-border); }
.gf-b-nocall { color:var(--gf-nocall); background:var(--gf-nocall-soft); border-color:var(--gf-nocall-border); }
.gf-b-info { color:var(--gf-info); background:var(--gf-info-soft); border-color:var(--gf-info-border); }
.gf-b-neutral { color:var(--gf-neutral); background:var(--gf-neutral-soft); border-color:var(--gf-border); }
.gf-b-brand { color:var(--gf-brand-ink); background:var(--gf-brand-soft); border-color:var(--gf-brand-border); }
.gf-b-sm { font-size:.7rem; padding:2px 8px; }

.gf-tag { display:inline-flex; align-items:center; gap:5px; font-family:var(--gf-mono);
  font-size:.76rem; background:var(--gf-surface-2); color:var(--gf-ink-2);
  border:1px solid var(--gf-border); border-radius:var(--gf-r-sm); padding:2px 7px; }
.gf-tag-mut { color:var(--gf-fail); background:var(--gf-fail-soft); border-color:var(--gf-fail-border); }
.gf-tag-gene { color:var(--gf-brand-ink); background:var(--gf-brand-soft); border-color:var(--gf-brand-border); }
.gf-tag-stat { color:var(--gf-nocall); background:var(--gf-nocall-soft); border-color:var(--gf-nocall-border); }

/* ── Mandatory safety banner ─────────────────────────────────────────── */
.gf-safety { display:flex; gap:12px; align-items:flex-start; background:var(--gf-info-soft);
  border:1px solid var(--gf-info-border); border-left:3px solid var(--gf-info);
  color:#0b4a5c; border-radius:var(--gf-r); padding:12px 15px; font-size:.86rem; line-height:1.5; }
.gf-safety .ico { color:var(--gf-info); margin-top:1px; flex:none; }
.gf-safety b { color:#083744; }

/* ── Stat / KPI tiles ────────────────────────────────────────────────── */
.gf-stats { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }
.gf-stat { background:var(--gf-surface); border:1px solid var(--gf-border);
  border-radius:var(--gf-r-lg); padding:15px 16px; box-shadow:var(--gf-sh-1);
  transition:box-shadow var(--gf-fast), border-color var(--gf-fast); }
.gf-stat:hover { box-shadow:var(--gf-sh-2); border-color:var(--gf-brand-border); }
.gf-stat-top { display:flex; align-items:center; justify-content:space-between; }
.gf-stat-lbl { font-size:.74rem; font-weight:650; letter-spacing:.03em; text-transform:uppercase;
  color:var(--gf-muted); }
.gf-stat-ico { color:var(--gf-faint); }
.gf-stat-val { font-size:1.9rem; font-weight:750; line-height:1.05; margin-top:8px;
  font-variant-numeric:tabular-nums; color:var(--gf-ink); }
.gf-stat-sub { font-size:.78rem; color:var(--gf-muted); margin-top:3px; }

/* ── List rows (patients / cases / analyses) ─────────────────────────── */
.gf-rows { display:flex; flex-direction:column; }
.gf-listhead, .gf-row2 { display:grid; align-items:center; gap:14px; padding:11px 16px; }
.gf-listhead { font-size:.72rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
  color:var(--gf-muted); border-bottom:1px solid var(--gf-border); }
.gf-row2 { border-bottom:1px solid var(--gf-border); transition:background var(--gf-fast); }
.gf-row2:last-child { border-bottom:none; }
.gf-row2:hover { background:var(--gf-surface-2); }
.gf-avatar { width:34px; height:34px; border-radius:9px; flex:none; display:grid; place-items:center;
  font-weight:700; font-size:.82rem; color:var(--gf-brand-ink); background:var(--gf-brand-soft);
  border:1px solid var(--gf-brand-border); }
.gf-name { font-weight:600; color:var(--gf-ink); font-size:.92rem; }
.gf-sub { color:var(--gf-muted); font-size:.8rem; }
.gf-mono { font-family:var(--gf-mono); font-size:.82rem; color:var(--gf-ink-2); }

/* ── Confidence meter ────────────────────────────────────────────────── */
.gf-conf { }
.gf-conf-top { display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
.gf-conf-num { font-size:1.15rem; font-weight:750; font-variant-numeric:tabular-nums; }
.gf-conf-cap { font-size:.72rem; color:var(--gf-muted); text-transform:uppercase; letter-spacing:.04em; }
.gf-track { position:relative; height:7px; border-radius:99px; background:var(--gf-surface-2);
  border:1px solid var(--gf-border); margin:7px 0 5px; overflow:hidden; }
.gf-track-fill { position:absolute; inset:0 auto 0 0; height:100%; border-radius:99px; }
.gf-track-band { position:absolute; top:0; bottom:0; background:rgba(15,27,45,.14);
  border-left:1px dashed rgba(15,27,45,.4); border-right:1px dashed rgba(15,27,45,.4); }
.gf-conf-note { font-size:.76rem; color:var(--gf-muted); }

/* ── Evidence Trace (signature component) ────────────────────────────── */
.gf-trace { display:flex; align-items:stretch; gap:0; flex-wrap:wrap; }
.gf-trace-step { flex:1 1 0; min-width:104px; position:relative; padding:12px 12px 12px 14px;
  border:1px solid var(--gf-border); background:var(--gf-surface-2); margin-left:-1px; }
.gf-trace-step:first-child { border-top-left-radius:var(--gf-r); border-bottom-left-radius:var(--gf-r); margin-left:0; }
.gf-trace-step:last-child { border-top-right-radius:var(--gf-r); border-bottom-right-radius:var(--gf-r); }
.gf-trace-k { font-size:.68rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
  color:var(--gf-muted); display:flex; align-items:center; gap:6px; }
.gf-trace-v { font-size:.85rem; font-weight:600; color:var(--gf-ink); margin-top:6px; line-height:1.3; }
.gf-trace-arrow { position:absolute; right:-9px; top:50%; transform:translateY(-50%); z-index:2;
  color:var(--gf-faint); background:var(--gf-surface); border-radius:99px; display:grid; place-items:center; }
.gf-trace-step.on { background:var(--gf-surface); box-shadow:inset 0 2px 0 var(--gf-brand-2); border-color:var(--gf-brand-border); }
.gf-trace-step.fail { box-shadow:inset 0 2px 0 var(--gf-fail); }
.gf-trace-step.work { box-shadow:inset 0 2px 0 var(--gf-work); }
.gf-trace-step.nocall { box-shadow:inset 0 2px 0 var(--gf-nocall); }

/* ── Pipeline stepper (processing) ───────────────────────────────────── */
.gf-pipe { display:flex; flex-direction:column; gap:2px; }
.gf-pipe-step { display:flex; align-items:flex-start; gap:12px; padding:9px 4px; }
.gf-pipe-rail { display:flex; flex-direction:column; align-items:center; }
.gf-pipe-dot { width:22px; height:22px; border-radius:99px; display:grid; place-items:center;
  border:2px solid var(--gf-border-strong); background:var(--gf-surface); color:var(--gf-faint); flex:none; }
.gf-pipe-line { width:2px; flex:1; min-height:14px; background:var(--gf-border); margin:2px 0; }
.gf-pipe-step.done .gf-pipe-dot { border-color:var(--gf-work); background:var(--gf-work); color:#fff; }
.gf-pipe-step.done .gf-pipe-line { background:var(--gf-work-border); }
.gf-pipe-step.active .gf-pipe-dot { border-color:var(--gf-brand-2); color:var(--gf-brand-2);
  box-shadow:0 0 0 4px var(--gf-brand-soft); }
.gf-pipe-step.active .gf-pipe-dot svg { animation:gf-spin 1.1s linear infinite; }
.gf-pipe-step.fail .gf-pipe-dot { border-color:var(--gf-fail); background:var(--gf-fail); color:#fff; }
.gf-pipe-txt { padding-top:1px; }
.gf-pipe-name { font-weight:600; font-size:.9rem; color:var(--gf-ink); }
.gf-pipe-step.pending .gf-pipe-name { color:var(--gf-faint); }
.gf-pipe-desc { font-size:.79rem; color:var(--gf-muted); margin-top:1px; }

/* ── Timeline ────────────────────────────────────────────────────────── */
.gf-tl { display:flex; flex-direction:column; }
.gf-tl-item { display:flex; gap:12px; padding-bottom:14px; position:relative; }
.gf-tl-item:not(:last-child)::before { content:""; position:absolute; left:10px; top:22px; bottom:-2px;
  width:2px; background:var(--gf-border); }
.gf-tl-dot { width:22px; height:22px; border-radius:99px; flex:none; display:grid; place-items:center;
  background:var(--gf-brand-soft); color:var(--gf-brand); border:1px solid var(--gf-brand-border); z-index:1; }
.gf-tl-body { padding-top:1px; }
.gf-tl-msg { font-size:.88rem; color:var(--gf-ink); font-weight:500; }
.gf-tl-at { font-size:.76rem; color:var(--gf-muted); margin-top:1px; }

/* ── Empty & skeleton states ─────────────────────────────────────────── */
.gf-empty { text-align:center; padding:44px 24px; border:1px dashed var(--gf-border-strong);
  border-radius:var(--gf-r-lg); background:var(--gf-surface); }
.gf-empty-ico { width:48px; height:48px; border-radius:13px; margin:0 auto 12px; display:grid;
  place-items:center; color:var(--gf-brand); background:var(--gf-brand-soft); border:1px solid var(--gf-brand-border); }
.gf-empty h3 { font-size:1.02rem; margin-bottom:5px; }
.gf-empty p { color:var(--gf-muted); font-size:.88rem; max-width:44ch; margin:0 auto; }
.gf-skel { height:14px; border-radius:6px; background:linear-gradient(90deg,#eef1f6 25%,#e2e7ef 37%,#eef1f6 63%);
  background-size:800px 100%; animation:gf-shimmer 1.4s infinite linear; }

/* ── Result card (antibiotic) ────────────────────────────────────────── */
.gf-result { background:var(--gf-surface); border:1px solid var(--gf-border);
  border-radius:var(--gf-r-lg); box-shadow:var(--gf-sh-1); overflow:hidden; }
.gf-result-head { display:flex; align-items:center; gap:16px; padding:14px 18px; }
.gf-result-bar { width:3px; align-self:stretch; border-radius:3px; }
.gf-result-name { font-size:1.05rem; font-weight:700; color:var(--gf-ink); }
.gf-result-class { font-size:.78rem; color:var(--gf-muted); }
.gf-kv { display:grid; grid-template-columns:180px 1fr; gap:6px 16px; align-items:start;
  font-size:.86rem; padding:2px 0; }
.gf-kv .k { color:var(--gf-muted); font-weight:600; font-size:.78rem; text-transform:uppercase; letter-spacing:.03em; }
.gf-kv .v { color:var(--gf-ink-2); }
.gf-evd-box { display:flex; gap:10px; align-items:flex-start; border-radius:var(--gf-r);
  padding:11px 13px; font-size:.85rem; line-height:1.5; border:1px solid; }
.gf-evd-i   { background:var(--gf-fail-soft);  border-color:var(--gf-fail-border);  color:#6d1a1a; }
.gf-evd-ii  { background:var(--gf-nocall-soft); border-color:var(--gf-nocall-border); color:#7a4a09; }
.gf-evd-iii { background:var(--gf-work-soft);  border-color:var(--gf-work-border);  color:#14532d; }
.gf-evd-conflicting { background:var(--gf-neutral-soft); border-color:var(--gf-border); color:var(--gf-ink-2); }
.gf-evd-box .ico { flex:none; margin-top:1px; }
.gf-evd-box b { display:block; }

/* ── Segmented meta strip ────────────────────────────────────────────── */
.gf-meta { display:flex; flex-wrap:wrap; gap:0; border:1px solid var(--gf-border);
  border-radius:var(--gf-r); overflow:hidden; background:var(--gf-surface); }
.gf-meta > div { padding:10px 15px; border-right:1px solid var(--gf-border); flex:1 1 auto; min-width:120px; }
.gf-meta > div:last-child { border-right:none; }
.gf-meta .k { font-size:.68rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; color:var(--gf-muted); }
.gf-meta .v { font-size:.9rem; font-weight:600; color:var(--gf-ink); margin-top:3px; }
.gf-meta .v.mono { font-family:var(--gf-mono); font-weight:500; font-size:.82rem; }

/* ── Demo environment ribbon ─────────────────────────────────────────── */
.gf-demo-chip { display:inline-flex; align-items:center; gap:6px; font-size:.7rem; font-weight:700;
  letter-spacing:.05em; text-transform:uppercase; color:var(--gf-nocall);
  background:var(--gf-nocall-soft); border:1px solid var(--gf-nocall-border);
  border-radius:var(--gf-r-pill); padding:3px 10px; }

/* ── Responsive ──────────────────────────────────────────────────────── */
@media (max-width:1000px) {
  .gf-stats { grid-template-columns:repeat(2,1fr); }
  [data-testid="stAppViewContainer"] .main .block-container { padding:20px 18px 72px; }
}
@media (max-width:640px) {
  .gf-stats { grid-template-columns:1fr; }
  .gf-trace-step { flex-basis:calc(50% - 1px); }
  .gf-kv { grid-template-columns:1fr; }
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────
def esc(x) -> str:
    return _html.escape(str(x))


def badge(label: str, tone: str = "neutral", icon_name: str | None = None,
          small: bool = False) -> str:
    cls = {"work": "gf-b-work", "fail": "gf-b-fail", "nocall": "gf-b-nocall",
           "info": "gf-b-info", "brand": "gf-b-brand", "neutral": "gf-b-neutral"}.get(tone, "gf-b-neutral")
    ico = icon(icon_name, 13) if icon_name else ""
    sm = " gf-b-sm" if small else ""
    return f'<span class="gf-badge {cls}{sm}">{ico}{esc(label)}</span>'


def prediction_badge(prediction: str, small: bool = False) -> str:
    m = PREDICTION_META.get(prediction, PREDICTION_META["no_call"])
    return badge(m["label"], m["tone"], m["icon"], small=small)


# Status → (label, tone, icon)
_STATUS_META = {
    AnalysisStatus.DRAFT.value: ("Draft", "neutral", "file"),
    AnalysisStatus.QUEUED.value: ("Queued", "info", "clock"),
    AnalysisStatus.UPLOADING.value: ("Uploading", "info", "upload-cloud"),
    AnalysisStatus.VALIDATING.value: ("Validating", "info", "loader"),
    AnalysisStatus.PROCESSING.value: ("Processing", "brand", "loader"),
    AnalysisStatus.COMPLETED.value: ("Completed", "work", "check-circle"),
    AnalysisStatus.COMPLETED_NO_CALL.value: ("Completed · no-call heavy", "nocall", "minus-circle"),
    AnalysisStatus.FAILED.value: ("Failed", "fail", "alert-triangle"),
    AnalysisStatus.CANCELLED.value: ("Cancelled", "neutral", "x-circle"),
}


def status_badge(status: str, small: bool = False) -> str:
    label, tone, ico = _STATUS_META.get(status, ("Unknown", "neutral", "circle"))
    return badge(label, tone, ico, small=small)


_QC_META = {
    QcStatus.PASSED.value: ("QC passed", "work", "check-circle"),
    QcStatus.WARNING.value: ("QC warning", "nocall", "alert-triangle"),
    QcStatus.FAILED.value: ("QC failed", "fail", "x-circle"),
    QcStatus.PENDING.value: ("QC pending", "neutral", "clock"),
}


def qc_badge(status: str, small: bool = False) -> str:
    label, tone, ico = _QC_META.get(status, ("QC pending", "neutral", "clock"))
    return badge(label, tone, ico, small=small)


def initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


# ─────────────────────────────────────────────────────────────────────────────
# Larger render helpers (draw directly)
# ─────────────────────────────────────────────────────────────────────────────
def page_header(title: str, *, subtitle: str = "", icon_name: str = "",
                crumbs: list[tuple[str, str | None]] | None = None) -> None:
    """Render breadcrumbs + a consistent page header. Actions are added by the
    caller via adjacent Streamlit columns/buttons."""
    if crumbs:
        parts = []
        for i, (label, _) in enumerate(crumbs):
            if i:
                parts.append('<span class="sep">/</span>')
            last = i == len(crumbs) - 1
            parts.append(f'<b>{esc(label)}</b>' if last else esc(label))
        st.markdown(f'<div class="gf-crumbs">{"".join(parts)}</div>', unsafe_allow_html=True)
    ico = f'<div class="gf-ph-icon">{icon(icon_name, 22)}</div>' if icon_name else ""
    sub = f'<div class="gf-ph-sub">{esc(subtitle)}</div>' if subtitle else ""
    st.markdown(
        f'<div class="gf-ph gf-fade"><div class="gf-ph-title">{ico}'
        f'<div><h1>{esc(title)}</h1>{sub}</div></div></div>',
        unsafe_allow_html=True,
    )


def safety_banner(text: str | None = None) -> None:
    body = text or (
        "<b>Research prototype — confirm every result with standard laboratory "
        "testing.</b> Decision support only; a trained professional makes the "
        "decision. This tool predicts and explains resistance that already exists "
        "in a sequenced genome — it never designs, modifies, or optimizes any organism."
    )
    st.markdown(
        f'<div class="gf-safety"><span class="ico">{icon("shield-alert", 18)}</span>'
        f'<div>{body}</div></div>',
        unsafe_allow_html=True,
    )


def stat_tile(label: str, value, sub: str = "", icon_name: str = "activity",
              value_color: str | None = None) -> str:
    col = f'style="color:{value_color}"' if value_color else ""
    return (
        f'<div class="gf-stat"><div class="gf-stat-top">'
        f'<span class="gf-stat-lbl">{esc(label)}</span>'
        f'<span class="gf-stat-ico">{icon(icon_name, 17)}</span></div>'
        f'<div class="gf-stat-val" {col}>{esc(value)}</div>'
        f'<div class="gf-stat-sub">{esc(sub)}</div></div>'
    )


def stat_row(tiles: Iterable[str]) -> None:
    st.markdown(f'<div class="gf-stats">{"".join(tiles)}</div>', unsafe_allow_html=True)


def empty_state(title: str, body: str, icon_name: str = "search") -> None:
    st.markdown(
        f'<div class="gf-empty"><div class="gf-empty-ico">{icon(icon_name, 24)}</div>'
        f'<h3>{esc(title)}</h3><p>{esc(body)}</p></div>',
        unsafe_allow_html=True,
    )


def confidence_meter(confidence: float, band: tuple[float, float],
                     tone: str, crossed: bool, no_call: bool) -> str:
    pct = max(0, min(100, round(confidence * 100)))
    color = {"work": "var(--gf-work)", "fail": "var(--gf-fail)",
             "nocall": "var(--gf-nocall)"}.get(tone, "var(--gf-neutral)")
    lo, hi = band
    band_html = (
        f'<div class="gf-track-band" style="left:{lo*100:.0f}%;width:{max(0.0,(hi-lo))*100:.0f}%"></div>'
    )
    if no_call:
        note = "No-call threshold triggered — model declined to cross the decision boundary."
    elif crossed:
        note = "Crossed the decision threshold. Calibrated model confidence — not a guarantee of clinical outcome."
    else:
        note = "Below the decision threshold."
    return (
        f'<div class="gf-conf"><div class="gf-conf-top">'
        f'<span class="gf-conf-num gf-tnum" style="color:{color}">{pct}%</span>'
        f'<span class="gf-conf-cap">calibrated confidence · band {lo*100:.0f}–{hi*100:.0f}%</span></div>'
        f'<div class="gf-track"><div class="gf-track-fill" style="width:{pct}%;background:{color}"></div>{band_html}</div>'
        f'<div class="gf-conf-note">{esc(note)}</div></div>'
    )


def evidence_trace(*, features_found: int, target_gate: str, prediction: str,
                   confidence: float, tone: str) -> str:
    """The signature Evidence Trace: submission → features → target → model →
    calibration → result, as a connected horizontal strip."""
    pm = PREDICTION_META.get(prediction, PREDICTION_META["no_call"])
    arrow = f'<div class="gf-trace-arrow">{icon("chevron-right", 15)}</div>'
    tg_label = {"passed": "Target present", "failed": "Target absent",
                "unknown": "Target unknown"}.get(target_gate, "—")
    steps = [
        ("Genome", "dna", "Submitted assembly", "on"),
        ("Features", "flask", f"{features_found} marker(s)", "on"),
        ("Target gate", "target", tg_label, "on" if target_gate == "passed" else "nocall"),
        ("Model", "cpu", "Per-drug score", "on"),
        ("Calibration", "gauge", f"{round(confidence*100)}%", "on"),
        ("Result", pm["icon"], pm["short"], tone),
    ]
    out = ['<div class="gf-trace">']
    for i, (k, ic, v, state) in enumerate(steps):
        a = arrow if i < len(steps) - 1 else ""
        out.append(
            f'<div class="gf-trace-step {state}"><div class="gf-trace-k">{icon(ic, 13)}{esc(k)}</div>'
            f'<div class="gf-trace-v">{esc(v)}</div>{a}</div>'
        )
    out.append("</div>")
    return "".join(out)


def pipeline_stepper(current_stage: int, *, failed_at: int | None = None,
                     complete: bool = False) -> str:
    out = ['<div class="gf-pipe">']
    n = len(PIPELINE_STAGES)
    for i, (name, desc) in enumerate(PIPELINE_STAGES):
        if failed_at is not None and i == failed_at:
            state, glyph = "fail", icon("x", 12)
        elif complete or i < current_stage or (failed_at is not None and i < failed_at):
            state, glyph = "done", icon("check", 12)
        elif i == current_stage and failed_at is None:
            state, glyph = "active", icon("loader", 12)
        else:
            state, glyph = "pending", f'<span style="font-size:.7rem;font-weight:700">{i+1}</span>'
        line = '<div class="gf-pipe-line"></div>' if i < n - 1 else ""
        out.append(
            f'<div class="gf-pipe-step {state}"><div class="gf-pipe-rail">'
            f'<div class="gf-pipe-dot">{glyph}</div>{line}</div>'
            f'<div class="gf-pipe-txt"><div class="gf-pipe-name">{esc(name)}</div>'
            f'<div class="gf-pipe-desc">{esc(desc)}</div></div></div>'
        )
    out.append("</div>")
    return "".join(out)


def timeline(events: list[dict]) -> str:
    out = ['<div class="gf-tl">']
    for ev in events:
        out.append(
            f'<div class="gf-tl-item"><div class="gf-tl-dot">{icon(ev.get("icon", "activity"), 12)}</div>'
            f'<div class="gf-tl-body"><div class="gf-tl-msg">{esc(ev["message"])}</div>'
            f'<div class="gf-tl-at">{esc(ev.get("at",""))}</div></div></div>'
        )
    out.append("</div>")
    return "".join(out)


def gene_tags(genes: list[str], mutations: list[str], statistical: list[str]) -> str:
    tags = []
    for g in genes:
        tags.append(f'<span class="gf-tag gf-tag-gene">{icon("flask", 11)}{esc(g)}</span>')
    for m in mutations:
        tags.append(f'<span class="gf-tag gf-tag-mut">{esc(m)}</span>')
    for s in statistical:
        tags.append(f'<span class="gf-tag gf-tag-stat">{icon("bar-chart", 11)}{esc(s)}</span>')
    if not tags:
        return '<span class="gf-sub">None cited</span>'
    return " ".join(tags)


_PANEL_STACK: list = []


def panel_open(title: str = "", eyebrow: str = "", icon_name: str = "") -> None:
    """Open a panel backed by a real Streamlit bordered container.

    Streamlit widgets cannot be nested inside a raw HTML <div> that is opened in
    one st.markdown call and closed in another (they render as siblings, not
    children). So a panel must be a genuine container; we enter its context here
    and exit it in panel_close(). Styling is applied to the container in CSS via
    the `gf-panel-wrap` marker class the container picks up.
    """
    c = st.container(border=True)
    c.__enter__()
    _PANEL_STACK.append(c)
    st.markdown('<span class="gf-panel-mark"></span>', unsafe_allow_html=True)
    if eyebrow or title:
        ey = (f'<span class="gf-eyebrow">{icon(icon_name, 13) if icon_name else ""}'
              f'{esc(eyebrow)}</span>') if eyebrow else ""
        ti = f"<h3>{esc(title)}</h3>" if title else ""
        st.markdown(f'<div class="gf-panel-h">{ti}{ey}</div>', unsafe_allow_html=True)


def panel_close() -> None:
    if _PANEL_STACK:
        c = _PANEL_STACK.pop()
        c.__exit__(None, None, None)


def relative_time(iso: str) -> str:
    """Human 'time ago' from an ISO-Z timestamp."""
    from datetime import datetime
    try:
        t = datetime.fromisoformat(iso.replace("Z", ""))
    except (ValueError, AttributeError):
        return iso
    delta = datetime.utcnow() - t
    s = int(delta.total_seconds())
    if s < 0:
        return "just now"
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    d = s // 86400
    if d < 30:
        return f"{d} d ago"
    return t.strftime("%b %d, %Y")
