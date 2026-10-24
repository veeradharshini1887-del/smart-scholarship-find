"""
app.py  -  Smart Scholarship Finder & Career Guidance System
Run with:  python app.py     then open  http://127.0.0.1:5000/

Security features implemented here
  * Password hashing            (werkzeug generate_password_hash / check_password_hash)
  * Session-based login         (signed Flask session cookie, separate student / admin keys)
  * CSRF protection             (token in every form and in fetch() headers)
  * SQL injection protection    (parameterised queries only - see database.py)
  * Input validation            (server-side for every form and JSON payload)
  * Secure file upload          (extension + size + file signature check, random file names)
  * Error handling              (friendly pages / JSON errors, no stack traces shown)
"""

import math
import os
import re
import secrets
import uuid
from datetime import date, datetime, timedelta
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

import ai_recommendation as ai      # noqa: E402  (after load_dotenv)
import database as db               # noqa: E402

# ---------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
MAX_FILE_BYTES = 2 * 1024 * 1024          # 2 MB per document
ALLOWED_EXTENSIONS = {
    "pdf": [b"%PDF"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
}
APPLICATION_STATUSES = ["Submitted", "Under Review", "Approved", "Rejected"]

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
if not app.config["SECRET_KEY"]:
    raise RuntimeError("SECRET_KEY is missing. Add it to your .env file.")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024     # whole request limit
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.permanent_session_lifetime = timedelta(hours=3)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def _json_default(obj):
    """Dates -> ISO strings so JSON responses are easy for JavaScript to use."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Cannot serialise {type(obj)}")


app.json.default = _json_default


# ---------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------
def _fmt_date(value):
    if not value:
        return ""
    try:
        return ai._to_date(value).strftime("%d-%m-%Y")
    except ValueError:
        return str(value)


app.jinja_env.filters["inr"] = ai.format_inr
app.jinja_env.filters["dmy"] = _fmt_date
app.jinja_env.filters["days_left"] = lambda d: ai.days_left(d)
app.jinja_env.filters["deadline_text"] = lambda d: ai.deadline_text(d)
app.jinja_env.filters["split_list"] = lambda t: [x.strip() for x in str(t or "").split(",") if x.strip()]


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.context_processor
def inject_globals():
    return {
        "logged_in": "student_id" in session,
        "student_name": session.get("student_name"),
        "is_admin": "admin_id" in session,
    }


# ---------------------------------------------------------------------
# Security: CSRF check, headers, error handling
# ---------------------------------------------------------------------
def wants_json():
    return (request.headers.get("X-Requested-With") == "fetch"
            or request.args.get("format") == "json"
            or request.is_json)


@app.before_request
def csrf_protect():
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        expected = session.get("_csrf")
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        if not expected or not sent or not secrets.compare_digest(expected, sent):
            abort(400, "Your session expired or the form was invalid. Refresh the page and try again.")


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


def error_response(code, message):
    if wants_json():
        return jsonify(error=message), code
    return render_template("error.html", code=code, message=message), code


@app.errorhandler(HTTPException)
def handle_http_error(e):
    message = e.description
    if e.code == 413:
        message = "The upload is too large. Each document must be 2 MB or smaller."
    if e.code == 404:
        message = "The page you are looking for does not exist."
    return error_response(e.code, message)


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    app.logger.exception("Unhandled error: %s", e)
    if isinstance(e, db.MySQLError):
        return error_response(500, "Cannot reach the database. Check that MySQL is running and the "
                                   "credentials in your .env file are correct.")
    return error_response(500, "Something went wrong on the server. Please try again.")


# ---------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------
def safe_next(target):
    """Only allow redirects to paths inside this site."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "student_id" not in session:
            if wants_json():
                return jsonify(error="Please log in first."), 401
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            if wants_json():
                return jsonify(error="Admin login required."), 401
            flash("Please log in as admin.", "warning")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapper


STUDENT_COLUMNS = ("student_id, name, email, college, degree, cgpa, family_income, "
                   "community, gender, state")


def get_student(student_id):
    return db.fetch_one(f"SELECT {STUDENT_COLUMNS} FROM student WHERE student_id=%s", (student_id,))


def profile_complete(student):
    fields = ("college", "degree", "cgpa", "family_income", "community", "gender", "state")
    return bool(student) and all(student.get(f) not in (None, "") for f in fields)


def get_documents(student_id):
    row = db.fetch_one("SELECT * FROM document WHERE student_id=%s", (student_id,))
    return row or {}


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------
@app.route("/")
def index():
    deadlines = []
    try:
        rows = db.fetch_all("SELECT * FROM scholarship")
        deadlines = ai.upcoming_deadlines(rows, date.today(), 30)[:4]
    except db.MySQLError:
        flash("Database not reachable yet. Start MySQL and check your .env file.", "warning")
    return render_template("index.html", deadlines=deadlines)


# ---------------------------------------------------------------------
# Registration / login / logout
# ---------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        errors = []
        if not 2 <= len(name) <= 100:
            errors.append("Enter your full name (2 to 100 characters).")
        if not EMAIL_RE.match(email) or len(email) > 150:
            errors.append("Enter a valid email address.")
        if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            errors.append("Password must be at least 8 characters and contain a letter and a number.")
        if password != confirm:
            errors.append("Password and confirmation do not match.")
        if not errors and db.fetch_one("SELECT student_id FROM student WHERE email=%s", (email,)):
            errors.append("An account with this email already exists. Log in instead.")
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", form={"name": name, "email": email})
        student_id, _ = db.execute(
            "INSERT INTO student (name, email, password_hash) VALUES (%s, %s, %s)",
            (name, email, generate_password_hash(password)))
        session.clear()
        session.permanent = True
        session["student_id"] = student_id
        session["student_name"] = name
        flash("Account created. Complete your profile to see matching scholarships.", "success")
        return redirect(url_for("profile"))
    return render_template("register.html", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = safe_next(request.values.get("next"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        row = db.fetch_one("SELECT student_id, name, password_hash FROM student WHERE email=%s", (email,))
        if row and check_password_hash(row["password_hash"], password):
            session.clear()
            session.permanent = True
            session["student_id"] = row["student_id"]
            session["student_name"] = row["name"]
            flash(f"Welcome back, {row['name']}.", "success")
            return redirect(next_url or url_for("recommendations"))
        flash("Incorrect email or password.", "danger")
        return render_template("login.html", email=email, next_url=next_url)
    return render_template("login.html", email="", next_url=next_url)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------
# Student profile
# ---------------------------------------------------------------------
def validate_profile(form):
    data = {k: form.get(k, "").strip() for k in
            ("name", "college", "degree", "cgpa", "family_income", "community", "gender", "state")}
    errors = []
    if not 2 <= len(data["name"]) <= 100:
        errors.append("Student name is required (2 to 100 characters).")
    if not 2 <= len(data["college"]) <= 150:
        errors.append("College name is required (2 to 150 characters).")
    for key, options, label in (("degree", ai.DEGREES, "Degree"), ("community", ai.COMMUNITIES, "Community"),
                                ("gender", ai.GENDERS, "Gender"), ("state", ai.STATES, "State")):
        if data[key] not in options:
            errors.append(f"Choose a valid {label}.")
    try:
        cgpa = float(data["cgpa"])
        if not math.isfinite(cgpa) or not 0 <= cgpa <= 10:
            raise ValueError
    except ValueError:
        errors.append("CGPA must be a number between 0 and 10.")
        cgpa = None
    try:
        income = float(data["family_income"])
        if not math.isfinite(income) or not 0 <= income <= 1_000_000_000:
            raise ValueError
    except ValueError:
        errors.append("Family income must be a positive number (annual, in rupees).")
        income = None
    return data, cgpa, income, errors


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    student = get_student(session["student_id"])
    if student is None:                       # account deleted while logged in
        session.clear()
        return redirect(url_for("login"))
    if request.method == "POST":
        data, cgpa, income, errors = validate_profile(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("profile.html", student={**student, **data}, ai=ai)
        db.execute(
            "UPDATE student SET name=%s, college=%s, degree=%s, cgpa=%s, family_income=%s, "
            "community=%s, gender=%s, state=%s WHERE student_id=%s",
            (data["name"], data["college"], data["degree"], cgpa, income,
             data["community"], data["gender"], data["state"], student["student_id"]))
        session["student_name"] = data["name"]
        flash("Profile saved. Here are the scholarships that match you.", "success")
        return redirect(url_for("recommendations"))
    return render_template("profile.html", student=student, ai=ai)


# ---------------------------------------------------------------------
# Scholarships: browse, recommend, details
# ---------------------------------------------------------------------
@app.route("/scholarships")
def scholarships():
    """Public list of all scholarships (no personal match scores)."""
    q = request.args.get("q", "").strip()
    rows = db.fetch_all("SELECT * FROM scholarship ORDER BY last_date")
    if q:
        rows = [r for r in rows if q.lower() in (r["scholarship_name"] + " " + r["eligibility"]).lower()]
    items = [{"s": r, "m": None} for r in rows]
    applied_ids = set()
    if "student_id" in session:
        applied_ids = {a["scholarship_id"] for a in
                       db.fetch_all("SELECT scholarship_id FROM application WHERE student_id=%s",
                                    (session["student_id"],))}
    if wants_json():
        return jsonify(scholarships=rows)
    return render_template("scholarships.html", mode="browse", items=items, q=q,
                           applied_ids=applied_ids, alerts=[], summary=None, show="all")


@app.route("/recommendations")
@login_required
def recommendations():
    student = get_student(session["student_id"])
    if not profile_complete(student):
        flash("Complete your profile first so the system can match scholarships.", "warning")
        return redirect(url_for("profile"))
    today = date.today()
    rows = db.fetch_all("SELECT * FROM scholarship")
    everything = ai.recommend(student, rows, today)          # closed ones already removed
    show = request.args.get("show", "relevant")
    if show == "eligible":
        items = [r for r in everything if r["m"]["is_eligible"]]
    elif show == "all":
        items = everything
    else:
        show = "relevant"
        items = [r for r in everything if r["m"]["status"] in ("Eligible", "Partially Eligible")]
    applied_ids = {a["scholarship_id"] for a in
                   db.fetch_all("SELECT scholarship_id FROM application WHERE student_id=%s",
                                (student["student_id"],))}
    eligible = [r for r in everything if r["m"]["is_eligible"]]
    summary = {
        "eligible": len(eligible),
        "partial": sum(1 for r in everything if r["m"]["status"] == "Partially Eligible"),
        "amount": sum(r["s"]["amount"] for r in eligible),
    }
    alerts = [d for d in ai.upcoming_deadlines([r["s"] for r in eligible], today, 30)
              if d["s"]["scholarship_id"] not in applied_ids]
    if wants_json():
        return jsonify(student_id=student["student_id"], summary=summary,
                       recommendations=[{**r["s"], "match": r["m"]} for r in items])
    return render_template("scholarships.html", mode="recommend", items=items, q="",
                           applied_ids=applied_ids, alerts=alerts, summary=summary, show=show)


@app.route("/scholarship/<int:scholarship_id>")
def scholarship_details(scholarship_id):
    s = db.fetch_one("SELECT * FROM scholarship WHERE scholarship_id=%s", (scholarship_id,))
    if s is None:
        abort(404)
    match = None
    applied = False
    docs_status = []
    needs_profile = False
    if "student_id" in session:
        student = get_student(session["student_id"])
        if profile_complete(student):
            match = ai.evaluate(student, s)
            docs_status = ai.document_status(s["required_documents"], get_documents(student["student_id"]))
        else:
            needs_profile = True
        applied = db.fetch_one("SELECT application_id FROM application WHERE student_id=%s AND scholarship_id=%s",
                               (session["student_id"], scholarship_id)) is not None
    return render_template("scholarship_details.html", s=s, m=match, applied=applied,
                           docs_status=docs_status, needs_profile=needs_profile)


# ---------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------
def build_application_checks(student, s):
    """Everything the apply step needs to know, plus a list of blocking problems."""
    problems = []
    match = None
    if not profile_complete(student):
        problems.append("Your profile is incomplete.")
    else:
        match = ai.evaluate(student, s)
        if match["is_closed"]:
            problems.append("The last date for this scholarship has passed.")
        elif not match["is_eligible"]:
            problems.append("You do not meet: " + ", ".join(match["failed"]) + ".")
    docs = ai.document_status(s["required_documents"], get_documents(student["student_id"]))
    missing = [d["label"] for d in docs if not d["uploaded"]]
    if missing:
        problems.append("Upload the required documents: " + ", ".join(missing) + ".")
    already = db.fetch_one("SELECT application_id FROM application WHERE student_id=%s AND scholarship_id=%s",
                           (student["student_id"], s["scholarship_id"])) is not None
    if already:
        problems = ["You have already applied for this scholarship."]
    return {"match": match, "docs": docs, "already": already, "problems": problems}


@app.route("/apply/<int:scholarship_id>", methods=["GET", "POST"])
@login_required
def apply(scholarship_id):
    student = get_student(session["student_id"])
    s = db.fetch_one("SELECT * FROM scholarship WHERE scholarship_id=%s", (scholarship_id,))
    if s is None:
        abort(404)
    checks = build_application_checks(student, s)
    if request.method == "POST":
        if checks["problems"]:
            for p in checks["problems"]:
                flash(p, "danger")
            return redirect(url_for("apply", scholarship_id=scholarship_id))
        db.execute("INSERT INTO application (student_id, scholarship_id, application_status, applied_date) "
                   "VALUES (%s, %s, 'Submitted', %s)", (student["student_id"], scholarship_id, date.today()))
        flash(f"Application submitted for {s['scholarship_name']}.", "success")
        return redirect(url_for("tracking"))
    return render_template("application.html", s=s, checks=checks)


@app.route("/applications")
@login_required
def tracking():
    rows = db.fetch_all(
        "SELECT a.application_id, a.application_status, a.applied_date, s.scholarship_id, "
        "s.scholarship_name, s.amount, s.last_date, s.is_demo "
        "FROM application a JOIN scholarship s ON s.scholarship_id = a.scholarship_id "
        "WHERE a.student_id=%s ORDER BY a.applied_date DESC, a.application_id DESC",
        (session["student_id"],))
    if wants_json():
        return jsonify(applications=rows)
    counts = {st: sum(1 for r in rows if r["application_status"] == st) for st in APPLICATION_STATUSES}
    return render_template("tracking.html", applications=rows, counts=counts, statuses=APPLICATION_STATUSES)


# ---------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------
def save_upload(file_storage, student_id):
    """Validate and store one file. Returns the relative path. Raises ValueError with a message."""
    original = file_storage.filename or ""
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("only PDF, JPG or PNG files are allowed")
    content = file_storage.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("file is larger than 2 MB")
    if not content:
        raise ValueError("file is empty")
    if not any(content.startswith(sig) for sig in ALLOWED_EXTENSIONS[ext]):
        raise ValueError("file content does not match its extension")
    folder = os.path.join(UPLOAD_FOLDER, f"student_{student_id}")
    os.makedirs(folder, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.{ext}"          # random name: user input never touches the path
    with open(os.path.join(folder, stored_name), "wb") as fh:
        fh.write(content)
    return f"student_{student_id}/{stored_name}"


def remove_file(relative_path):
    if not relative_path:
        return
    full = os.path.abspath(os.path.join(UPLOAD_FOLDER, relative_path))
    if full.startswith(UPLOAD_FOLDER + os.sep) and os.path.isfile(full):
        os.remove(full)


@app.route("/upload-document", methods=["GET", "POST"])
@login_required
def upload_document():
    student_id = session["student_id"]
    docs = get_documents(student_id)
    if request.method == "POST":
        saved = failed = 0
        for field in ai.DOC_FIELDS:                    # whitelist: safe to use in SQL text below
            f = request.files.get(field)
            if not f or not f.filename:
                continue
            label = ai.DOC_LABELS[field]
            try:
                path = save_upload(f, student_id)
            except ValueError as exc:
                flash(f"{label}: {exc}.", "danger")
                failed += 1
                continue
            if docs:
                db.execute(f"UPDATE document SET {field}=%s WHERE student_id=%s", (path, student_id))
            else:
                db.execute(f"INSERT INTO document (student_id, {field}) VALUES (%s, %s)", (student_id, path))
                docs = {"student_id": student_id}
            remove_file(docs.get(field))
            docs[field] = path
            saved += 1
            flash(f"{label} uploaded.", "success")
        if saved == 0 and failed == 0:
            flash("Choose at least one file to upload.", "warning")
        return redirect(url_for("upload_document"))
    items = [{"field": f, "label": ai.DOC_LABELS[f], "uploaded": bool(docs.get(f))} for f in ai.DOC_FIELDS]
    return render_template("documents.html", items=items)


@app.route("/documents/<field>/view")
@login_required
def view_own_document(field):
    if field not in ai.DOC_FIELDS:
        abort(404)
    path = get_documents(session["student_id"]).get(field)
    if not path:
        abort(404)
    return send_from_directory(UPLOAD_FOLDER, path)


# ---------------------------------------------------------------------
# Career guidance
# ---------------------------------------------------------------------
@app.route("/career-guidance")
def career_guidance():
    default_degree = ""
    if "student_id" in session:
        st = get_student(session["student_id"])
        default_degree = (st or {}).get("degree") or ""
    degree = request.args.get("degree", default_degree)
    if degree not in ai.DEGREES:
        degree = ""
    suggestions = ai.suggested_interests(degree) if degree else []
    interest = request.args.get("interest", "")
    if interest not in ai.CAREER_PATHS:
        interest = suggestions[0] if suggestions and request.args.get("degree") is None and default_degree else ""
    plan = ai.build_career_plan(degree, interest) if degree and interest else None
    if wants_json():
        return jsonify(plan=plan)
    others = [i for i in ai.CAREER_PATHS if i not in suggestions]
    return render_template("career.html", degree=degree, interest=interest, plan=plan, ai=ai,
                           suggestions=suggestions, others=others)


# ---------------------------------------------------------------------
# Admin: login and dashboard
# ---------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        row = db.fetch_one("SELECT admin_id, username, password_hash FROM admin WHERE username=%s", (username,))
        if row and check_password_hash(row["password_hash"], password):
            session.clear()
            session.permanent = True
            session["admin_id"] = row["admin_id"]
            session["admin_name"] = row["username"]
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect admin username or password.", "danger")
    return render_template("admin_login.html")


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    flash("Admin logged out.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    def count(sql):
        return db.fetch_one(sql)["n"]
    stats = {
        "students": count("SELECT COUNT(*) AS n FROM student"),
        "scholarships": count("SELECT COUNT(*) AS n FROM scholarship"),
        "demo": count("SELECT COUNT(*) AS n FROM scholarship WHERE is_demo=1"),
        "applications": count("SELECT COUNT(*) AS n FROM application"),
        "pending": count("SELECT COUNT(*) AS n FROM application WHERE application_status IN ('Submitted','Under Review')"),
    }
    return render_template("admin.html", stats=stats, ai=ai, statuses=APPLICATION_STATUSES)


# ---------------------------------------------------------------------
# Admin API (JSON) - scholarships CRUD
# ---------------------------------------------------------------------
def validate_scholarship(payload, exclude_id=0):
    """Returns (clean_dict, errors_dict)."""
    errors = {}
    clean = {}
    name = str(payload.get("scholarship_name", "")).strip()
    if not 3 <= len(name) <= 150:
        errors["scholarship_name"] = "Name is required (3 to 150 characters)."
    elif db.fetch_one("SELECT scholarship_id FROM scholarship WHERE scholarship_name=%s AND scholarship_id<>%s",
                      (name, exclude_id)):
        errors["scholarship_name"] = "A scholarship with this name already exists."
    clean["scholarship_name"] = name

    def number(key, label, low, high):
        try:
            v = float(payload.get(key, ""))
            if not math.isfinite(v) or not low <= v <= high:
                raise ValueError
            return v
        except (TypeError, ValueError):
            errors[key] = f"{label} must be a number between {low:g} and {high:g}."
            return None

    clean["amount"] = number("amount", "Amount", 0, 1_000_000_000)
    clean["minimum_cgpa"] = number("minimum_cgpa", "Minimum CGPA", 0, 10)
    clean["maximum_income"] = number("maximum_income", "Maximum income", 0, 1_000_000_000)

    elig = str(payload.get("eligibility", "")).strip()
    if not 5 <= len(elig) <= 1000:
        errors["eligibility"] = "Eligibility description is required (5 to 1000 characters)."
    clean["eligibility"] = elig

    for key, allowed, label in (("degree", ai.DEGREES, "Degree"), ("community", ai.COMMUNITIES, "Community"),
                                ("state", ai.STATES, "State")):
        try:
            clean[key] = ai.normalize_choice_list(str(payload.get(key, "")), allowed, label)
        except ValueError as exc:
            errors[key] = str(exc)
    gender = str(payload.get("gender", "All")).strip().title()
    if gender not in ai.SCHOLARSHIP_GENDERS:
        errors["gender"] = "Gender must be All, Male, Female or Other."
    clean["gender"] = gender

    docs = payload.get("required_documents", [])
    if isinstance(docs, str):
        docs = [d.strip() for d in docs.split(",") if d.strip()]
    valid_docs = list(ai.DOC_LABELS.values())
    if not isinstance(docs, list) or not docs or any(d not in valid_docs for d in docs):
        errors["required_documents"] = "Select at least one required document."
    else:
        clean["required_documents"] = ",".join(d for d in valid_docs if d in docs)

    try:
        clean["last_date"] = datetime.strptime(str(payload.get("last_date", "")), "%Y-%m-%d").date()
    except ValueError:
        errors["last_date"] = "Enter a valid last date."

    link = str(payload.get("official_link") or "").strip()
    if link and not re.match(r"^https?://[^\s]+$", link):
        errors["official_link"] = "Link must start with http:// or https://"
    clean["official_link"] = link or None
    clean["is_demo"] = 1 if payload.get("is_demo") in (True, 1, "1", "true", "on") else 0
    return clean, errors


SCHOLARSHIP_COLS = ("scholarship_name", "amount", "eligibility", "minimum_cgpa", "maximum_income", "degree",
                    "community", "gender", "state", "required_documents", "last_date", "official_link", "is_demo")


@app.route("/admin/scholarships", methods=["GET"])
@admin_required
def admin_list_scholarships():
    rows = db.fetch_all("SELECT s.*, (SELECT COUNT(*) FROM application a WHERE a.scholarship_id=s.scholarship_id) "
                        "AS application_count FROM scholarship s ORDER BY s.last_date")
    return jsonify(scholarships=rows)


@app.route("/admin/scholarships", methods=["POST"])
@admin_required
def admin_add_scholarship():
    clean, errors = validate_scholarship(request.get_json(silent=True) or {})
    if errors:
        return jsonify(error="Please correct the highlighted fields.", fields=errors), 422
    new_id, _ = db.execute(
        f"INSERT INTO scholarship ({', '.join(SCHOLARSHIP_COLS)}) VALUES ({', '.join(['%s'] * len(SCHOLARSHIP_COLS))})",
        tuple(clean[c] for c in SCHOLARSHIP_COLS))
    return jsonify(message="Scholarship added.", scholarship_id=new_id), 201


@app.route("/admin/scholarships/<int:scholarship_id>", methods=["PUT"])
@admin_required
def admin_update_scholarship(scholarship_id):
    if not db.fetch_one("SELECT scholarship_id FROM scholarship WHERE scholarship_id=%s", (scholarship_id,)):
        return jsonify(error="Scholarship not found."), 404
    clean, errors = validate_scholarship(request.get_json(silent=True) or {}, exclude_id=scholarship_id)
    if errors:
        return jsonify(error="Please correct the highlighted fields.", fields=errors), 422
    assignments = ", ".join(f"{c}=%s" for c in SCHOLARSHIP_COLS)
    db.execute(f"UPDATE scholarship SET {assignments} WHERE scholarship_id=%s",
               tuple(clean[c] for c in SCHOLARSHIP_COLS) + (scholarship_id,))
    return jsonify(message="Scholarship updated.")


@app.route("/admin/scholarships/<int:scholarship_id>", methods=["DELETE"])
@admin_required
def admin_delete_scholarship(scholarship_id):
    if not db.fetch_one("SELECT scholarship_id FROM scholarship WHERE scholarship_id=%s", (scholarship_id,)):
        return jsonify(error="Scholarship not found."), 404
    n = db.fetch_one("SELECT COUNT(*) AS n FROM application WHERE scholarship_id=%s", (scholarship_id,))["n"]
    if n and request.args.get("force") != "1":
        return jsonify(error=f"{n} application(s) exist for this scholarship.", applications=n), 409
    db.execute("DELETE FROM application WHERE scholarship_id=%s", (scholarship_id,))   # explicit, no reliance on cascade
    db.execute("DELETE FROM scholarship WHERE scholarship_id=%s", (scholarship_id,))
    return jsonify(message="Scholarship deleted.")


@app.route("/admin/scholarships/demo", methods=["DELETE"])
@admin_required
def admin_delete_demo():
    db.execute("DELETE FROM application WHERE scholarship_id IN "
               "(SELECT scholarship_id FROM scholarship WHERE is_demo=1)")
    _, removed = db.execute("DELETE FROM scholarship WHERE is_demo=1")
    return jsonify(message=f"Removed {removed} demo scholarship(s).")


# ---------------------------------------------------------------------
# Admin API - students, applications, documents
# ---------------------------------------------------------------------
@app.route("/admin/students", methods=["GET"])
@admin_required
def admin_students():
    rows = db.fetch_all(f"SELECT {STUDENT_COLUMNS}, created_at FROM student ORDER BY student_id DESC")
    return jsonify(students=rows)


@app.route("/admin/applications", methods=["GET"])
@admin_required
def admin_applications():
    rows = db.fetch_all(
        "SELECT a.application_id, a.application_status, a.applied_date, st.student_id, st.name AS student_name, "
        "st.college, s.scholarship_id, s.scholarship_name "
        "FROM application a JOIN student st ON st.student_id=a.student_id "
        "JOIN scholarship s ON s.scholarship_id=a.scholarship_id ORDER BY a.application_id DESC")
    return jsonify(applications=rows, statuses=APPLICATION_STATUSES)


@app.route("/admin/applications/<int:application_id>", methods=["PUT"])
@admin_required
def admin_update_application(application_id):
    status = str((request.get_json(silent=True) or {}).get("status", ""))
    if status not in APPLICATION_STATUSES:
        return jsonify(error="Invalid status."), 422
    if not db.fetch_one("SELECT application_id FROM application WHERE application_id=%s", (application_id,)):
        return jsonify(error="Application not found."), 404
    db.execute("UPDATE application SET application_status=%s WHERE application_id=%s", (status, application_id))
    return jsonify(message=f"Status changed to {status}.")


@app.route("/admin/documents", methods=["GET"])
@admin_required
def admin_documents():
    rows = db.fetch_all(
        "SELECT st.student_id, st.name, st.email, d.aadhaar, d.income_certificate, d.marksheet, "
        "d.community_certificate, d.updated_at FROM student st JOIN document d ON d.student_id=st.student_id "
        "ORDER BY d.updated_at DESC")
    out = []
    for r in rows:      # send only yes/no flags - never expose server file paths
        out.append({"student_id": r["student_id"], "name": r["name"], "email": r["email"],
                    "updated_at": r["updated_at"], **{f: bool(r[f]) for f in ai.DOC_FIELDS}})
    return jsonify(documents=out)


@app.route("/admin/documents/<int:student_id>/<field>")
@admin_required
def admin_view_document(student_id, field):
    if field not in ai.DOC_FIELDS:
        abort(404)
    path = get_documents(student_id).get(field)
    if not path:
        abort(404)
    return send_from_directory(UPLOAD_FOLDER, path)


# ---------------------------------------------------------------------
if __name__ == "__main__":
    try:
        db.init_admin()
    except Exception as exc:                       # keep the site running so the error is visible
        print(f"[warning] Could not reach MySQL: {exc}\n"
              "          Check that MySQL is running, schema.sql was imported and .env is correct.")
    app.run(host="127.0.0.1", port=5000, debug=os.getenv("FLASK_DEBUG", "0") == "1")
