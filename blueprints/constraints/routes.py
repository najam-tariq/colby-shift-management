from flask import render_template
from . import constraints_bp

# GitHub Issues #21-37: Constraints & Equity
# Features: Shift duration, gaps, fairness, policy management, etc.

@constraints_bp.route('/')
def index():
    return render_template('constraints_index.html')

