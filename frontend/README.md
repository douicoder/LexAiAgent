# LexAgent Frontend

Production-quality Flask frontend for the LexAgent legal AI workspace.

## Stack

- Flask 3 + Jinja2
- TailwindCSS + DaisyUI
- HTMX (server-rendered partials)
- Alpine.js (tabs, dropdowns, modals)

## Prerequisites

- Python 3.11+
- LexAgent backend running at `http://localhost:8000`

## Setup

```bash
cd frontend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

Copy `.env` and set `API_BASE_URL` if your backend differs.

Ensure backend `CORS_ORIGINS` includes `http://localhost:5000`.

## Run

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000)

## Routes

| Route | Description |
|---|---|
| `/auth/login` | Sign in |
| `/auth/register` | Create account |
| `/dashboard` | New matter workspace |
| `/case/<id>` | Case chat + notice panel |
| `/research` | Legal document search |
| `/settings` | Profile & preferences |

## Tests

```bash
pip install pytest
pytest tests/
```
