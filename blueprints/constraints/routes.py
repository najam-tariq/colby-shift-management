from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from . import constraints_bp
from models import db, Policy, UndesirableTimeWindow, Term
from datetime import time

# GitHub Issues #21-37: Constraints & Equity
# Features: Shift duration, gaps, fairness, policy management, etc.

@constraints_bp.route('/')
@login_required
def index():
    return render_template('constraints_index.html')

@constraints_bp.route('/undesirable-windows')
@login_required
def undesirable_windows():
    """Display undesirable time windows management interface"""
    terms = Term.query.all()
    policies = Policy.query.all()
    
    # Get all undesirable windows with their policies
    windows = db.session.query(UndesirableTimeWindow, Policy, Term).join(
        Policy, UndesirableTimeWindow.policy_id == Policy.policy_id
    ).join(
        Term, Policy.term_id == Term.term_id
    ).all()
    
    return render_template('undesirable_windows.html', 
                         terms=terms, 
                         policies=policies, 
                         windows=windows)

@constraints_bp.route('/undesirable-windows/add', methods=['GET', 'POST'])
@login_required  
def add_undesirable_window():
    """Add a new undesirable time window"""
    if request.method == 'POST':
        try:
            # Get form data
            policy_id = request.form.get('policy_id')
            name = request.form.get('name')
            window_type = request.form.get('window_type')
            day_of_week = request.form.get('day_of_week')
            start_time_str = request.form.get('start_time')
            end_time_str = request.form.get('end_time')
            weight = float(request.form.get('weight', 1.0))
            
            # Convert time strings to time objects
            start_time = time.fromisoformat(start_time_str)
            end_time = time.fromisoformat(end_time_str)
            
            # Handle day_of_week (None for all days, specific day otherwise)
            day_of_week = int(day_of_week) if day_of_week else None
            
            # Create new undesirable window
            window = UndesirableTimeWindow(
                policy_id=policy_id,
                name=name,
                window_type=window_type,
                day_of_week=day_of_week,
                start_time=start_time,
                end_time=end_time,
                weight=weight
            )
            
            db.session.add(window)
            db.session.commit()
            
            flash(f'Undesirable time window "{name}" added successfully!', 'success')
            return redirect(url_for('constraints.undesirable_windows'))
            
        except Exception as e:
            flash(f'Error adding undesirable window: {str(e)}', 'error')
            db.session.rollback()
    
    # GET request - show form
    policies = Policy.query.all()
    return render_template('add_undesirable_window.html', policies=policies)

@constraints_bp.route('/undesirable-windows/delete/<int:window_id>', methods=['POST'])
@login_required
def delete_undesirable_window(window_id):
    """Delete an undesirable time window"""
    try:
        window = UndesirableTimeWindow.query.get_or_404(window_id)
        window_name = window.name
        
        db.session.delete(window)
        db.session.commit()
        
        flash(f'Undesirable time window "{window_name}" deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting undesirable window: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('constraints.undesirable_windows'))

