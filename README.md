# Zaabu Learning Hub

A Python/Flask learning-management prototype for CPA Uganda. It uses CPALMS as a reference for course and resource discovery, topic alignment, and class planning. The interface, examples, sample data and branding are original.

## Features

- Student registration and sign-in with password hashing.
- Server-side authorization for Student, Tutor and Admin roles.
- Students can enroll, complete resources and submit assignment responses.
- Tutors and admins can create class sites and assignments.
- Admins can assign roles, disable accounts and manage users.
- Course and resource search, course detail views and completion-based progress.
- Local SQLite storage and CSRF protection for form and API writes.

## Run locally

Python 3.10 or newer is recommended.

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    flask --app app create-admin

The command prompts securely for the first administrator’s email, name and password. Start the local server:

    python app.py

Open http://127.0.0.1:5000. Students can create accounts from the sign-in page. An administrator can change a student to Tutor or Admin in User management.

## Configuration

Set FLASK_SECRET_KEY to a long random value that stays the same between restarts. Set FLASK_COOKIE_SECURE=1 when serving over HTTPS. FLASK_DEBUG defaults to off; use FLASK_DEBUG=1 only for local development. ZAABU_LMS_DB can point to a different SQLite database file.

## Permissions

- Student: browse courses/resources, enroll, record completions and submit assignments.
- Tutor: student learning actions plus class-site and assignment creation.
- Admin: tutor permissions plus user role and account management.

Registration always creates a Student account. The first administrator is created from the terminal. The admin screen prevents removal or deactivation of the last active administrator.

## Production work still needed

This remains a prototype. Before using real student data, add email verification and password recovery, login throttling, multi-factor authentication, secure deployment and backups, database migrations, privacy controls, and a security review. The built-in development server is not intended for production hosting.

Use only original or properly licensed learning materials. CPALMS is a reference for information architecture and learning workflows; its branding and materials are not included.
