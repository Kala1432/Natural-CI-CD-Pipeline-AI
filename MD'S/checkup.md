# Pipeline.sh - Phase Checkup Log

This file tracks the manual changes, logs, and verification steps required by the user after each phase of implementation.

## Phase 1 & 2 Completion
- **Database Migrations:** Make sure to run `flask db upgrade` if you haven't already.
- **Background Workers:** To process repository analysis in the background, ensure Redis is running and start the Celery worker:
  `celery -A backend.celery_app.celery_app worker --loglevel=info`
- **Environment Variables:** Ensure `OPENAI_API_KEY` is set in your `.env` file to utilize the AI Pipeline Generation feature.

## Phase 3 Completion
- **GitHub Token:** To run simulations, your configured GitHub Token must have `repo` and `workflow` scopes so that the platform can commit code to branches and read GitHub Actions logs.
- **Simulation Background Tasks:** The `run_simulation` logic relies heavily on Celery. You must ensure your Celery worker is running (`celery -A backend.celery_app.celery_app worker --loglevel=info`) to orchestrate the chaos injection and fix loop.

## Phase 4 Completion
- **Frontend Build:** The frontend has been overhauled to integrate Simulation Dashboards and AI Readiness Scores.
- **Run Frontend:** To view these changes locally, navigate to `frontend/` and run `npm run dev`. Ensure the backend and Celery workers are still running to supply data to the new UI components.

## Phase 5 Completion
- **Deployment Engine:** The backend now includes a Celery-based deployment orchestrator that simulates AWS EC2 provisioning.
- **Monitoring & Rollbacks:** Background workers automatically monitor the health of deployed instances. We added a 10% chance for health checks to fail during our mock deployments to perfectly demonstrate the auto-rollback and incident logging features.
- **Usage:** You can trigger deployments from the `ProjectDetail.jsx` page (after the PR is merged) via the new "Deploy to AWS" button. Monitor them live on the new `/deployments` dashboard.

## Phase 6 Completion
- **Admin Dashboard:** A new Admin Dashboard is accessible via the `/admin` route (available only to users with `is_admin=True`). It displays platform statistics including User Count, Projects Analyzed, Total Workflows Generated, and Active Deployments.
- **Machine Learning & Anomaly Detection:** The deployment monitoring now includes mock CPU and Memory metrics. Anomaly detection flags deployments with CPU usage > 85% or Memory usage > 90% as "Critical Incidents," triggering an automatic rollback to the previous stable state.
- **Testing and Verification:** All comprehensive unit, integration, and API tests (`test_deployments.py`, `test_phase5.py`, etc.) are passing correctly.
- **Frontend Build Validation:** The frontend application builds flawlessly for production (`npm run build`). External SVG icon sets were updated to use inline SVGs avoiding dependency issues.
