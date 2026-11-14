from datetime import datetime
from pathlib import Path
import sqlite3

from flask import Flask, jsonify, render_template, request, session

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "zaabu_lms.sqlite3"
app = Flask(__name__)
app.secret_key = "change-this-demo-secret-before-deployment"

COURSES = [
    ("P7", "Financial Reporting", "CPA Uganda", "Paper 7", "Build confidence in financial statements, standards and exam technique.", "12 weeks", 68, "FR"),
    ("P12", "Advanced Financial Reporting", "CPA Uganda", "Paper 12", "Work through complex reporting, groups and current reporting issues.", "14 weeks", 42, "AFR"),
    ("P13", "Public Financial Management", "CPA Uganda", "Paper 13", "Connect public-sector accounting, procurement and governance.", "12 weeks", 31, "PFM"),
    ("P18", "Integration of Knowledge", "CPA Uganda", "Paper 18", "Turn case evidence into clear, practical advice for decision-makers.", "10 weeks", 76, "IoK"),
]
RESOURCES = [
    ("IAS 1: Presentation of Financial Statements", "Study note", "P7", "Financial Reporting", "18 min", "A concise guide to statement structure, classification and disclosure."),
    ("Consolidated statement of financial position", "Worked example", "P12", "Advanced Financial Reporting", "32 min", "Follow the group structure, net assets, goodwill and non-controlling interest."),
    ("Budget variances and accountability", "Interactive lesson", "P13", "Public Financial Management", "15 min", "Practise explaining budget variances and the actions they require."),
    ("Zuma Hotels: operating environment", "Case activity", "P18", "Integration of Knowledge", "25 min", "Identify external and internal factors, then connect them to the case."),
    ("IAS 33: diluted earnings per share", "Tutor video", "P12", "Advanced Financial Reporting", "21 min", "Understand the sequence for testing potential ordinary shares."),
    ("Cash flow statement: indirect method", "Practice set", "P7", "Financial Reporting", "28 min", "Classify cash movements and reconcile opening to closing balances."),
]
ASSIGNMENTS = [
    ("IAS 1 presentation checklist", "P7", "2026-11-18", "In progress"),
    ("Group accounts: goodwill and NCI", "P12", "2026-11-21", "Not started"),
    ("Zuma Hotels: board briefing", "P18", "2026-11-24", "In progress"),
]

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def initialise():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS courses (
            code TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
            paper TEXT NOT NULL, description TEXT NOT NULL, duration TEXT NOT NULL,
            progress INTEGER NOT NULL, short_name TEXT NOT NULL
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
                ASSIGNMENTS,
            )
            con.executemany("INSERT OR IGNORE INTO enrollments(user_name, course_code) VALUES (?, ?)",
                            [("Philip", "P7"), ("Philip", "P12"), ("Philip", "P18")])

def rows(sql, params=()):
    with connect() as con:
        return [dict(row) for row in con.execute(sql, params).fetchall()]

def current_user():
    return session.get("user_name", "Philip")

@app.get("/")
def home():
    courses = rows("SELECT * FROM courses ORDER BY code")
    resources = rows("SELECT * FROM resources ORDER BY id")
    assignments = rows("SELECT * FROM assignments ORDER BY due_date")
    with connect() as con:
        enrolled = {r[0] for r in con.execute(
            "SELECT course_code FROM enrollments WHERE user_name = ?", (current_user(),)
        ).fetchall()}
        completed = {r[0] for r in con.execute(
            "SELECT resource_id FROM completions WHERE user_name = ?", (current_user(),)
        ).fetchall()}
        class_sites = [dict(r) for r in con.execute(
            "SELECT * FROM class_sites ORDER BY id DESC LIMIT 4"
        ).fetchall()]
    return render_template(
        "index.html", courses=courses, resources=resources, assignments=assignments,
        role=session.get("role", "student"), enrolled=enrolled, completed=completed,
        class_sites=class_sites, user_name=current_user(),
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
        for item in rows(
            "SELECT code AS id, title, paper AS label, description AS summary, 'Course' AS kind "
            "FROM courses WHERE (? = '' OR title LIKE ? OR paper LIKE ? OR description LIKE ?) "
            "AND (? = '' OR code = ?)",
            (query, pattern, pattern, pattern, paper, paper),
        ):
            found.append(item)
    if kind in {"all", "resources"}:
        for item in rows(
            "SELECT id, title, kind AS label, summary, 'Resource' AS kind FROM resources "
            "WHERE (? = '' OR title LIKE ? OR summary LIKE ? OR course LIKE ?) "
            "AND (? = '' OR code = ?)",
            (query, pattern, pattern, pattern, paper, paper),
        ):
            found.append(item)
    return jsonify(results=found)

@app.post("/api/enroll")
def enroll():
    data = request.get_json(silent=True) or {}
    code = data.get("course_code", "")
    with connect() as con:
        exists = con.execute("SELECT 1 FROM courses WHERE code = ?", (code,)).fetchone()
        if not exists:
            return jsonify(error="Course not found."), 404
        con.execute("INSERT OR IGNORE INTO enrollments(user_name, course_code) VALUES (?, ?)",
                    (current_user(), code))
    return jsonify(ok=True, message="Course added to your learning plan.")

@app.post("/api/complete")
def complete():
    data = request.get_json(silent=True) or {}
    resource_id = data.get("resource_id")
    if not resource_id:
        return jsonify(error="A resource is required."), 400
    with connect() as con:
        exists = con.execute("SELECT 1 FROM resources WHERE id = ?", (resource_id,)).fetchone()
        if not exists:
            return jsonify(error="Resource not found."), 404
        con.execute(
            "INSERT OR IGNORE INTO completions(user_name, resource_id, completed_at) VALUES (?, ?, ?)",
            (current_user(), resource_id, datetime.utcnow().isoformat(timespec="seconds")),
        )
    return jsonify(ok=True, message="Marked complete. Your learning record is updated.")

@app.post("/api/submit")
def submit():
    data = request.get_json(silent=True) or {}
    assignment_id = data.get("assignment_id")
    answer = data.get("answer", "").strip()
    if not answer:
        return jsonify(error="Write a short response before submitting."), 400
    with connect() as con:
        exists = con.execute("SELECT 1 FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
        if not exists:
            return jsonify(error="Assignment not found."), 404
        con.execute(
            "INSERT INTO submissions(user_name, assignment_id, answer, submitted_at) VALUES (?, ?, ?, ?)",
            (current_user(), assignment_id, answer, datetime.utcnow().isoformat(timespec="seconds")),
        )
        con.execute("UPDATE assignments SET status = 'Submitted' WHERE id = ?", (assignment_id,))
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
            (title, cohort, meeting, datetime.utcnow().isoformat(timespec="seconds")),
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
    with connect() as con:
        con.execute(
            "INSERT INTO assignments(title, course, due_date, status, description) VALUES (?, ?, ?, 'Not started', '')",
            (title, course, due_date),
        )
    return jsonify(ok=True, message="Assignment published. Refresh to see it.")

if __name__ == "__main__":
    initialise()
    app.run(debug=True)
