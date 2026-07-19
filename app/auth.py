"""
Authentication module for BioShield AI.

Provides email/password and Google OAuth 2.0 login via Supabase Auth.
Manages Streamlit session state for the authenticated user.
"""

from __future__ import annotations

import streamlit as st

try:
    # supabase >= 2.15 renamed the auth package gotrue → supabase_auth
    from supabase_auth.errors import AuthApiError
except ImportError:  # pragma: no cover - older supabase installs
    from gotrue.errors import AuthApiError

from app.supabase_client import get_supabase
from app.icons import icon


# ─── Session helpers ─────────────────────────────────────────────────────────

def get_current_user() -> dict | None:
    """Return the current authenticated user dict from session state, or None."""
    return st.session_state.get("user")


def is_authenticated() -> bool:
    """Check if a user is currently logged in (includes guest/demo sessions)."""
    return get_current_user() is not None


def is_guest() -> bool:
    """True if the current session is a no-login demo/guest session."""
    user = get_current_user()
    return bool(user and user.get("is_guest"))


def enter_guest_mode() -> None:
    """Start a local demo session with no Supabase account.

    Lets judges/reviewers use the tool with zero setup. Guest sessions never
    touch Supabase (no profile, no persistence) — everything stays in-memory.
    """
    st.session_state["user"] = {
        "id": "guest",
        "email": "guest@localhost",
        "user_metadata": {"full_name": "Guest (demo)"},
        "is_guest": True,
    }
    st.session_state["session"] = None
    st.session_state["access_token"] = None


def _set_session(user: dict, session: dict) -> None:
    """Store user and session in Streamlit session state."""
    st.session_state["user"] = user
    st.session_state["session"] = session
    st.session_state["access_token"] = session.get("access_token")


def _clear_session() -> None:
    """Clear auth + app state from the session (fresh slate on next login)."""
    for key in (
        "user", "session", "access_token",
        "guest_patients", "guest_records",
        "_pdf_done", "_pdf_msg", "_clear_new_patient",
    ):
        st.session_state.pop(key, None)


# ─── Email/Password Auth ─────────────────────────────────────────────────────

def sign_up(email: str, password: str, full_name: str) -> tuple[bool, str]:
    """
    Register a new user with email and password.
    Returns (success: bool, message: str).
    """
    try:
        supabase = get_supabase()
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"full_name": full_name}},
        })
        if response.user:
            return True, "Account created! Check your email to confirm your address."
        return False, "Sign-up failed. Please try again."
    except AuthApiError as e:
        return False, str(e)
    except RuntimeError as e:
        # e.g. Supabase not configured — guide the user to the guest demo path.
        return False, f"{e}  (Tip: use 'Continue as guest' to explore without setup.)"


def sign_in(email: str, password: str) -> tuple[bool, str]:
    """
    Sign in with email and password.
    Returns (success: bool, message: str).
    """
    try:
        supabase = get_supabase()
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        if response.user and response.session:
            _set_session(
                user=response.user.model_dump(),
                session=response.session.model_dump(),
            )
            return True, "Signed in successfully."
        return False, "Invalid credentials."
    except AuthApiError as e:
        return False, str(e)
    except RuntimeError as e:
        # e.g. Supabase not configured — guide the user to the guest demo path.
        return False, f"{e}  (Tip: use 'Continue as guest' to explore without setup.)"


def sign_out() -> None:
    """Sign out the current user and clear app state.

    Guests never had a Supabase session, so we skip the server-side logout for
    them (avoids an unnecessary network round-trip on the way out).
    """
    if not is_guest():
        try:
            get_supabase().auth.sign_out()
        except Exception:
            pass
    _clear_session()


def reset_password(email: str) -> tuple[bool, str]:
    """
    Send a password reset email.
    Returns (success: bool, message: str).
    """
    try:
        supabase = get_supabase()
        supabase.auth.reset_password_email(email)
        return True, "Password reset email sent. Check your inbox."
    except AuthApiError as e:
        return False, str(e)
    except RuntimeError as e:
        # e.g. Supabase not configured — guide the user to the guest demo path.
        return False, f"{e}  (Tip: use 'Continue as guest' to explore without setup.)"


# ─── Google OAuth 2.0 ────────────────────────────────────────────────────────

def get_google_login_url() -> str | None:
    """
    Get the Google OAuth sign-in URL from Supabase.
    Returns the redirect URL or None on failure.
    """
    try:
        supabase = get_supabase()
        response = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {"redirect_to": _get_redirect_url()},
        })
        return response.url
    except Exception:
        return None


def handle_oauth_code(code: str) -> tuple[bool, str]:
    """
    Exchange a PKCE authorization `code` (returned as a ?code= query param after
    Google sign-in) for a Supabase session. Returns (success, message).
    """
    try:
        supabase = get_supabase()
        response = supabase.auth.exchange_code_for_session({"auth_code": code})
        if response.user and response.session:
            _set_session(
                user=response.user.model_dump(),
                session=response.session.model_dump(),
            )
            return True, "Signed in with Google."
        return False, "OAuth exchange failed."
    except AuthApiError as e:
        return False, str(e)
    except RuntimeError as e:
        # e.g. Supabase not configured — guide the user to the guest demo path.
        return False, f"{e}  (Tip: use 'Continue as guest' to explore without setup.)"


def _get_redirect_url() -> str:
    """Build the OAuth redirect URL based on the current Streamlit app URL."""
    import os
    return os.environ.get("OAUTH_REDIRECT_URL", "http://localhost:8501")


# ─── Auth UI Components ──────────────────────────────────────────────────────

def render_login_page() -> None:
    """Render the login/register UI. Call this when user is not authenticated."""
    # Center everything in a narrow card-like column.
    _left, mid, _right = st.columns([1, 1.25, 1])

    with mid:
        st.markdown(
            '<div class="gf-login">'
            f'<div class="gf-hero-mark gf-login-mark">{icon("shield-check", 28)}</div>'
            '<h1 class="gf-login-title gf-wordmark">BioShield AI</h1>'
            '<div class="gf-pill">Defensive prototype</div>'
            '<div class="gf-hero-sub gf-login-sub">Calibrated antibiotic-resistance '
            'prediction for <em>Staphylococcus aureus</em>.</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="gf-login-hint">Sign in to manage your patients and keep a '
            'history of every analysis.</div>',
            unsafe_allow_html=True,
        )

        tab_login, tab_register, tab_reset = st.tabs(["Sign In", "Register", "Reset"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email", placeholder="you@hospital.org")
                password = st.text_input("Password", type="password", placeholder="••••••••")
                submitted = st.form_submit_button("Sign In", use_container_width=True)
                if submitted:
                    if not email or not password:
                        st.error("Please enter both email and password.")
                    else:
                        success, msg = sign_in(email, password)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

        with tab_register:
            with st.form("register_form"):
                reg_name = st.text_input("Full Name")
                reg_email = st.text_input("Email")
                reg_password = st.text_input("Password", type="password")
                reg_password2 = st.text_input("Confirm Password", type="password")
                submitted = st.form_submit_button("Create Account", use_container_width=True)
                if submitted:
                    if not reg_email or not reg_password or not reg_name:
                        st.error("Please fill in all fields.")
                    elif reg_password != reg_password2:
                        st.error("Passwords do not match.")
                    elif len(reg_password) < 6:
                        st.error("Password must be at least 6 characters.")
                    else:
                        success, msg = sign_up(reg_email, reg_password, reg_name)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)

        with tab_reset:
            with st.form("reset_form"):
                reset_email = st.text_input("Email")
                submitted = st.form_submit_button("Send Reset Link", use_container_width=True)
                if submitted:
                    if not reset_email:
                        st.error("Please enter your email.")
                    else:
                        success, msg = reset_password(reset_email)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)

        st.markdown('<div class="gf-or"><span>or</span></div>', unsafe_allow_html=True)
        if st.button("Continue as guest (demo — records aren't saved)", use_container_width=True):
            enter_guest_mode()
            st.rerun()
        st.markdown(
            '<div class="gf-login-foot">Research prototype — confirm every result with '
            'standard laboratory testing.</div>',
            unsafe_allow_html=True,
        )


def render_user_sidebar() -> None:
    """Render user info and sign-out button in the sidebar."""
    user = get_current_user()
    if not user:
        return

    with st.sidebar:
        st.divider()
        user_meta = user.get("user_metadata", {})
        display_name = user_meta.get("full_name") or user.get("email", "User")
        st.markdown(f"**Signed in as:** {display_name}")
        st.caption(user.get("email", ""))
        if st.button("Sign Out", key="btn_sign_out", use_container_width=True):
            sign_out()
            st.rerun()
