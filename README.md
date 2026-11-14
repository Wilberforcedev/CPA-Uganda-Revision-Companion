# Zaabu Learning Hub

A Python/Flask learning-management prototype for CPA Uganda. It uses CPALMS as a reference for course and resource discovery, topic alignment, and class planning. The interface, examples, sample data and branding are original.

## Included workflows

- Browse four CPA Uganda papers and their learning resources.
- Search courses and resources by keyword and filter by paper.
- Open a course detail view, review its materials and mark resources complete.
- Track course progress from completed resources.
- Add courses to a learner's plan and submit written assignment responses.
- Switch the preview between Student, Tutor and Admin navigation.
- Create sample tutor class sites and assignments.
- Store demo activity in a local SQLite database.

## Run locally

Python 3.10 or newer is recommended.

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python app.py

Open http://127.0.0.1:5000. The application seeds demo records into the zaabu_lms.sqlite3 database on first run. Remove that local database file to reset the demo data.

Set FLASK_SECRET_KEY to a long random value before deployment. Set FLASK_COOKIE_SECURE=1 when serving over HTTPS. FLASK_DEBUG defaults to off; use FLASK_DEBUG=1 only for local development.

## Demo status and production work

The role selector is only a navigation preview, not authentication or authorization. This prototype does not provide real accounts, payments, video hosting, file uploads, email notifications, tutor marking or production access controls. Do not use real student records. Before production, add account management, role-based authorization, database migrations, backups, privacy controls, deployment configuration and a full review of operational security.

All sample questions, notes and student records should be original or supplied with permission. CPALMS is a reference for information architecture and learning workflows; its branding and materials are not included.
