# Shared Expenses App

A full-stack shared expenses tracker built for the Spreetail internship take-home assignment. Handles group expense splitting (equal/unequal/percentage/share), multi-currency support, time-bounded group membership, debt settlement, and a CSV/XLSX import pipeline with automated anomaly detection.

## Tech Stack

- **Backend:** Django 6, Django REST Framework, SimpleJWT, PostgreSQL 18, psycopg3
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS v4
- **Deployment:** Railway (backend + Postgres), Vercel (frontend)

## AI Tool Used

Claude (Anthropic) was used as the primary development collaborator throughout this project — architecture design, code generation, debugging, and documentation. See `AI_USAGE.md` for details, prompts, and specific cases where AI output was wrong and corrected.

## Local Setup

### Prerequisites
- Python 3.12+
- Node.js 18+
- PostgreSQL 18 (or Docker)

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\Activate.ps1        # Windows
pip install -r requirements.txt
```

Create `backend/.env` (see `.env.example` for the full list):
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=True
DB_NAME=shared_expenses_db
DB_USER=shared_expenses_user
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:5173

Create the Postgres database and user (see `SCOPE.md` for exact SQL), then:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo_data      # optional: creates a realistic demo group
python manage.py test                # run backend test suite
python manage.py runserver
```

**Note:** Django's test runner needs `CREATEDB` privilege on the Postgres user:
```sql
ALTER USER shared_expenses_user CREATEDB;
```

### Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env`:
VITE_API_URL=http://127.0.0.1:8000/api

```bash
npm run dev
```

Visit `http://localhost:5173`.

## Importing the Sample Data

1. Log in (or register a new account, or use a seeded user like `Aisha` / `testpass123` after running `seed_demo_data`)
2. Open a group → **Import** tab
3. Upload `sample_data/expenses_export.xlsx`
4. Review flagged rows (each shows the detected anomaly and severity)
5. Approve/reject rows needing manual review
6. Click **Commit Import**

See `SCOPE.md` for the full anomaly catalog and handling policy for each.

## Project Structure
backend/
accounts/     - registration
groups/       - Group, GroupMembership (time-bounded), balances
expenses/     - Expense, ExpenseSplit, Settlement, split calculation, balance calculation
imports/      - CSV/XLSX import pipeline: parser, anomaly detectors, scan/review/commit
frontend/
src/api/      - typed API client with JWT refresh
src/pages/    - route-level pages
src/components/ - reusable UI (expense form, import review panel)
sample_data/
expenses_export.xlsx - the assignment's source data file

## Key Design Documents

- `SCOPE.md` — full anomaly log (every data problem found in the CSV, with row numbers and handling policy) + database schema
- `DECISIONS.md` — significant engineering decisions, alternatives considered, and reasoning
- `AI_USAGE.md` — AI collaboration details, prompts used, and corrected AI mistakes