# ShopApp — IncidentIQ Demo Target

A real e-commerce app (products, cart, orders, auth) that runs cleanly out of the box.
When bugs are introduced, **IncidentIQ automatically detects them, performs RCA, and generates a fix**.

---

## Architecture

```
┌─────────────────────────┐        ┌──────────────────────────┐
│   ShopApp Frontend      │        │   ShopApp Backend        │
│   React + Tailwind      │◄──────►│   FastAPI + SQLite       │
│   http://localhost:3001 │  /api  │   http://localhost:8001  │
└─────────────────────────┘        └──────────┬───────────────┘
                                              │ GET /metrics
                                              │ (OTEL telemetry)
                                   ┌──────────▼───────────────┐
                                   │   IncidentIQ             │
                                   │   AI Incident Response   │
                                   │   http://localhost:8000  │
                                   └──────────────────────────┘
```

## Quick Start

### 1. Start IncidentIQ (must be running first)
```powershell
# In terminal 1 — from c:\grabhack\incidentiq\
$env:PYTHONPATH = "C:\grabhack\incidentiq"
C:\grabhack\venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000 --reload
```

### 2. Start ShopApp backend
```powershell
# In terminal 2 — from c:\grabhack\shopapp\backend\
C:\grabhack\venv\Scripts\python.exe -m uvicorn main:app --port 8001 --reload
```

### 3. Start ShopApp frontend
```powershell
# In terminal 3 — from c:\grabhack\shopapp\frontend\
npm run dev
# Opens at http://localhost:3001
```

### 4. Run the full demo
```powershell
# In terminal 4 — from c:\grabhack\shopapp\
C:\grabhack\venv\Scripts\python.exe scripts\run_demo.py
```

---

## What the Demo Does

| Step | What happens |
|------|-------------|
| 1 | Verifies both services are running |
| 2 | Generates clean traffic — 0% errors ✅ |
| 3 | Introduces 3 bugs into the backend code |
| 4 | Generates traffic — errors spike 🔴 |
| 5 | Sends telemetry + buggy code to IncidentIQ |
| 6 | IncidentIQ performs RCA, generates PR with fix |
| 7 | Restores clean files automatically |
| 8 | Verifies service recovered ✅ |

---

## The Bugs Introduced

### Bug 1 — `routes/sessions.py` — Connection Leak
```python
# BUGGY: raw connection, never released on exception
conn = engine.connect()
try:
    result = conn.execute(text(f"SELECT * FROM sessions WHERE user_id = {user_id}"))
    ...
except Exception as e:
    raise HTTPException(...)
    # conn.close() NEVER called → pool exhaustion under load
```

### Bug 2 — `routes/products.py` — SQL Injection
```python
# BUGGY: f-string interpolation → SQL injection
sql = f"SELECT * FROM products WHERE category = '{category}'"
result = db.execute(text(sql))
```

### Bug 3 — `routes/orders.py` — No Timeout + Connection Leak
```python
# BUGGY: no timeout, connection never released on error
conn = engine.connect()   # blocks forever if pool exhausted
...
except Exception as e:
    raise HTTPException(...)
    # conn.close() NEVER called
```

---

## Manual Bug Control

```powershell
# Introduce bugs manually
C:\grabhack\venv\Scripts\python.exe scripts\introduce_bug.py

# Send to IncidentIQ manually
C:\grabhack\venv\Scripts\python.exe scripts\notify_incidentiq.py

# Restore clean files
C:\grabhack\venv\Scripts\python.exe scripts\fix_bug.py
```

## Continuous Watcher (optional)

Runs in the background and auto-alerts IncidentIQ when anomalies are detected:

```powershell
# Basic watcher
C:\grabhack\venv\Scripts\python.exe scripts\watch_and_alert.py

# With auto-fix (restores .bak files automatically)
C:\grabhack\venv\Scripts\python.exe scripts\watch_and_alert.py --auto-fix
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/metrics` | OTEL telemetry (read by IncidentIQ) |
| GET | `/products` | List products (supports `?category=`) |
| GET | `/products/{id}` | Get single product |
| POST | `/orders` | Create order |
| GET | `/orders` | List orders |
| POST | `/users/register` | Register user |
| POST | `/users/login` | Login |
| GET | `/sessions/{user_id}` | Get active session |

---

## Services Summary

| Service | URL | Port |
|---------|-----|------|
| ShopApp UI | http://localhost:3001 | 3001 |
| ShopApp API | http://localhost:8001 | 8001 |
| ShopApp API Docs | http://localhost:8001/docs | 8001 |
| IncidentIQ UI | http://localhost:3000 | 3000 |
| IncidentIQ API | http://localhost:8000 | 8000 |
| IncidentIQ Docs | http://localhost:8000/docs | 8000 |
