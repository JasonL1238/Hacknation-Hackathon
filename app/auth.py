"""
Authentication for Genome Firewall.

Email/password + Google OAuth via Supabase, plus a zero-setup guest/demo mode.
Supabase is imported lazily so the app boots and the demo runs even when the
`supabase` package or credentials are absent — the guest path never touches it.

The auth logic functions are backend-agnostic; a real IdP can replace the
Supabase calls without changing the sign-in UI.
"""

from __future__ import annotations

import os

import streamlit as st

from app.icons import icon


# ─── lazy supabase access ────────────────────────────────────────────────────
def _auth_error_cls():
    try:
        from supabase_auth.errors import AuthApiError  # supabase >= 2.15
        return AuthApiError
    except Exception:  # pragma: no cover
        try:
            from gotrue.errors import AuthApiError
            return AuthApiError
        except Exception:
            return Exception


def _supabase():
    from app.supabase_client import get_supabase
    return get_supabase()


def supabase_available() -> bool:
    """True if the supabase package is importable AND credentials are present."""
    try:
        import supabase  # noqa: F401
    except Exception:
        return False
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"))


# ─── session helpers ─────────────────────────────────────────────────────────
def get_current_user() -> dict | None:
    return st.session_state.get("user")


def is_authenticated() -> bool:
    return get_current_user() is not None


def is_guest() -> bool:
    user = get_current_user()
    return bool(user and user.get("is_guest"))


def enter_guest_mode() -> None:
    st.session_state["user"] = {
        "id": "guest",
        "email": "demo.clinician@genomefirewall.dev",
        "user_metadata": {"full_name": "Dr. Demo Clinician"},
        "is_guest": True,
    }
    st.session_state["session"] = None
    st.session_state["access_token"] = None


def _set_session(user: dict, session: dict) -> None:
    st.session_state["user"] = user
    st.session_state["session"] = session
    st.session_state["access_token"] = session.get("access_token")


def _clear_session() -> None:
    for key in ("user", "session", "access_token", "gf_store",
                "guest_patients", "guest_records", "route", "route_params",
                "_pdf_done", "_pdf_msg", "_clear_new_patient", "wizard"):
        st.session_state.pop(key, None)


# ─── email/password + OAuth (lazy) ───────────────────────────────────────────
def sign_up(email: str, password: str, full_name: str) -> tuple[bool, str]:
    try:
        response = _supabase().auth.sign_up({
            "email": email, "password": password,
            "options": {"data": {"full_name": full_name}},
        })
        if response.user:
            return True, "Account created. Check your email to confirm your address."
        return False, "Sign-up failed. Please try again."
    except _auth_error_cls() as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"{e}  (Tip: use 'Continue to demo workspace' to explore without setup.)"


def sign_in(email: str, password: str) -> tuple[bool, str]:
    try:
        response = _supabase().auth.sign_in_with_password(
            {"email": email, "password": password})
        if response.user and response.session:
            _set_session(response.user.model_dump(), response.session.model_dump())
            return True, "Signed in."
        return False, "Invalid credentials."
    except _auth_error_cls() as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"{e}  (Tip: use 'Continue to demo workspace' to explore without setup.)"


def sign_out() -> None:
    if not is_guest():
        try:
            _supabase().auth.sign_out()
        except Exception:
            pass
    _clear_session()


def reset_password(email: str) -> tuple[bool, str]:
    try:
        _supabase().auth.reset_password_email(email)
        return True, "Password reset email sent. Check your inbox."
    except _auth_error_cls() as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"{e}  (Tip: use 'Continue to demo workspace' to explore without setup.)"


def get_google_login_url() -> str | None:
    try:
        response = _supabase().auth.sign_in_with_oauth({
            "provider": "google",
            "options": {"redirect_to": _get_redirect_url()},
        })
        return response.url
    except Exception:
        return None


def handle_oauth_code(code: str) -> tuple[bool, str]:
    try:
        response = _supabase().auth.exchange_code_for_session({"auth_code": code})
        if response.user and response.session:
            _set_session(response.user.model_dump(), response.session.model_dump())
            return True, "Signed in with Google."
        return False, "OAuth exchange failed."
    except _auth_error_cls() as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _get_redirect_url() -> str:
    return os.environ.get("OAUTH_REDIRECT_URL", "http://localhost:8501")


# ─── premium sign-in experience ──────────────────────────────────────────────
_LOGIN_CSS = r"""
<style>
[data-testid="stSidebar"] { display:none !important; }
[data-testid="stAppViewContainer"] .main .block-container { max-width:1080px; padding-top:52px; }
/* Left: product preview panel (deep navy) — a self-contained card */
.gf-auth-left { background:
    radial-gradient(680px 320px at 12% -8%, rgba(56,189,248,.16), transparent 60%),
    radial-gradient(560px 340px at 108% 112%, rgba(37,99,235,.24), transparent 58%),
    var(--gf-nav);
  color:#e2e8f0; padding:34px 32px 30px; display:flex; flex-direction:column; gap:18px;
  border-radius:18px; box-shadow:var(--gf-sh-3); height:100%; min-height:560px; }
.gf-auth-brand { display:flex; align-items:center; gap:12px; }
.gf-auth-brand .m { width:40px; height:40px; border-radius:11px; display:grid; place-items:center;
  color:#fff; background:linear-gradient(150deg,var(--gf-brand-2),var(--gf-brand-3));
  box-shadow:0 6px 20px rgba(37,99,235,.5); }
.gf-auth-brand b { font-size:1.12rem; color:#fff; letter-spacing:-.01em; }
.gf-auth-brand span { display:block; font-size:.68rem; letter-spacing:.08em; text-transform:uppercase; color:#7c8aa5; }
.gf-auth-hl { font-size:1.5rem; font-weight:700; line-height:1.2; letter-spacing:-.02em; color:#f8fafc; margin-top:8px; }
.gf-auth-hl em { color:#7dd3fc; font-style:normal; }
.gf-auth-lead { color:#aab6cc; font-size:.92rem; line-height:1.55; }
.gf-auth-feats { display:flex; flex-direction:column; gap:11px; margin-top:2px; }
.gf-auth-feat { display:flex; gap:11px; align-items:flex-start; }
.gf-auth-feat .fi { color:#7dd3fc; margin-top:1px; flex:none; }
.gf-auth-feat b { color:#e2e8f0; font-size:.88rem; font-weight:600; }
.gf-auth-feat p { color:#8695ad; font-size:.8rem; margin:1px 0 0; }
/* Product preview mock */
.gf-preview { margin-top:auto; border:1px solid #24324d; border-radius:12px; overflow:hidden; background:#0d1626; }
.gf-preview .bar { display:flex; gap:6px; padding:9px 12px; border-bottom:1px solid #1c2740; }
.gf-preview .bar i { width:9px; height:9px; border-radius:99px; background:#33415580; display:block; }
.gf-preview .body { padding:12px; display:flex; flex-direction:column; gap:8px; }
.gf-preview .rowp { display:flex; align-items:center; justify-content:space-between; gap:10px;
  background:#101d33; border:1px solid #1c2740; border-radius:8px; padding:8px 10px; }
.gf-preview .rowp .nm { color:#cbd5e1; font-size:.76rem; font-weight:600; }
.gf-pchip { font-size:.64rem; font-weight:700; padding:2px 8px; border-radius:99px; }
.gf-pchip.f { color:#fca5a5; background:#3a1414; }
.gf-pchip.w { color:#86efac; background:#0f2e1c; }
.gf-pchip.n { color:#fcd34d; background:#392a0c; }
.gf-auth-legal { color:#7c8aa5; font-size:.72rem; margin-top:2px; }
/* Right: form panel */
.gf-auth-right h2 { font-size:1.28rem; }
.gf-auth-right .lead { color:var(--gf-muted); font-size:.9rem; margin:4px 0 14px; }
.gf-secnote { display:flex; align-items:center; gap:8px; font-size:.76rem; color:var(--gf-muted);
  background:var(--gf-surface-2); border:1px solid var(--gf-border); border-radius:var(--gf-r); padding:9px 12px; margin-top:14px; }
.gf-secnote .si { color:var(--gf-work); flex:none; }
.gf-orline { display:flex; align-items:center; gap:12px; color:var(--gf-faint); font-size:.72rem;
  text-transform:uppercase; letter-spacing:.08em; margin:14px 0 10px; }
.gf-orline::before, .gf-orline::after { content:""; flex:1; height:1px; background:var(--gf-border); }
</style>
"""


def _feature(ic: str, title: str, body: str) -> str:
    return (f'<div class="gf-auth-feat"><span class="fi">{icon(ic, 17)}</span>'
            f'<div><b>{title}</b><p>{body}</p></div></div>')


def render_login_page() -> None:
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    left = (
        '<div class="gf-auth-left">'
        f'<div class="gf-auth-brand"><div class="m">{icon("shield-check", 22)}</div>'
        '<div><b>Genome Firewall</b><span>Clinical AMR Intelligence</span></div></div>'
        '<div class="gf-auth-hl">Calibrated antibiotic-resistance decision support for '
        '<em>Staphylococcus&nbsp;aureus</em>.</div>'
        '<div class="gf-auth-lead">Submit a reconstructed, quality-checked genome and review a '
        'per-antibiotic report with calibrated confidence, honest evidence categories, and a full '
        'analysis history tied to each patient and case.</div>'
        '<div class="gf-auth-feats">'
        + _feature("gauge", "Calibrated & honest",
                   "Confidence is calibrated on held-out data; weak evidence returns an explicit no-call.")
        + _feature("flask", "Evidence you can trace",
                   "Separates catalog-confirmed markers from statistical associations — never conflated.")
        + _feature("lock", "Built for clinical trust",
                   "Human-in-the-loop by design; every result requires laboratory confirmation.")
        + '</div>'
        '<div class="gf-preview"><div class="bar"><i></i><i></i><i></i></div>'
        '<div class="body">'
        '<div class="rowp"><span class="nm">Cefoxitin</span><span class="gf-pchip f">LIKELY TO FAIL</span></div>'
        '<div class="rowp"><span class="nm">Tetracycline</span><span class="gf-pchip w">LIKELY TO WORK</span></div>'
        '<div class="rowp"><span class="nm">Gentamicin</span><span class="gf-pchip n">NO-CALL</span></div>'
        '</div></div>'
        '<div class="gf-auth-legal">Research prototype · synthetic demonstration data only · '
        'not a cleared diagnostic device.</div>'
        '</div>'
    )

    col_left, col_right = st.columns([1.02, 0.98], gap="medium")
    with col_left:
        st.markdown(left, unsafe_allow_html=True)
    with col_right:
        st.markdown('<div class="gf-auth-right">', unsafe_allow_html=True)
        st.markdown("<h2>Sign in</h2>"
                    '<div class="lead">Access your clinical research workspace.</div>',
                    unsafe_allow_html=True)

        tab_login, tab_register, tab_reset = st.tabs(["Sign in", "Create account", "Reset"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Work email", placeholder="you@hospital.org")
                password = st.text_input("Password", type="password", placeholder="••••••••")
                submitted = st.form_submit_button("Sign in", use_container_width=True,
                                                  type="primary")
                if submitted:
                    if not email or not password:
                        st.error("Please enter both email and password.")
                    else:
                        ok, msg = sign_in(email, password)
                        (st.success if ok else st.error)(msg)
                        if ok:
                            st.rerun()

            gurl = get_google_login_url() if supabase_available() else None
            if gurl:
                st.link_button("Continue with Google", gurl, use_container_width=True,
                               icon=":material/login:")

        with tab_register:
            with st.form("register_form"):
                reg_name = st.text_input("Full name")
                reg_email = st.text_input("Work email")
                c1, c2 = st.columns(2)
                reg_pw = c1.text_input("Password", type="password")
                reg_pw2 = c2.text_input("Confirm", type="password")
                if st.form_submit_button("Create account", use_container_width=True,
                                         type="primary"):
                    if not (reg_email and reg_pw and reg_name):
                        st.error("Please complete all fields.")
                    elif reg_pw != reg_pw2:
                        st.error("Passwords do not match.")
                    elif len(reg_pw) < 6:
                        st.error("Password must be at least 6 characters.")
                    else:
                        ok, msg = sign_up(reg_email, reg_pw, reg_name)
                        (st.success if ok else st.error)(msg)

        with tab_reset:
            with st.form("reset_form"):
                reset_email = st.text_input("Work email")
                if st.form_submit_button("Send reset link", use_container_width=True):
                    if not reset_email:
                        st.error("Please enter your email.")
                    else:
                        ok, msg = reset_password(reset_email)
                        (st.success if ok else st.error)(msg)

        st.markdown('<div class="gf-orline">or</div>', unsafe_allow_html=True)
        if st.button("Continue to demo workspace", use_container_width=True,
                     icon=":material/science:"):
            enter_guest_mode()
            st.rerun()

        st.markdown(
            '<div class="gf-secnote"><span class="si">'
            + icon("lock", 15) +
            '</span> Single-tenant access with row-level isolation. Use synthetic '
            'demonstration data only — do not enter real protected health information.</div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)


def render_user_sidebar() -> None:  # retained for backward compatibility
    return None
