from flask import render_template
from . import staffing_bp

# GitHub Issues #13-20: Staffing Needs
# Features: Coverage windows, role requirements, templates, validation, etc.

@staffing_bp.route('/')
def index():
    return render_template('staffing_index.html')

