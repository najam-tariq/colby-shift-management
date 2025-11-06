from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from . import staffing_bp
from models import db, StaffingNeeds, Term
from datetime import datetime, time
import json

@staffing_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_coverage':
            # Add new coverage requirement
            try:
                day_of_week = int(request.form.get('day_of_week'))
                start_time = datetime.strptime(request.form.get('start_time'), '%H:%M').time()
                end_time = datetime.strptime(request.form.get('end_time'), '%H:%M').time()
                role_required = request.form.get('role_required')
                required_count = int(request.form.get('required_count'))
                
                # We  might want to make this user-selectable)
                term = Term.query.first()  # For now, using first term
                if not term:
                    flash('No active term found. Please create a term first.', 'error')
                    return redirect(url_for('staffing.index'))
                
                # Validate time range
                if start_time >= end_time:
                    flash('Start time must be before end time.', 'error')
                    return redirect(url_for('staffing.index'))
                
                # Check for overlapping coverage windows
                existing = StaffingNeeds.query.filter(
                    StaffingNeeds.term_id == term.term_id,
                    StaffingNeeds.day_of_week == day_of_week,
                    StaffingNeeds.role_required == role_required,
                    ((StaffingNeeds.start_time <= start_time) & (StaffingNeeds.end_time > start_time)) |
                    ((StaffingNeeds.start_time < end_time) & (StaffingNeeds.end_time >= end_time)) |
                    ((StaffingNeeds.start_time >= start_time) & (StaffingNeeds.end_time <= end_time))
                ).first()
                
                if existing:
                    flash('Coverage window overlaps with existing requirement.', 'error')
                    return redirect(url_for('staffing.index'))
                
                # Create new staffing need
                new_need = StaffingNeeds(
                    term_id=term.term_id,
                    day_of_week=day_of_week,
                    start_time=start_time,
                    end_time=end_time,
                    role_required=role_required,
                    required_count=required_count
                )
                
                db.session.add(new_need)
                db.session.commit()
                
                flash(f'Coverage requirement added successfully!', 'success')
                
            except ValueError as e:
                flash('Invalid input format. Please check your entries.', 'error')
            except Exception as e:
                flash(f'Error adding coverage requirement: {str(e)}', 'error')
                db.session.rollback()
                
        elif action == 'delete_coverage':
            # Delete coverage requirement
            try:
                need_id = int(request.form.get('need_id'))
                need = StaffingNeeds.query.get(need_id)
                
                if need:
                    db.session.delete(need)
                    db.session.commit()
                    flash('Coverage requirement deleted successfully!', 'success')
                else:
                    flash('Coverage requirement not found.', 'error')
                    
            except Exception as e:
                flash(f'Error deleting coverage requirement: {str(e)}', 'error')
                db.session.rollback()
        
        elif action == 'bulk_template':
            # Apply bulk template
            template_type = request.form.get('template_type')
            
            try:
                term = Term.query.first()
                if not term:
                    flash('No active term found.', 'error')
                    return redirect(url_for('staffing.index'))
                
                if template_type == 'standard_weekdays':
                    # Monday-Friday 9AM-5PM, 2 students
                    for day in range(5):  # Mon-Fri (0-4)
                        existing = StaffingNeeds.query.filter(
                            StaffingNeeds.term_id == term.term_id,
                            StaffingNeeds.day_of_week == day,
                            StaffingNeeds.start_time == time(9, 0),
                            StaffingNeeds.end_time == time(17, 0)
                        ).first()
                        
                        if not existing:
                            new_need = StaffingNeeds(
                                term_id=term.term_id,
                                day_of_week=day,
                                start_time=time(9, 0),
                                end_time=time(17, 0),
                                role_required='student',
                                required_count=2
                            )
                            db.session.add(new_need)
                    
                    db.session.commit()
                    flash('Standard weekday template applied successfully!', 'success')
                    
                elif template_type == 'extended_hours':
                    # Monday-Friday 8AM-8PM, varying staff
                    schedules = [
                        (time(8, 0), time(12, 0), 'student', 1),
                        (time(12, 0), time(17, 0), 'student', 2),
                        (time(17, 0), time(20, 0), 'student', 1)
                    ]
                    
                    for day in range(5):  # Mon-Fri
                        for start_t, end_t, role, count in schedules:
                            existing = StaffingNeeds.query.filter(
                                StaffingNeeds.term_id == term.term_id,
                                StaffingNeeds.day_of_week == day,
                                StaffingNeeds.start_time == start_t,
                                StaffingNeeds.end_time == end_t,
                                StaffingNeeds.role_required == role
                            ).first()
                            
                            if not existing:
                                new_need = StaffingNeeds(
                                    term_id=term.term_id,
                                    day_of_week=day,
                                    start_time=start_t,
                                    end_time=end_t,
                                    role_required=role,
                                    required_count=count
                                )
                                db.session.add(new_need)
                    
                    db.session.commit()
                    flash('Extended hours template applied successfully!', 'success')
                    
            except Exception as e:
                flash(f'Error applying template: {str(e)}', 'error')
                db.session.rollback()
        
        elif action == 'clear_all':
            # Clear all coverage requirements
            try:
                term = Term.query.first()
                if term:
                    deleted_count = StaffingNeeds.query.filter(
                        StaffingNeeds.term_id == term.term_id
                    ).delete()
                    db.session.commit()
                    flash(f'Cleared {deleted_count} coverage requirements successfully!', 'success')
                else:
                    flash('No active term found.', 'error')
                    
            except Exception as e:
                flash(f'Error clearing coverage requirements: {str(e)}', 'error')
                db.session.rollback()
        
        return redirect(url_for('staffing.index'))
    
    # GET request - display the staffing needs
    try:
        term = Term.query.first()  # For now, using first term
        staffing_needs = []
        
        if term:
            staffing_needs = StaffingNeeds.query.filter(
                StaffingNeeds.term_id == term.term_id
            ).order_by(
                StaffingNeeds.day_of_week,
                StaffingNeeds.start_time
            ).all()
        
        # Organize data for visual display
        visual_data = {}
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        for day_idx, day_name in enumerate(day_names):
            visual_data[day_name] = []
            day_needs = [need for need in staffing_needs if need.day_of_week == day_idx]
            
            for need in day_needs:
                visual_data[day_name].append({
                    'start_time': need.start_time.strftime('%H:%M'),
                    'end_time': need.end_time.strftime('%H:%M'),
                    'role': need.role_required,
                    'count': need.required_count
                })
        
        return render_template('staffing_index.html', 
                             staffing_needs=staffing_needs,
                             visual_data=visual_data,
                             day_names=day_names)
        
    except Exception as e:
        flash(f'Error loading staffing data: {str(e)}', 'error')
        return render_template('staffing_index.html', 
                             staffing_needs=[],
                             visual_data={},
                             day_names=[])

