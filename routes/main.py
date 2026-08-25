import io
import os
import re
import secrets
import requests
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for, send_file
from werkzeug.utils import secure_filename

from models.models import (
    check_user_password, create_or_update_google_user, create_user,
    get_connection, get_user_by_email, record_login,
    list_users_with_login_stats, list_login_events, list_user_login_events,
)

main_bp = Blueprint("main", __name__)


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf(token):
    expected = session.get("csrf_token", "")
    return bool(token and expected and secrets.compare_digest(str(token), str(expected)))


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_connection()
    try:
        row = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def login_required_api(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            next_url = request.headers.get("Referer") or url_for("main.index")
            return jsonify({
                "error": "Please create an account or log in to use AI features.",
                "auth_required": True,
                "login_url": url_for("main.login", next=next_url),
            }), 401
        if not validate_csrf(request.headers.get("X-CSRF-Token")):
            return jsonify({"error": "Your session expired. Refresh the page and try again."}), 400
        return f(*args, **kwargs)
    return wrapped


def safe_next(value):
    if not value:
        return url_for("main.index")
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return url_for("main.index")
    return value if value.startswith("/") else url_for("main.index")


@main_bp.app_context_processor
def inject_user():
    return {"current_user": current_user(), "config": current_app.config, "csrf_token": csrf_token()}


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/calculators")
def calculators():
    return render_template("calculators.html")


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(safe_next(request.args.get("next") or request.form.get("next")))
    next_url = safe_next(request.args.get("next") or request.form.get("next"))
    if request.method == "POST":
        if not validate_csrf(request.form.get("csrf_token")):
            flash("Your session expired. Please refresh the page and try again.", "error")
            return render_template("auth.html", mode="login", next_url=next_url)
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_user_by_email(email)
        if not user or not check_user_password(user, password):
            flash("Incorrect email or password.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user.get("name") or email.split("@")[0]
            record_login(user["id"], "email", request.remote_addr or "", request.headers.get("User-Agent", ""))
            return redirect(next_url)
    return render_template("auth.html", mode="login", next_url=next_url)


@main_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user_id"):
        return redirect(url_for("main.index"))
    next_url = safe_next(request.args.get("next") or request.form.get("next"))
    if request.method == "POST":
        if not validate_csrf(request.form.get("csrf_token")):
            flash("Your session expired. Please refresh the page and try again.", "error")
            return render_template("auth.html", mode="signup", next_url=next_url)
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        errors = []
        if not name: errors.append("Name is required.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email): errors.append("Enter a valid email address.")
        if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            errors.append("Password must be at least 8 characters and contain a letter and a number.")
        if password != confirm: errors.append("Passwords do not match.")
        if get_user_by_email(email): errors.append("An account with that email already exists.")
        if errors:
            for error in errors: flash(error, "error")
        else:
            user = create_user(name, email, password)
            if not user:
                flash("An account with that email already exists.", "error")
            else:
                session.clear()
                session["user_id"] = user["id"]
                session["user_name"] = user["name"]
                record_login(user["id"], "signup", request.remote_addr or "", request.headers.get("User-Agent", ""))
                return redirect(next_url)
    return render_template("auth.html", mode="signup", next_url=next_url)


@main_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.index"))


@main_bp.route("/auth/google")
def google_login():
    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    client_secret = current_app.config.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        current_app.logger.error("Google OAuth is unavailable: GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET are missing")
        flash("Google sign-in is temporarily unavailable. Please use email and password, or try again later.", "error")
        return redirect(url_for("main.login", next=safe_next(request.args.get("next"))))
    session["google_state"] = secrets.token_urlsafe(32)
    session["auth_next"] = safe_next(request.args.get("next"))
    params = {
        "client_id": client_id,
        "redirect_uri": current_app.config.get("GOOGLE_REDIRECT_URI") or url_for("main.google_callback", _external=True),
        "response_type": "code",
        "scope": "openid email profile",
        "state": session["google_state"],
        "access_type": "online",
        "prompt": "select_account",
    }
    from urllib.parse import urlencode
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@main_bp.route("/auth/google/callback")
def google_callback():
    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    client_secret = current_app.config.get("GOOGLE_CLIENT_SECRET")
    next_url = safe_next(session.get("auth_next", url_for("main.index")))
    if not client_id or not client_secret:
        current_app.logger.error("Google OAuth callback reached without configured credentials")
        return redirect(url_for("main.login", next=next_url))
    if not secrets.compare_digest(request.args.get("state", ""), session.pop("google_state", "")):
        flash("Google sign-in could not be verified. Please try again.", "error")
        return redirect(url_for("main.login", next=next_url))
    code = request.args.get("code")
    if not code:
        flash("Google sign-in was cancelled or failed.", "error")
        return redirect(url_for("main.login", next=next_url))
    try:
        token_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": current_app.config.get("GOOGLE_REDIRECT_URI") or url_for("main.google_callback", _external=True),
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()
        id_token = tokens.get("id_token")
        if not id_token:
            raise ValueError("Google did not return an ID token")
        verify = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token}, timeout=10)
        verify.raise_for_status()
        info = verify.json()
        if info.get("aud") != client_id or info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise ValueError("Invalid Google token audience or issuer")
        if str(info.get("email_verified", "")).lower() != "true":
            raise ValueError("Google email is not verified")
        email = (info.get("email") or "").strip().lower()
        google_id = str(info.get("sub") or "")
        if not email or not google_id:
            raise ValueError("Google account information is incomplete")
        user = create_or_update_google_user(email, info.get("name") or email.split("@")[0], google_id)
        if not user:
            raise ValueError("Could not create Google user")
        next_url = safe_next(session.get("auth_next", url_for("main.index")))
        session.clear()
        session["user_id"] = user["id"]
        session["user_name"] = user.get("name") or email.split("@")[0]
        record_login(user["id"], "google", request.remote_addr or "", request.headers.get("User-Agent", ""))
        return redirect(next_url)
    except (requests.RequestException, ValueError, KeyError):
        current_app.logger.exception("Google OAuth callback failed")
        flash("Google sign-in could not be completed. Please try again.", "error")
        return redirect(url_for("main.login"))




def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        user = current_user()
        allowed = {email.strip().lower() for email in current_app.config.get("ADMIN_EMAILS", "").split(",") if email.strip()}
        if not user or user.get("email", "").lower() not in allowed:
            if not user:
                return redirect(url_for("main.login", next=request.path))
            return (render_template("404.html"), 404)
        return f(*args, **kwargs)
    return wrapped


@main_bp.route("/admin/users")
@admin_required
def admin_users():
    users = list_users_with_login_stats()
    login_events = list_login_events(200)
    return render_template("admin_users.html", users=users, login_events=login_events)

@main_bp.route("/profile")
def profile():
    user = current_user()
    if not user:
        return redirect(url_for("main.login", next=url_for("main.profile")))
    return render_template("profile.html", user=user)


@main_bp.route("/activity")
def activity():
    user = current_user()
    if not user:
        return redirect(url_for("main.login", next=url_for("main.activity")))
    return render_template("activity.html", user=user, login_events=list_user_login_events(user["id"], 50))


@main_bp.route("/timetable")
def timetable():
    return render_template("timetable.html")


@main_bp.route("/resume-builder")
def resume_builder():
    return render_template("resume.html")


@main_bp.route("/notes")
def notes():
    return render_template("notes.html")


@main_bp.route("/pdf-tools")
def pdf_tools():
    return render_template("pdf_tools.html")


@main_bp.route("/api/pdf/merge", methods=["POST"])
def merge_pdfs():
    try:
        from pypdf import PdfReader, PdfWriter
        files = request.files.getlist("files")
        files = [f for f in files if f and f.filename.lower().endswith(".pdf")]
        if len(files) < 2:
            return jsonify({"error": "Choose at least two PDF files."}), 400
        writer = PdfWriter()
        for uploaded in files:
            reader = PdfReader(uploaded.stream)
            for page in reader.pages:
                writer.add_page(page)
        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        return send_file(output, mimetype="application/pdf", as_attachment=True, download_name="student-hub-merged.pdf")
    except ImportError:
        return jsonify({"error": "PDF support is not installed. Run pip install -r requirements.txt."}), 503
    except Exception:
        current_app.logger.exception("PDF merge failed")
        return jsonify({"error": "We couldn't merge those PDFs. Make sure they are valid PDF files."}), 400


@main_bp.route("/api/pdf/extract", methods=["POST"])
def extract_pdf():
    try:
        from pypdf import PdfReader
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Choose a PDF file first."}), 400
        reader = PdfReader(uploaded.stream)
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
        return jsonify({"filename": secure_filename(uploaded.filename), "pages": len(reader.pages), "text": text})
    except ImportError:
        return jsonify({"error": "PDF support is not installed. Run pip install -r requirements.txt."}), 503
    except Exception:
        current_app.logger.exception("PDF extraction failed")
        return jsonify({"error": "We couldn't read that PDF. It may be encrypted or invalid."}), 400
