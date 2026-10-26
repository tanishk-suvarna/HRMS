# HRMS AI â€” Multi-tenant HR SaaS platform

A responsive HRMS web app built with React, Vite, Recharts and Lucide, now paired with a tenant-aware FastAPI/PostgreSQL backend foundation.

## Run
Requirements: Node.js 18+ (20+ recommended) and npm.

```bash
npm install
npm run dev
```
Open the URL Vite prints, usually http://localhost:5173.

## Run the real backend locally

The backend uses SQLite by default for a quick local start and PostgreSQL through Docker Compose for a production-like local environment.

### Option A: PostgreSQL with Docker

```bash
set JWT_SECRET=replace-with-a-long-random-value
docker compose up --build
```

This starts PostgreSQL, applies the versioned Alembic migration, and starts the API. The API is then available at http://localhost:8000. Its interactive API documentation is at http://localhost:8000/docs.

PowerShell equivalent:

```powershell
$env:JWT_SECRET = [System.Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }))
docker compose up --build
```

### Option B: Python virtual environment

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Copy `.env.example` to `.env` and set a long random `JWT_SECRET` before using this outside local development.

For local SQLite development, automatic schema creation is enabled. For PostgreSQL or production, schema changes must be made through Alembic:

```bash
cd backend
alembic upgrade head
```

To connect the React app to the backend, copy the root `.env.example` to `.env`, keep `VITE_API_URL=http://localhost:8000`, restart Vite, and sign in with the seeded development account:

```text
Email: neha@northstar.io
Password: Welcome123!
```

When `VITE_API_URL` is not set, the UI runs in local development mode. For company use, always configure the API URL.

### What you need to set up

You do not need to manually create tables. Docker starts PostgreSQL and the API applies the Alembic migrations automatically. For a real deployment you must provide a persistent PostgreSQL database, a secret `JWT_SECRET`, HTTPS, backups, and an object-storage provider for documents.

The simplest Windows setup is:

```powershell
cd "C:\Users\Saisree Elango\Desktop\HRMS_AI_SaaS_Full_Code"
$env:JWT_SECRET = [Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }))
docker compose up --build
```

In another PowerShell window:

```powershell
cd "C:\Users\Saisree Elango\Desktop\HRMS_AI_SaaS_Full_Code"
Copy-Item ".env.example" ".env"
npm install
npm run dev
```

Open `http://localhost:5173`. The initial account is `neha@northstar.io` with password `Welcome123!`. Change this account and password before sharing the system.

Build check:
```bash
npm run build
npm run preview
```

## Core workflow
1. Sign in with any non-empty email/password and choose a role.
2. HR/Admin: Employees â†’ add/edit/remove employee â†’ export CSV.
3. Leave management â†’ create a request â†’ approve/reject it.
4. Projects & tasks â†’ create a project/task â†’ mark a task done.
5. Recruitment â†’ add a candidate and change pipeline stage.
6. Communication â†’ send a message.
7. AI assistant â†’ ask about headcount, pending leave, payroll preview, or projects.
8. Reports & analytics â†’ show charts; switch role using the profile menu.

## Implemented

Frontend role-aware navigation; employee CRUD/search/filter/CSV export; attendance check-in/out and history; leave request and approval workflow; projects/tasks; candidate pipeline; payroll records and configurable payslips; local chat; announcements; rule-based HR assistant; charts/reports; dark mode; responsive layouts.

Backend foundation: organization/workspace provisioning; user accounts; organization memberships; role-aware JWT authentication; PBKDF2 password hashing; tenant-scoped employee and leave endpoints; audit event recording for key writes; CORS configuration; health endpoint; PostgreSQL Docker Compose setup; SQLite development fallback.

Communication uses `GET /messages` and `POST /messages` when the API is configured, so messages are stored by organization and visible to authenticated workspace members. Without the API, messages remain in browser storage and are not shared.

Resume uploads use `POST /resumes` when the API is configured. TXT, Markdown, and PDF files are size-limited, stored with their extracted text, and parsed into email, phone, skills, detected sections, line count, and a text preview. The current parser is deterministic extraction, not a hiring decision; scanned/image-only PDFs require OCR before their text can be extracted.

## Current production-readiness status

The database and authentication foundation is real, but the entire application is not yet production software. PostgreSQL, tenant-aware organizations, memberships, JWT authentication, password hashing, migrations, employee/leave APIs, and audit events are implemented. The frontend company registration flow works against the API.

The remaining product work is substantial: attendance, projects, recruitment, payroll, chat, announcements, and reports still use local development state until their API endpoints are migrated. Invitations, account recovery, billing, notifications, rate limiting, HTTPS, backups, monitoring, automated authorization tests, secure document storage, and deployment configuration are still required before accepting real company data. Do not enter real HR data until those controls are deployed. The AI assistant currently uses a local, deterministic dashboard-aware responder. For a production AI assistant, add a server-side OpenAI or Azure OpenAI integration that sends only authorized, tenant-scoped summaries, redacts sensitive HR data, logs requests, and returns source records or citations with answers. Never expose an AI provider key in the browser.

## How the SaaS tenant model works

Each customer company is an `Organization`. Every user belongs to one or more organizations through a `Membership`, and each membership has a role. Business records such as employees and leave requests carry an `organization_id`.

1. A company owner registers a workspace.
2. The server creates the organization, the first HR/Admin user, and their membership in one transaction.
3. The user signs in and receives a short-lived token containing the user, organization, membership, and role context.
4. Every API request derives the organization from the verified token; the browser never chooses the tenant scope.
5. Every query includes that organization scope, so Company A cannot retrieve Company B's records.
6. The frontend renders the same application shell, but the server returns the current company's data and permitted role.
7. An invitation flow can later add managers and employees as additional memberships without duplicating the application.

This is the standard shared-database, shared-schema SaaS model. It is cost-effective for an early product. PostgreSQL row-level security or separate databases can be added later for higher-isolation enterprise plans.

## Recommended production sequence

1. Finish API migration module by module, starting with employees, leave, and attendance.
2. Add new schema changes as Alembic migrations; never rely on `create_all` in production.
3. Add invitation, organization switching, membership administration, and account recovery.
4. Add server-side authorization tests and cross-tenant access tests.
5. Add object storage for resumes and documents, with signed downloads.
6. Add notifications, background jobs, observability, backups, and deployment secrets.
7. Add real reporting queries and AI features only over authorized backend data.
