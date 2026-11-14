from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
import hmac
import os
import re
import secrets
import sqlite3

import click
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("ZAABU_LMS_DB", ROOT / "zaabu_lms.sqlite3"))
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=256 * 1024,
)

COURSES = [
    ("P7", "Financial Reporting", "CPA Uganda", "Paper 7", "Build confidence in financial statements, standards and exam technique.", "12 weeks", 0, "FR"),
    ("P12", "Advanced Financial Reporting", "CPA Uganda", "Paper 12", "Work through complex reporting, groups and current reporting issues.", "14 weeks", 0, "AFR"),
    ("P13", "Public Financial Management", "CPA Uganda", "Paper 13", "Connect public-sector accounting, procurement and governance.", "12 weeks", 0, "PFM"),
    ("P18", "Integration of Knowledge", "CPA Uganda", "Paper 18", "Turn case evidence into clear, practical advice for decision-makers.", "10 weeks", 0, "IoK"),
]
RESOURCES = [
    ("IAS 1: Presentation of Financial Statements", "Study note", "P7", "Financial Reporting", "18 min", "A concise guide to statement structure, classification and disclosure."),
    ("Consolidated statement of financial position", "Worked example", "P12", "Advanced Financial Reporting", "32 min", "Follow the group structure, net assets, goodwill and non-controlling interest."),
    ("Budget variances and accountability", "Interactive lesson", "P13", "Public Financial Management", "15 min", "Practise explaining budget variances and the actions they require."),
    ("Zuma Hotels: operating environment", "Case activity", "P18", "Integration of Knowledge", "25 min", "Identify external and internal factors, then connect them to the case."),
    ("IAS 33: diluted earnings per share", "Tutor video", "P12", "Advanced Financial Reporting", "21 min", "Understand the sequence for testing potential ordinary shares."),
    ("Cash flow statement: indirect method", "Practice set", "P7", "Financial Reporting", "28 min", "Classify cash movements and reconcile opening to closing balances."),
]

def seed_assignments():
    today = date.today()
    return [
        ("IAS 1 presentation checklist", "P7", (today + timedelta(days=4)).isoformat(), "In progress"),
        ("Group accounts: goodwill and NCI", "P12", (today + timedelta(days=7)).isoformat(), "Not started"),
        ("Zuma Hotels: board briefing", "P18", (today + timedelta(days=10)).isoformat(), "In progress"),
    ]

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def ensure_column(con, table, column, declaration):
    existing = {row["name"] for row in con.execute("PRAGMA table_info(" + table + ")")}
    if column not in existing:
        con.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " " + declaration)

def initialise():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student' CHECK(role IN ('student','tutor','admin')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS courses (
            code TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
            paper TEXT NOT NULL, description TEXT NOT NULL, duration TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0, short_name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, kind TEXT NOT NULL,
            code TEXT NOT NULL, course TEXT NOT NULL, duration TEXT NOT NULL, summary TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, course TEXT NOT NULL,
            due_date TEXT NOT NULL, status TEXT NOT NULL, description TEXT DEFAULT '',
            created_by TEXT
        );
        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_name TEXT NOT NULL, course_code TEXT NOT NULL,
            UNIQUE(user_name, course_code)
        );
        CREATE TABLE IF NOT EXISTS completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_name TEXT NOT NULL, resource_id INTEGER NOT NULL,
            completed_at TEXT NOT NULL, UNIQUE(user_name, resource_id)
        );
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_name TEXT NOT NULL, assignment_id INTEGER NOT NULL,
            answer TEXT NOT NULL, submitted_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS class_sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, cohort TEXT NOT NULL,
            meeting TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT
        );
        """)
        ensure_column(con, "assignments", "created_by", "TEXT")
        ensure_column(con, "class_sites", "created_by", "TEXT")
        con.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        if con.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0:
            con.executemany("INSERT INTO courses VALUES (?, ?, ?, ?, ?, ?, ?, ?)", COURSES)
            con.executemany(
                "INSERT INTO resources(title, kind, code, course, duration, summary) VALUES (?, ?, ?, ?, ?, ?)",
                RESOURCES,
            )
            con.executemany(
                "INSERT INTO assignments(title, course, due_date, status) VALUES (?, ?, ?, ?)",
                seed_assignments(),
            )

def rows(sql, params=()):
    with connect() as con:
        return [dict(row) for row in con.execute(sql, params).fetchall()]

def current_user():
    """Load the active account from SQLite so role changes take effect immediately."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return next(iter(rows(
        "SELECT id, display_name, email, role, is_active, created_at FROM users WHERE id = ? AND is_active = 1",
        (user_id,),
    )), None)

def api_error(message, status):
    return jsonify(error=message), status

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            if request.path.startswith("/api/"):
                return api_error("Sign in to continue.", 401)
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def roles_required(*allowed_roles):
    """Require one of the allowed roles, using the account loaded for this request."""
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                if request.path.startswith("/api/"):
                    return api_error("Sign in to continue.", 401)
                return redirect(url_for("login"))
            if user["role"] not in allowed_roles:
                if request.path.startswith("/api/"):
                    return api_error("You do not have permission to do that.", 403)
                return render_template("error.html", code=403, message="You do not have permission to view this page."), 403
            return view(*args, **kwargs)
        return wrapped
    return decorate

def normalize_email(value):
    return value.strip().lower()

def valid_email(value):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))

def new_csrf_token():
    session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]

@app.before_request
def protect_post_requests():
    """Reject state-changing requests without this session's CSRF token."""
    if request.method != "POST":
        return None
    expected = session.get("csrf_token", "")
    supplied = request.headers.get("X-CSRF-Token", "") or request.form.get("csrf_token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        if request.path.startswith("/api/"):
            return api_error("Your session token expired. Refresh the page and try again.", 400)
        return render_template("error.html", code=400, message="Your form expired. Refresh the page and try again."), 400
    return None

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("home"))
    csrf_token = session.setdefault("csrf_token", secrets.token_urlsafe(32))
    if request.method == "GET":
        return render_template("auth.html", mode="login", csrf_token=csrf_token, error="")
    email = normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "")
    user = next(iter(rows("SELECT * FROM users WHERE email = ?", (email,))), None)
    if not user or not user["is_active"] or len(password) > 128 or not check_password_hash(user["password_hash"], password):
        return render_template("auth.html", mode="login", csrf_token=csrf_token,
                               error="Email or password is incorrect."), 401
    session.clear()
    session["user_id"] = user["id"]
    new_csrf_token()
    return redirect(url_for("home"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("home"))
    csrf_token = session.setdefault("csrf_token", secrets.token_urlsafe(32))
    if request.method == "GET":
        return render_template("auth.html", mode="register", csrf_token=csrf_token, error="")
    display_name = request.form.get("display_name", "").strip()
    email = normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "")
    if len(display_name) < 2 or len(display_name) > 80:
        error = "Enter your name using 2 to 80 characters."
    elif len(email) > 254 or not valid_email(email):
        error = "Enter a valid email address."
    elif len(password) < 12 or len(password) > 128:
        error = "Choose a password between 12 and 128 characters."
    else:
        try:
            with connect() as con:
                cursor = con.execute(
                    "INSERT INTO users(display_name, email, password_hash, role, is_active, created_at) "
                    "VALUES (?, ?, ?, 'student', 1, ?)",
                    (display_name, email, generate_password_hash(password), datetime.now(timezone.utc).isoformat(timespec="seconds")),
                )
                user_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            error = "An account with that email already exists."
        else:
            session.clear()
            session["user_id"] = user_id
            new_csrf_token()
            return redirect(url_for("home"))
    return render_template("auth.html", mode="register", csrf_token=csrf_token, error=error), 400

@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.get("/")
@login_required
def home():
    user = current_user()
    user_key = user["email"]
    courses = rows("SELECT * FROM courses ORDER BY code")
    resources = rows("SELECT * FROM resources ORDER BY id")
    with connect() as con:
        if user["role"] == "admin":
            assignments = [dict(r) for r in con.execute("SELECT * FROM assignments ORDER BY due_date").fetchall()]
            class_sites = [dict(r) for r in con.execute("SELECT * FROM class_sites ORDER BY id DESC LIMIT 20").fetchall()]
        elif user["role"] == "tutor":
            assignments = [dict(r) for r in con.execute(
                "SELECT * FROM assignments WHERE created_by IS NULL OR created_by = ? ORDER BY due_date", (user_key,)
            ).fetchall()]
            class_sites = [dict(r) for r in con.execute(
                "SELECT * FROM class_sites WHERE created_by IS NULL OR created_by = ? ORDER BY id DESC LIMIT 20", (user_key,)
            ).fetchall()]
        else:
            assignments = [dict(r) for r in con.execute("SELECT * FROM assignments ORDER BY due_date").fetchall()]
            class_sites = []
        enrolled = {r[0] for r in con.execute(
            "SELECT course_code FROM enrollments WHERE user_name = ?", (user_key,)
        ).fetchall()}
        completed = {r[0] for r in con.execute(
            "SELECT resource_id FROM completions WHERE user_name = ?", (user_key,)
        ).fetchall()}
        submitted = {r[0] for r in con.execute(
            "SELECT DISTINCT assignment_id FROM submissions WHERE user_name = ?", (user_key,)
        ).fetchall()}
        admin_users = []
        if user["role"] == "admin":
            admin_users = [dict(r) for r in con.execute(
                "SELECT id, display_name, email, role, is_active, created_at FROM users ORDER BY display_name"
            ).fetchall()]
    resources_by_course = {}
    for resource in resources:
        resources_by_course.setdefault(resource["code"], []).append(resource)
        resource["completed"] = resource["id"] in completed
    for course in courses:
        course_resources = resources_by_course.get(course["code"], [])
        done = sum(1 for resource in course_resources if resource["id"] in completed)
        course["progress"] = round(done * 100 / len(course_resources)) if course_resources else 0
        course["enrolled"] = course["code"] in enrolled
    for assignment in assignments:
        if assignment["id"] in submitted:
            assignment["status"] = "Submitted"
    upcoming = [a for a in assignments if a["status"] != "Submitted" and a["due_date"] >= date.today().isoformat()]
    next_due = min((a["due_date"] for a in upcoming), default="")
    overall_progress = round(sum(c["progress"] for c in courses) / len(courses)) if courses else 0
    return render_template(
        "index.html", courses=courses, resources=resources, assignments=assignments,
        role=user["role"], enrolled=enrolled, completed=completed, class_sites=class_sites,
        admin_users=admin_users, user=user, csrf_token=session.setdefault("csrf_token", secrets.token_urlsafe(32)),
        active_course_count=len(enrolled), due_count=len(upcoming), next_due_label=next_due,
        overall_progress=overall_progress,
    )

@app.get("/api/search")
@login_required
def search():
    query = request.args.get("q", "").strip()
    kind = request.args.get("kind", "all")
    paper = request.args.get("paper", "")
    pattern = "%" + query + "%"
    found = []
    if kind in {"all", "courses"}:
        found.extend(rows(
            "SELECT code AS id, title, paper AS label, description AS summary, 'Course' AS kind "
            "FROM courses WHERE (? = '' OR title LIKE ? OR paper LIKE ? OR description LIKE ?) "
            "AND (? = '' OR code = ?)",
            (query, pattern, pattern, pattern, paper, paper),
        ))
    if kind in {"all", "resources"}:
        found.extend(rows(
            "SELECT id, title, kind AS label, summary, 'Resource' AS kind FROM resources "
            "WHERE (? = '' OR title LIKE ? OR summary LIKE ? OR course LIKE ?) "
            "AND (? = '' OR code = ?)",
            (query, pattern, pattern, pattern, paper, paper),
        ))
    return jsonify(results=found)

@app.get("/api/courses/<code>")
@login_required
def course_detail(code):
    course = next(iter(rows("SELECT * FROM courses WHERE code = ?", (code,))), None)
    if not course:
        return api_error("Course not found.", 404)
    resources = rows("SELECT * FROM resources WHERE code = ? ORDER BY id", (code,))
    completed = {r["resource_id"] for r in rows(
        "SELECT resource_id FROM completions WHERE user_name = ?", (current_user()["email"],)
    )}
    for resource in resources:
        resource["completed"] = resource["id"] in completed
    course["progress"] = round(sum(r["completed"] for r in resources) * 100 / len(resources)) if resources else 0
    return jsonify(course=course, resources=resources)

@app.post("/api/enroll")
@login_required
def enroll():
    data = request.get_json(silent=True) or {}
    code = data.get("course_code", "")
    with connect() as con:
        if not con.execute("SELECT 1 FROM courses WHERE code = ?", (code,)).fetchone():
            return api_error("Course not found.", 404)
        con.execute("INSERT OR IGNORE INTO enrollments(user_name, course_code) VALUES (?, ?)",
                    (current_user()["email"], code))
    return jsonify(ok=True, message="Course added to your learning plan.")

@app.post("/api/complete")
@login_required
def complete():
    data = request.get_json(silent=True) or {}
    try:
        resource_id = int(data.get("resource_id"))
    except (TypeError, ValueError):
        return api_error("Choose a valid resource.", 400)
    with connect() as con:
        if not con.execute("SELECT 1 FROM resources WHERE id = ?", (resource_id,)).fetchone():
            return api_error("Resource not found.", 404)
        con.execute(
            "INSERT OR IGNORE INTO completions(user_name, resource_id, completed_at) VALUES (?, ?, ?)",
            (current_user()["email"], resource_id, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return jsonify(ok=True, message="Marked complete. Course progress has been updated.")

@app.post("/api/submit")
@login_required
def submit():
    data = request.get_json(silent=True) or {}
    try:
        assignment_id = int(data.get("assignment_id"))
    except (TypeError, ValueError):
        return api_error("Choose a valid assignment.", 400)
    answer = data.get("answer", "").strip()
    if not answer:
        return api_error("Write a short response before submitting.", 400)
    with connect() as con:
        if not con.execute("SELECT 1 FROM assignments WHERE id = ?", (assignment_id,)).fetchone():
            return api_error("Assignment not found.", 404)
        con.execute(
            "INSERT INTO submissions(user_name, assignment_id, answer, submitted_at) VALUES (?, ?, ?, ?)",
            (current_user()["email"], assignment_id, answer, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return jsonify(ok=True, message="Your response has been submitted.")

@app.post("/api/class-sites")
@roles_required("tutor", "admin")
def create_class_site():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    cohort = data.get("cohort", "").strip()
    meeting = data.get("meeting", "").strip()
    if not all((title, cohort, meeting)):
        return api_error("Enter a class name, cohort and meeting time.", 400)
    with connect() as con:
        con.execute(
            "INSERT INTO class_sites(title, cohort, meeting, created_at, created_by) VALUES (?, ?, ?, ?, ?)",
            (title, cohort, meeting, datetime.now(timezone.utc).isoformat(timespec="seconds"), current_user()["email"]),
        )
    return jsonify(ok=True, message="Class site created. Refresh to see it.")

@app.post("/api/assignments")
@roles_required("tutor", "admin")
def create_assignment():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    course = data.get("course", "").strip()
    due_date = data.get("due_date", "").strip()
    if not all((title, course, due_date)):
        return api_error("Enter an assignment title, paper and due date.", 400)
    if not any(course == item[0] for item in COURSES):
        return api_error("Choose a valid CPA paper.", 400)
    try:
        date.fromisoformat(due_date)
    except ValueError:
        return api_error("Enter a valid due date.", 400)
    with connect() as con:
        con.execute(
            "INSERT INTO assignments(title, course, due_date, status, description, created_by) "
            "VALUES (?, ?, ?, 'Not started', '', ?)",
            (title, course, due_date, current_user()["email"]),
        )
    return jsonify(ok=True, message="Assignment published. Refresh to see it.")

@app.post("/api/admin/users/<int:user_id>")
@roles_required("admin")
def update_user(user_id):
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    is_active = data.get("is_active")
    if role not in {"student", "tutor", "admin"} or not isinstance(is_active, bool):
        return api_error("Choose a valid role and account status.", 400)
    with connect() as con:
        target = con.execute("SELECT id, role, is_active FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            return api_error("User not found.", 404)
        removing_admin = target["role"] == "admin" and target["is_active"] and (role != "admin" or not is_active)
        if removing_admin:
            active_admins = con.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1").fetchone()[0]
            if active_admins <= 1:
                return api_error("Keep at least one active administrator.", 409)
        con.execute("UPDATE users SET role = ?, is_active = ? WHERE id = ?", (role, int(is_active), user_id))
    return jsonify(ok=True, message="Account permissions updated.")

@app.cli.command("create-admin")
def create_admin():
    """Create the first administrator account from a secure terminal prompt."""
    email = normalize_email(click.prompt("Administrator email"))
    display_name = click.prompt("Administrator name").strip()
    if not valid_email(email):
        raise click.ClickException("Enter a valid email address.")
    password = click.prompt("Password (minimum 12 characters)", hide_input=True, confirmation_prompt=True)
    if len(password) < 12 or len(password) > 128:
        raise click.ClickException("Password must contain between 12 and 128 characters.")
    try:
        with connect() as con:
            con.execute(
                "INSERT INTO users(display_name, email, password_hash, role, is_active, created_at) "
                "VALUES (?, ?, ?, 'admin', 1, ?)",
                (display_name, email, generate_password_hash(password), datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
    except sqlite3.IntegrityError:
        raise click.ClickException("An account with that email already exists.")
    click.echo("Administrator account created.")

initialise()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
