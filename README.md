# Zaabu Learning Hub

A Python/Flask learning-management prototype for CPA Uganda. The public discovery and planning patterns take inspiration from CPALMS: browseable course and learning-resource catalogs, clear topic alignment, and tools for tutors to organize classes and assignments. The interface, examples, data and branding here are original.

## Features in this prototype

- Browse four CPA Uganda papers and their study resources.
- Search courses and resources by keyword and filter by paper.
- Add courses to a learner's plan and mark resources complete.
- Submit written assignment responses.
- Preview Student, Tutor and Admin navigation.
- Create sample tutor class sites and assignments.
- Store demo activity in a local SQLite database.

## Run locally

Python 3.10 or newer is recommended.

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python app.py

Open http://127.0.0.1:5000. The application seeds demo records into \`zaabu_lms.sqlite3\` on first run. Remove that local database file to reset the demo data.

## Demo status and next steps

The role selector is only a preview switch. This prototype does not provide real authentication, payments, video hosting, file uploads, email notifications, or production access controls. Do not use real student records. Before production, add secure account management, authorization checks on every write action, CSRF protection, migrations, backups, privacy controls and deployment configuration.

All sample questions, notes and student records should be original or supplied with permission. CPALMS is a reference for information architecture and learning workflows; its branding and materials are not included.
