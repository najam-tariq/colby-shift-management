# Azure Deployment Plan

## Detected Application
- **App Name:** colby-shift-management
- **App Type:** Python **Flask** web app (server-rendered templates/static) using **Gunicorn** (Procfile) and **Flask-SQLAlchemy** (supports MySQL via `DATABASE_URL`/`JAWSDB_URL`, local SQLite fallback).

## Recommended Azure Region
- **eastus**

## Azure Resources Needed
1. **Azure App Service (Linux) – Web App**
   - Runtime: Python 3.11 (or latest supported)
   - Startup command (example): `gunicorn app:app --preload --bind=0.0.0.0:8000`
   - Configure App Settings:
     - `SECRET_KEY` (required)
     - `DATABASE_URL` (recommended; point to managed MySQL)

2. **Azure Database for MySQL – Flexible Server** (recommended)
   - The app already supports MySQL via SQLAlchemy + PyMySQL.
   - Connection string should use `mysql+pymysql://...` (the app also normalizes `mysql://`).

3. **Azure Key Vault** (recommended)
   - Store `SECRET_KEY`, DB password/connection string.
   - Optionally use a **managed identity** on App Service to read secrets.

4. **Azure Monitor / Application Insights** (recommended)
   - Centralized logs/metrics for the Flask + Gunicorn service.

## GitHub Actions Workflow (CI/CD)
- **Trigger:** on push to `main` (and optionally PR validation)
- **Build/Test:**
  - Checkout
  - Set up Python
  - `pip install -r requirements.txt`
  - Run lightweight checks (optional): `python -m compileall .` (and tests if present)
- **Deploy:**
  - Authenticate to Azure using **GitHub OIDC** (`azure/login`)
  - Deploy to App Service using `azure/webapps-deploy` (zip deploy)
  - Apply/verify required App Settings (`SECRET_KEY`, `DATABASE_URL`)

## Infrastructure as Code (IaC)
- Generate **Bicep** templates to provision:
  - Resource Group
  - App Service Plan + Web App
  - MySQL Flexible Server + database
  - Key Vault (+ access policies/role assignments)
  - Application Insights

## Next Steps
1. Decide the production database (recommended: Azure Database for MySQL Flexible Server).
2. Define required environment variables (`SECRET_KEY`, `DATABASE_URL`) and store in Key Vault.
3. Create Bicep for the resources above and wire GitHub OIDC to the Azure subscription.
4. Add the GitHub Actions workflow to build and deploy on every push to `main`.
