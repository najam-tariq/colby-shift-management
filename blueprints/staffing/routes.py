from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from . import staffing_bp
from models import db, StaffingNeeds, Term
from datetime import datetime, time
import json

@staffing_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    print(f"DEBUG: Request method: {request.method}", flush=True)
    if request.method == 'POST':
        print("DEBUG: POST request received!", flush=True)
        
    # Get selected term from query parameter or default to first available
    selected_term_id = request.args.get('term_id', type=int)
    available_terms = Term.query.order_by(Term.start_date.desc()).all()
    
    if selected_term_id:
        selected_term = Term.query.get(selected_term_id)
    else:
        selected_term = available_terms[0] if available_terms else None
    
    if request.method == 'POST':
        action = request.form.get('action')
        print(f"DEBUG: POST request received with action: {action}", flush=True)
        print(f"DEBUG: Form data: {dict(request.form)}", flush=True)
        
        if action == 'create_term':
            print("DEBUG: Processing create_term action", flush=True)
            # Create new term
            try:
                term_name = request.form.get('term_name', '').strip()
                start_date_str = request.form.get('start_date')
                end_date_str = request.form.get('end_date')
                availability_deadline_str = request.form.get('availability_deadline')
                
                print(f"DEBUG: Extracted form data - term_name='{term_name}', start_date='{start_date_str}', end_date='{end_date_str}', deadline='{availability_deadline_str}'", flush=True)
                
                # Check if all required fields are present
                if not all([term_name, start_date_str, end_date_str, availability_deadline_str]):
                    print("DEBUG: Missing required fields", flush=True)
                    flash('All fields are required.', 'error')
                    return redirect(url_for('staffing.index'))
                
                # Parse dates
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                    availability_deadline = datetime.strptime(availability_deadline_str, '%Y-%m-%d').date()
                    print(f"DEBUG: Successfully parsed dates - start: {start_date}, end: {end_date}, deadline: {availability_deadline}", flush=True)
                except ValueError as e:
                    print(f"DEBUG: Date parsing error: {e}", flush=True)
                    flash('Invalid date format. Please use the date picker.', 'error')
                    return redirect(url_for('staffing.index'))
                
                # Validation
                if len(term_name) > 50:
                    print("DEBUG: Term name too long", flush=True)
                    flash('Term name must be 50 characters or less.', 'error')
                    return redirect(url_for('staffing.index'))
                elif start_date >= end_date:
                    print("DEBUG: Invalid date range", flush=True)
                    flash('Start date must be before end date.', 'error')
                    return redirect(url_for('staffing.index'))
                elif availability_deadline > start_date:
                    print("DEBUG: Invalid availability deadline", flush=True)
                    flash('Availability deadline must be before or on the start date.', 'error')
                    return redirect(url_for('staffing.index'))
                
                print("DEBUG: Validation passed, checking for duplicates", flush=True)
                # Check for duplicate term name
                existing_term = Term.query.filter_by(name=term_name).first()
                if existing_term:
                    print(f"DEBUG: Duplicate term found: {existing_term.name}", flush=True)
                    flash(f'A term with the name "{term_name}" already exists.', 'error')
                    return redirect(url_for('staffing.index'))
                
                print("DEBUG: No duplicate found, creating new term", flush=True)
                # Create new term
                new_term = Term(
                    name=term_name,
                    start_date=start_date,
                    end_date=end_date,
                    availability_deadline=availability_deadline,
                    locked=False
                )
                print(f"DEBUG: Created term object: {new_term}", flush=True)
                
                db.session.add(new_term)
                print("DEBUG: Added to session", flush=True)
                
                db.session.commit()
                print(f"DEBUG: Committed to database, term_id: {new_term.term_id}", flush=True)
                
                flash(f'Term "{term_name}" created successfully!', 'success')
                print("DEBUG: Redirecting to staffing index with new term", flush=True)
                return redirect(url_for('staffing.index', term_id=new_term.term_id))
                        
            except Exception as e:
                print(f"DEBUG: Unexpected exception in create_term: {e}", flush=True)
                flash(f'Error creating term: {str(e)}', 'error')
                db.session.rollback()
                return redirect(url_for('staffing.index'))
        
        elif action == 'toggle_term_lock':
            # Toggle term lock status
            try:
                term_id = int(request.form.get('term_id'))
                term = Term.query.get(term_id)
                
                if not term:
                    flash('Term not found.', 'error')
                else:
                    term.locked = not term.locked
                    db.session.commit()
                    status = "locked" if term.locked else "unlocked"
                    flash(f'Term "{term.name}" has been {status}.', 'success')
                    
            except ValueError:
                flash('Invalid term ID.', 'error')
            except Exception as e:
                flash(f'Error updating term: {str(e)}', 'error')
                db.session.rollback()
        
        elif action == 'add_coverage':
            # Add new coverage requirement
            try:
                day_of_week = int(request.form.get('day_of_week'))
                start_time = datetime.strptime(request.form.get('start_time'), '%H:%M').time()
                end_time = datetime.strptime(request.form.get('end_time'), '%H:%M').time()
                role_required = request.form.get('role_required')
                required_count = int(request.form.get('required_count'))
                
                # Use selected term for adding coverage
                term_id = request.form.get('term_id')
                if term_id:
                    term = Term.query.get(int(term_id))
                else:
                    term = selected_term
                
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
        staffing_needs = []
        
        if selected_term:
            staffing_needs = StaffingNeeds.query.filter(
                StaffingNeeds.term_id == selected_term.term_id
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
                             day_names=day_names,
                             available_terms=available_terms,
                             selected_term=selected_term)
        
    except Exception as e:
        flash(f'Error loading staffing data: {str(e)}', 'error')
        return render_template('staffing_index.html', 
                             staffing_needs=[],
                             visual_data={},
                             day_names=[],
                             available_terms=available_terms,
                             selected_term=selected_term)

