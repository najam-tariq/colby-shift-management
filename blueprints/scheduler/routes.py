from flask import render_template
from . import scheduler_bp

# GitHub Issues #38-39: Schedule Generation
# Features: Generate initial schedule, manual adjustments, regeneration, etc.

@scheduler_bp.route('/')
def index():
    return render_template('scheduler_index.html')

