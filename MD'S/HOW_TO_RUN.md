# FluxForge — How to Run

This guide provides detailed instructions on how to set up, run, and develop the **FluxForge** platform locally.

> Looking to verify each feature? See [`FEATURE_TESTING_GUIDE.md`](./FEATURE_TESTING_GUIDE.md) for the step-by-step walkthrough.

## Prerequisites
- **Python 3.10+**
- **Node.js 18+**
- **Redis server** (running locally or via Docker)
- **PostgreSQL** (optional, uses SQLite by default for local development)
- **GitHub Account** (for OAuth integration)
- **OpenAI API Key** (for the AI Recommendations feature)

---

## 1. Environment Setup

Copy the example environment configuration and fill in the missing secrets:
```bash
cp .env.example .env
```
Ensure that you at least have `OPENAI_API_KEY`, `JWT_SECRET_KEY`, and `SECRET_KEY` populated.

---

## 2. Backend Setup & Run

The backend is a Flask API that handles repository analysis, ML anomaly detection, and database operations.

1. **Navigate to the root directory**:
   ```bash
   cd path/to/Natural-CI-CD-Pipeline-AI
   ```
2. **Install Python Dependencies**:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. **Initialize the Database**:
   ```bash
   # Make sure your PYTHONPATH includes the project root
   set PYTHONPATH=.   # Windows
   export PYTHONPATH=. # macOS/Linux

   flask --app backend.app db upgrade
   ```
4. **Run the Backend API**:
   ```bash
   flask --app backend.app run --port=5001 --debug
   ```
   The backend will run at `http://127.0.0.1:5001`.

---

## 3. Background Workers (Celery & Redis)

FluxForge relies on background tasks for deployments, AI generation, and repository intelligence.

1. **Start your Redis Server**:
   Make sure Redis is running on port `6379`.
2. **Start the Celery Worker**:
   In a new terminal instance (from the project root):
   ```bash
   set PYTHONPATH=.   # Windows
   export PYTHONPATH=. # macOS/Linux

   celery -A backend.celery_app.celery_app worker --loglevel=info
   ```

---

## 4. Frontend Setup & Run

The frontend is a React.js dashboard built with Vite.

1. **Navigate to the frontend directory**:
   ```bash
   cd frontend
   ```
2. **Install Node Dependencies**:
   ```bash
   npm install
   ```
3. **Start the Development Server**:
   ```bash
   npm run dev
   ```
   The dashboard will be available at `http://localhost:3000`.

---

## 5. Running the Test Suite

We use `pytest` for unit and integration testing.

```bash
# Run all tests
set PYTHONPATH=. 
pytest backend/tests/ -v

# Run tests with coverage
pytest backend/tests/ --cov=backend
```

---

## 6. Accessing the Admin Dashboard

To access the `/admin` route on the frontend, you must have an account with the `is_admin` flag set to `True`.
If you need to make an existing account an admin locally, you can do so manually via SQLite:

```bash
sqlite3 hifi_local.db
sqlite> UPDATE user SET is_admin = 1 WHERE email = 'your-email@example.com';
sqlite> .exit
```

> **Note:** the SQLite file is `hifi_local.db` for historical reasons — the brand name is **FluxForge** but the local DB filename is unchanged for backwards compatibility.

---

## Important Project Features
* **Deployment Simulations**: Clicking "Deploy to AWS" initiates a background task mimicking EC2 provisioning.
* **ML Anomaly Detection**: The Celery worker will randomly simulate CPU/Memory usage. If usage exceeds thresholds (CPU > 85%, Mem > 90%), an automated rollback is triggered and logged as an Incident.
* **Email Verification**: Can be toggled on/off in `.env` via `EMAIL_VERIFICATION_REQUIRED=False`. If testing locally without an SMTP server configured, we recommend turning this `False`.
