"""Authentication and authorization helpers using Firebase Admin SDK."""
from __future__ import annotations

from functools import wraps
from typing import Callable, Any

from flask import session, jsonify, redirect, url_for, request

import firebase_admin
from firebase_admin import auth as firebase_auth


# -----------------------------
# VERIFY FIREBASE TOKEN
# -----------------------------
def verify_firebase_token(id_token: str):
    """
    Verifies Firebase Auth ID token.
    Returns decoded user info or None.
    """
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        return decoded_token
    except Exception:
        return None


# -----------------------------
# CURRENT USER
# -----------------------------
def current_user_id() -> str | None:
    return session.get("user_id")


# -----------------------------
# LOGIN REQUIRED
# -----------------------------
def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):

        # CASE 1: already logged in via session
        if session.get("user_id"):
            return view(*args, **kwargs)

        # CASE 2: try Firebase token (API / frontend auth)
        auth_header = request.headers.get("Authorization")

        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split("Bearer ")[1]
            decoded = verify_firebase_token(token)

            if decoded:
                # store minimal session info
                session["user_id"] = decoded["uid"]
                session["firebase_user"] = decoded
                return view(*args, **kwargs)

        # NOT AUTHENTICATED
        if request.path.startswith("/api/"):
            return jsonify({
                "success": False,
                "message": "Authentication required"
            }), 401

        return redirect(url_for("login_page"))

    return wrapped


# -----------------------------
# ROLE REQUIRED
# -----------------------------
def role_required(*roles: str):
    """Require one of the given roles for a view."""
    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):

            user = session.get("user")

            # fallback: try firebase user
            if not user and session.get("firebase_user"):
                fb = session["firebase_user"]
                user = {
                    "id": fb.get("uid"),
                    "role": fb.get("role", "student")  # default fallback
                }

            if not user or user.get("role") not in roles:
                if request.path.startswith("/api/"):
                    return jsonify({
                        "success": False,
                        "message": "Access denied"
                    }), 403
                return redirect(url_for("login_page"))

            return view(*args, **kwargs)

        return wrapped
    return decorator
