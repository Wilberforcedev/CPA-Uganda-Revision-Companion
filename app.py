from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import hmac
import os
import secrets
import sqlite3

from flask import Flask, jsonify, render_template, request, session

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

def initialise():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript("""
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
            due_date TEXT NOT NULL, status TEXT NOT NULL, description TEXT DEFAULT ''
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
            meeting TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """)
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
            con.executemany(
                "INSERT OR IGNORE INTO enrollments(user_name, course_code) VALUES (?, ?)",
                [("Philip", "P7"), ("Philip", "P12"), ("Philip", "P18")],
            )

def rows(sql, params=()):
    with connect() as con:
        return [dict(row) for row in con.execute(sql, params).fetchall()]

def current_user():
    return session.get("user_name", "Philip")

@app.before_request
def protect_post_requests():
    if request.method != "POST":
        return None
    expected = session.get("csrf_token", "")
    supplied = request.headers.get("X-CSRF-Token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        return jsonify(error="Your session token expired. Refresh the page and try again."), 400
    return None

@app.get("/")
def home():
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    user = current_user()
    courses = rows("SELECT * FROM courses ORDER BY code")
    resources = rows("SELECT * FROM resources ORDER BY id")
    assignments = rows("SELECT * FROM assignments ORDER BY due_date")
    with connect() as con:
        enrolled = {r[0] for r in con.execute(
            "SELECT course_code FROM enrollments WHERE user_name = ?", (user,)
        ).fetchall()}
        completed = {r[0] for r in con.execute(
            "SELECT resource_id FROM completions WHERE user_name = ?", (user,)
        ).fetchall()}
        submitted = {r[0] for r in con.execute(
            "SELECT DISTINCT assignment_id FROM submissions WHERE user_name = ?", (user,)
        ).fetchall()}
        class_sites = [dict(r) for r in con.execute(
            "SELECT * FROM class_sites ORDER BY id DESC LIMIT 4"
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
        role=session.get("role", "student"), enrolled=enrolled, completed=completed,
        class_sites=class_sites, user_name=user, csrf_token=session["csrf_token"],
        active_course_count=len(enrolled), due_count=len(upcoming),
        next_due_label=next_due, overall_progress=overall_progress,
    )

@app.post("/api/role")
def set_role():
    data = request.get_json(silent=True) or {}
    role = data.get("role", "student")
    if role not in {"student", "tutor", "admin"}:
        return jsonify(error="Choose student, tutor or admin."), 400
    session["role"] = role
    return jsonify(role=role)

@app.get("/api/search")
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
def course_detail(code):
    course = next(iter(rows("SELECT * FROM courses WHERE code = ?", (code,))), None)
    if not course:
        return jsonify(error="Course not found."), 404
    resources = rows("SELECT * FROM resources WHERE code = ? ORDER BY id", (code,))
    completed = {r["resource_id"] for r in rows(
        "SELECT resource_id FROM completions WHERE user_name = ?", (current_user(),)
    )}
    for resource in resources:
        resource["completed"] = resource["id"] in completed
    course_resources = len(resources)
    course["progress"] = round(sum(r["completed"] for r in resources) * 100 / course_resources) if course_resources else 0
    return jsonify(course=course, resources=resources)

@app.post("/api/enroll")
def enroll():
    data = request.get_json(silent=True) or {}
    code = data.get("course_code", "")
    with connect() as con:
        if not con.execute("SELECT 1 FROM courses WHERE code = ?", (code,)).fetchone():
            return jsonify(error="Course not found."), 404
        con.execute("INSERT OR IGNORE INTO enrollments(user_name, course_code) VALUES (?, ?)",
                    (current_user(), code))
    return jsonify(ok=True, message="Course added to your learning plan.")

@app.post("/api/complete")
def complete():
    data = request.get_json(silent=True) or {}
    try:
        resource_id = int(data.get("resource_id"))
    except (TypeError, ValueError):
        return jsonify(error="Choose a valid resource."), 400
    with connect() as con:
        if not con.execute("SELECT 1 FROM resources WHERE id = ?", (resource_id,)).fetchone():
            return jsonify(error="Resource not found."), 404
        con.execute(
            "INSERT OR IGNORE INTO completions(user_name, resource_id, completed_at) VALUES (?, ?, ?)",
            (current_user(), resource_id, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return jsonify(ok=True, message="Marked complete. Course progress has been updated.")

@app.post("/api/submit")
def submit():
    data = request.get_json(silent=True) or {}
    try:
        assignment_id = int(data.get("assignment_id"))
    except (TypeError, ValueError):
        return jsonify(error="Choose a valid assignment."), 400
    answer = data.get("answer", "").strip()
    if not answer:
        return jsonify(error="Write a short response before submitting."), 400
    with connect() as con:
        if not con.execute("SELECT 1 FROM assignments WHERE id = ?", (assignment_id,)).fetchone():
            return jsonify(error="Assignment not found."), 404
        con.execute(
            "INSERT INTO submissions(user_name, assignment_id, answer, submitted_at) VALUES (?, ?, ?, ?)",
            (current_user(), assignment_id, answer, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return jsonify(ok=True, message="Your response has been submitted.")

@app.post("/api/class-sites")
def create_class_site():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    cohort = data.get("cohort", "").strip()
    meeting = data.get("meeting", "").strip()
    if not all((title, cohort, meeting)):
        return jsonify(error="Enter a class name, cohort and meeting time."), 400
    with connect() as con:
        con.execute(
            "INSERT INTO class_sites(title, cohort, meeting, created_at) VALUES (?, ?, ?, ?)",
            (title, cohort, meeting, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return jsonify(ok=True, message="Class site created. Refresh to see it.")

@app.post("/api/assignments")
def create_assignment():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    course = data.get("course", "").strip()
    due_date = data.get("due_date", "").strip()
    if not all((title, course, due_date)):
        return jsonify(error="Enter an assignment title, paper and due date."), 400
    if not any(course == item[0] for item in COURSES):
        return jsonify(error="Choose a valid CPA paper."), 400
    try:
        date.fromisoformat(due_date)
    except ValueError:
        return jsonify(error="Enter a valid due date."), 400
    with connect() as con:
        con.execute(
            "INSERT INTO assignments(title, course, due_date, status, description) VALUES (?, ?, ?, 'Not started', '')",
            (title, course, due_date),
        )
    return jsonify(ok=True, message="Assignment published. Refresh to see it.")

initialise()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
