# Sokha Haven Hotel

A Khmer-language hotel booking site with a React/Vite frontend, a Python/FastAPI API, and a persistent SQLite database.

## Requirements

- Node.js 18 or newer
- Python 3.9 or newer

## Run locally

Install the frontend dependencies and start Vite:

```bash
npm install
npm run dev
```

In another terminal, install the Python dependencies and start the API:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ADMIN_TOKEN="choose-a-long-private-token" python -m uvicorn backend.main:app --reload
```

Open the Vite URL shown in the first terminal. The API listens on `http://127.0.0.1:8000`; its interactive API documentation is at `/docs`.

The SQLite database is created at `backend/hotel.db` on the first API startup and seeded with sample rooms. The admin panel uses the `ADMIN_TOKEN` environment variable; do not expose the development server publicly or use a guessable token in production.

## Features

- Search available rooms by check-in/check-out date.
- Submit reservations with guest contact details and capacity validation.
- Prevent overlapping active bookings, including simultaneous booking attempts.
- Admin-protected room creation and availability toggling.
- Admin-protected booking review and status changes.
