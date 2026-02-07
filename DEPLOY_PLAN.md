# Azure Deployment Plan

## App
- **App Name:** colby-shift-management
- **App Type:** Python Flask web application (server-rendered templates/static) running via **Gunicorn**.
  - Dependencies: Flask, Flask-SQLAlchemy, Flask-Login, Flask-Migrate, PyMySQL.
  - Database: supports **MySQL** via `DATABASE_URL`/`JAWSDB_URL` (SQLite fallback for local dev).

## Recommended Azure Region
- **eastus**

## Azure Resources Needed
1. **Resource Group** (eastus)

2. **Azure App Service Plan (Linux)** + **Azure Web App (Linux)**
   - Runtime: Python (e.g., 3.11 or latest supported by App Service)
   - Startup command:
     - `gunicorn app:app --preload --bind=0.0.0.0:${PORT:-8000}`
   - App settings (minimum):
     - `SECRET_KEY`
     - `DATABASE_URL` (preferred) or `JAWSDB_URL`

3. **Azure Database for MySQL – Flexible Server** (recommended for production)
   - Provide SQLAlchemy connection string (app normalizes `mysql://` → `mysql+pymysql://`).

4. **Azure Key Vault** (recommended)
   - Store `SECRET_KEY` and DB connection string/credentials.
   - Optionally use Web App **managed identity** + Key Vault references.

5. **Application Insights / Azure Monitor** (recommended)
   - Centralized logs, metrics, and alerting for the Flask + Gunicorn service.

## GitHub Actions Workflow (CI/CD)
- **PR validation**
  - Setup Python
  - `pip install -r requirements.txt`
  - Basic checks (e.g., `python -m compileall .`; run tests if/when added)
- **Deploy on push to main**
  - Login to Azure using **GitHub OIDC**
  - Deploy to App Service (zip deploy)
  - Ensure required app settings exist (`SECRET_KEY`, `DATABASE_URL`)
  - Optionally run DB migrations (recommend adding a standard `flask db upgrade` step if migrations are used)

## Infrastructure as Code (IaC)
- Generate **Bicep** templates (recommended) to provision:
  - Resource Group, App Service Plan/Web App
  - MySQL Flexible Server (+ database + firewall/VNet rules)
  - Key Vault, Application Insights
  - (Alternative: Terraform, if your org standardizes on it)

## Next Steps
1. Decide production database approach (recommended: **MySQL Flexible Server**).
2. Define how secrets are managed (Key Vault + managed identity recommended).
3. Implement IaC (Bicep) and configure GitHub OIDC to Azure.
4. Add GitHub Actions workflow and deploy a first environment to **eastus**.
