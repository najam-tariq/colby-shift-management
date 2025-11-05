from flask import render_template
from . import availability_bp

# GitHub Issues #1-12: Availability & Inputs
# Features: Availability management, CSV import, templates, deadlines, etc.

@availability_bp.route('/')
def index():
    return render_template('availability_index.html')

