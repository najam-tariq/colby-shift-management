# Azure Deployment Plan

## App
- **App Name:** colby-shift-management
- **App Type:** Python Flask web app (server-rendered templates/static) using Gunicorn. Data layer: Flask-SQLAlchemy; supports MySQL via `DATABASE_URL`/`JAWSDB_URL` (SQLite fallback for local dev).

## Recommended Azure Region
- **eastus**

## Azure Resources Needed
1. **Azure App Service (Linux) – Web App**
   - Runtime: Python 3.11 (or latest supported)
   - Startup command: `gunicorn app:app --preload --bind=0.0.0.0:${PORT:-8000}`
   - App settings: `SECRET_KEY`, `DATABASE_URL` (or `JAWSDB_URL`)

2. **Azure Database for MySQL – Flexible Server** (recommended for production)
   - Provide SQLAlchemy connection string (the app normalizes `mysql://` → `mysql+pymysql://`).

3. **Azure Key Vault** (recommended)
   - Store `SECRET_KEY` and DB credentials; optionally use App Service managed identity.

4. **Azure Monitor + Application Insights** (recommended)
   - Centralized logs/metrics for the Flask + Gunicorn service.

## GitHub Actions Workflow (CI/CD)
- On push to `main` (and PR validation):
  - Build: setup Python, `pip install -r requirements.txt`
  - Checks: `python -m compileall .` (and tests if/when added)
  - Deploy: Azure OIDC login, zip deploy to App Service, set/validate app settings
  - Optional: run DB migrations (if a Flask-Migrate/Alembic command is added to the repo)

## Infrastructure as Code (IaC)
- Generate **Bicep** templates to provision: Resource Group, App Service Plan/Web App, MySQL Flexible Server (DB + firewall), Key Vault, Application Insights.

## Next Steps
1. Confirm production database choice (MySQL Flexible Server recommended).
2. Provision Azure resources via Bicep and configure GitHub OIDC.
3. Set secrets (`SECRET_KEY`, `DATABASE_URL`) via Key Vault/App Settings.
4. Add GitHub Actions workflow to deploy on pushes to `main`.
