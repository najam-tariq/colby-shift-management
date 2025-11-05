from flask import render_template
from . import outputs_bp

# GitHub Issues #40-49: Outputs & Access
# Features: Live preview, CSV export, iCal generation, student views, etc.

@outputs_bp.route('/')
def index():
    return render_template('outputs_index.html')

