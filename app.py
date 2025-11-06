from flask import Flask
from flask_login import LoginManager
from flask import request
import os

# Import database instance only - models will be imported later after app config
from models import db

# Import blueprint instances (routes will be imported later)
from blueprints.auth import auth_bp
from blueprints.availability import availability_bp  
from blueprints.staffing import staffing_bp
from blueprints.constraints import constraints_bp
from blueprints.scheduler import scheduler_bp
from blueprints.outputs import outputs_bp

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Create instance directory if it doesn't exist
basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, 'instance')
os.makedirs(instance_dir, exist_ok=True)

# Use absolute path for database
db_path = os.path.join(instance_dir, 'shift_management.db')

# Debug info to understand path differences
print(f"Process: {'MAIN' if not os.environ.get('WERKZEUG_RUN_MAIN') else 'RELOADER'}")
print(f"Base dir: {basedir}")
print(f"DB path: {db_path}")
print(f"DB exists: {os.path.exists(db_path)}")

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f'sqlite:///{db_path}')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.shiftManagementLogin'
login_manager.login_message = 'Please log in to access this page.'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return db.session.get(User, int(user_id))

# Import routes after app configuration to avoid circular imports
from blueprints.auth import routes as auth_routes
from blueprints.availability import routes as availability_routes
from blueprints.staffing import routes as staffing_routes
from blueprints.constraints import routes as constraints_routes
from blueprints.scheduler import routes as scheduler_routes
from blueprints.outputs import routes as outputs_routes

# Register blueprints for routes
app.register_blueprint(auth_bp)
app.register_blueprint(availability_bp)
app.register_blueprint(staffing_bp)
app.register_blueprint(constraints_bp)
app.register_blueprint(scheduler_bp)
app.register_blueprint(outputs_bp)

# Global request/response instrumentation to diagnose missing debug prints & redirects
@app.before_request
def _debug_before_request():
    try:
        auth_state = 'auth' if (hasattr(request, 'method') and hasattr(login_manager._login_disabled, '__call__') == False) else 'n/a'
    except Exception:
        auth_state = 'n/a'
    from flask_login import current_user
    print(f"TRACE: BEFORE {request.method} {request.path} is_authenticated={getattr(current_user, 'is_authenticated', None)}", flush=True)

@app.after_request
def _debug_after_request(resp):
    print(f"TRACE: AFTER  {request.method} {request.path} -> {resp.status_code} redirect_to={resp.headers.get('Location')}", flush=True)
    return resp

# SQLAlchemy event hooks for commit visibility
from sqlalchemy import event
from sqlalchemy.orm import Session

@event.listens_for(Session, "after_flush")
def _after_flush(session, ctx):
    if session.new:
        print("TRACE: after_flush NEW objects:", [repr(o) for o in session.new], flush=True)
    if session.dirty:
        print("TRACE: after_flush DIRTY objects:", [repr(o) for o in session.dirty], flush=True)
    if session.deleted:
        print("TRACE: after_flush DELETED objects:", [repr(o) for o in session.deleted], flush=True)

@event.listens_for(Session, "after_commit")
def _after_commit(session):
    print("TRACE: after_commit committed successfully", flush=True)

@event.listens_for(Session, "after_rollback")
def _after_rollback(session):
    print("TRACE: after_rollback invoked", flush=True)

# Import all models so SQLAlchemy can create all tables
from models import User, Term, StaffingNeeds, Availability, Shift, Policy, UndesirableTimeWindow

# Create database tables (no reloader issues with use_reloader=False)
with app.app_context():
    db.create_all()
    print("Database tables created successfully!")

if __name__ == '__main__':
    # Disable reloader to avoid database connection issues during development
    app.run(debug=True, use_reloader=False)