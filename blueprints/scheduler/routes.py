from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from . import scheduler_bp
from models import db, Term, Shift, User, Policy, StaffingNeeds, Availability, ShiftViolation, ShiftGap
from schedule_generator import ScheduleGenerator, GapAnalyzer
from datetime import datetime, date, timedelta, time
import uuid

# GitHub Issues #38-39: Schedule Generation
# Features: Generate initial schedule, manual adjustments, regeneration, etc.

@scheduler_bp.route('/')
@login_required
def index():
    """Main scheduler page with week-by-week overview and generation form"""
    # Only supervisors can access scheduler
    if current_user.role == 'student':
        flash('Access denied. Only supervisors can access the scheduler.', 'error')
        return redirect(url_for('auth.shiftManagement'))
    
    # Get selected term from query parameter or default to latest
    selected_term_id = request.args.get('term_id', type=int)
    available_terms = Term.query.order_by(Term.start_date.desc()).all()
    
    if selected_term_id:
        selected_term = Term.query.get(selected_term_id)
    else:
        selected_term = available_terms[0] if available_terms else None
    
    if not selected_term:
        flash('No term found. Please create a term first in the Staffing section.', 'error')
        return render_template('scheduler_index.html', 
                             available_terms=available_terms,
                             selected_term=None,
                             week_overview=[],
                             policy=None,
                             total_shifts=0,
                             students_with_shifts=0)
    
    # Get policy for this term
    policy = Policy.get_policy_with_defaults(selected_term.term_id)
    
    # Calculate week-by-week overview
    term_start = selected_term.start_date
    term_end = selected_term.end_date
    
    # Calculate number of weeks in term
    days_in_term = (term_end - term_start).days + 1
    weeks_in_term = (days_in_term + 6) // 7  # Round up to include partial weeks
    
    week_overview = []
    for week_num in range(weeks_in_term):
        week_start = term_start + timedelta(weeks=week_num)
        week_end = week_start + timedelta(days=6)
        
        # Don't go past term end
        if week_end > term_end:
            week_end = term_end
        
        # Get shifts for this week
        shifts_in_week = Shift.query.filter(
            Shift.term_id == selected_term.term_id,
            Shift.date >= week_start,
            Shift.date <= week_end
        ).all()
        
        # Get unique students with shifts this week
        students_in_week = len(set([s.user_id for s in shifts_in_week]))
        
        # Determine status
        if len(shifts_in_week) == 0:
            status = 'empty'
            icon = '✗'
        elif len(shifts_in_week) < 5:  # Less than 1 shift per weekday
            status = 'warning'
            icon = '⚠'
        else:
            status = 'complete'
            icon = '✓'
        
        week_overview.append({
            'week_num': week_num + 1,
            'week_start': week_start,
            'week_end': week_end,
            'shift_count': len(shifts_in_week),
            'student_count': students_in_week,
            'status': status,
            'icon': icon
        })
    
    # Calculate overall statistics
    total_shifts = Shift.query.filter_by(term_id=selected_term.term_id).count()
    students_with_shifts = len(set([s.user_id for s in Shift.query.filter_by(term_id=selected_term.term_id).all()]))
    
    # Find next unscheduled week
    next_unscheduled_week = None
    for week in week_overview:
        if week['status'] == 'empty':
            next_unscheduled_week = week
            break
    
    # Get staffing needs summary
    staffing_needs = StaffingNeeds.query.filter_by(term_id=selected_term.term_id).all()
    has_staffing_needs = len(staffing_needs) > 0
    
    return render_template('scheduler_index.html',
                         available_terms=available_terms,
                         selected_term=selected_term,
                         week_overview=week_overview,
                         policy=policy,
                         total_shifts=total_shifts,
                         students_with_shifts=students_with_shifts,
                         next_unscheduled_week=next_unscheduled_week,
                         has_staffing_needs=has_staffing_needs)


@scheduler_bp.route('/generate', methods=['POST'])
@login_required
def generate():
    """Generate schedule for specified date range"""
    if current_user.role == 'student':
        flash('Access denied. Only supervisors can generate schedules.', 'error')
        return redirect(url_for('scheduler.index'))
    
    try:
        term_id = int(request.form.get('term_id'))
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        
        # Validate inputs
        if not all([term_id, start_date_str, end_date_str]):
            flash('Please provide term and date range.', 'error')
            return redirect(url_for('scheduler.index', term_id=term_id))
        
        # Parse dates
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        # Validate date range
        if start_date > end_date:
            flash('Start date must be before or equal to end date.', 'error')
            return redirect(url_for('scheduler.index', term_id=term_id))
        
        term = Term.query.get(term_id)
        if not term:
            flash('Term not found.', 'error')
            return redirect(url_for('scheduler.index'))
        
        # Check if dates are within term
        if start_date < term.start_date or end_date > term.end_date:
            flash(f'Date range must be within term dates ({term.start_date} to {term.end_date}).', 'error')
            return redirect(url_for('scheduler.index', term_id=term_id))
        
        # Check for existing shifts in date range
        existing_shifts = Shift.query.filter(
            Shift.term_id == term_id,
            Shift.date >= start_date,
            Shift.date <= end_date
        ).count()
        
        if existing_shifts > 0:
            overwrite = request.form.get('overwrite') == 'true'
            if not overwrite:
                flash(f'Warning: {existing_shifts} shifts already exist in this date range. Check "Overwrite existing shifts" to proceed.', 'error')
                return redirect(url_for('scheduler.index', term_id=term_id))
            else:
                # Delete existing shifts
                Shift.query.filter(
                    Shift.term_id == term_id,
                    Shift.date >= start_date,
                    Shift.date <= end_date
                ).delete()
                db.session.commit()
        
        # Check if staffing needs exist
        staffing_needs = StaffingNeeds.query.filter_by(term_id=term_id).count()
        if staffing_needs == 0:
            flash('No staffing needs defined. Please define staffing requirements first.', 'error')
            return redirect(url_for('scheduler.index', term_id=term_id))
        
        # Check if students have availability
        availability_count = Availability.query.filter_by(term_id=term_id).count()
        if availability_count == 0:
            flash('No student availability data. Please collect availability first.', 'error')
            return redirect(url_for('scheduler.index', term_id=term_id))
        
        # Initialize schedule generator
        generator = ScheduleGenerator(term_id)
        
        # Generate schedule
        results = generator.generate_schedule(start_date, end_date, dry_run=False)
        
        # Display results
        if results['total_shifts_generated'] > 0:
            flash(f'Schedule generated successfully! Created {results["total_shifts_generated"]} shifts.', 'success')
            
            if results['warnings']:
                for warning in results['warnings'][:5]:  # Show first 5 warnings
                    flash(warning, 'info')
                if len(results['warnings']) > 5:
                    flash(f'... and {len(results["warnings"]) - 5} more warnings.', 'info')
        else:
            flash('No shifts were generated. Please check staffing needs and availability.', 'error')
        
        # Redirect to results or preview
        return redirect(url_for('scheduler.generation_results', term_id=term_id, 
                              start_date=start_date_str, end_date=end_date_str))
        
    except ValueError as e:
        flash(f'Invalid date format: {str(e)}', 'error')
        return redirect(url_for('scheduler.index'))
    except Exception as e:
        flash(f'Error generating schedule: {str(e)}', 'error')
        db.session.rollback()
        return redirect(url_for('scheduler.index'))


@scheduler_bp.route('/generation-results')
@login_required
def generation_results():
    """Display results of schedule generation"""
    if current_user.role == 'student':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.shiftManagement'))
    
    term_id = request.args.get('term_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    if not all([term_id, start_date_str, end_date_str]):
        flash('Missing generation parameters.', 'error')
        return redirect(url_for('scheduler.index'))
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        term = Term.query.get(term_id)
        if not term:
            flash('Term not found.', 'error')
            return redirect(url_for('scheduler.index'))
        
        # Get generated shifts
        shifts = Shift.query.filter(
            Shift.term_id == term_id,
            Shift.date >= start_date,
            Shift.date <= end_date
        ).order_by(Shift.date, Shift.start_time).all()
        
        # Calculate statistics
        total_shifts = len(shifts)
        unique_students = len(set([s.user_id for s in shifts]))
        
        # Group shifts by student
        shifts_by_student = {}
        for shift in shifts:
            if shift.user_id not in shifts_by_student:
                shifts_by_student[shift.user_id] = {
                    'student': shift.user,
                    'shifts': [],
                    'total_hours': 0
                }
            
            # Calculate shift duration
            shift_start = datetime.combine(shift.date, shift.start_time)
            shift_end = datetime.combine(shift.date, shift.end_time)
            duration_hours = (shift_end - shift_start).seconds / 3600
            
            shifts_by_student[shift.user_id]['shifts'].append(shift)
            shifts_by_student[shift.user_id]['total_hours'] += duration_hours
        
        # Detect any violations or gaps
        policy = Policy.get_policy_with_defaults(term_id)
        violations = []
        gaps = []
        
        for shift in shifts:
            # Check for duration violations
            is_valid, error = shift.validate_duration_constraints()
            if not is_valid:
                violations.append({
                    'shift': shift,
                    'error': error
                })
        
        # Detect gaps
        gap_analyzer = GapAnalyzer()
        gap_analysis = gap_analyzer.analyze_term_gaps(term_id)
        
        return render_template('generation_results.html',
                             term=term,
                             start_date=start_date,
                             end_date=end_date,
                             total_shifts=total_shifts,
                             unique_students=unique_students,
                             shifts_by_student=shifts_by_student,
                             violations=violations,
                             gap_analysis=gap_analysis,
                             policy=policy)
        
    except Exception as e:
        flash(f'Error displaying results: {str(e)}', 'error')
        return redirect(url_for('scheduler.index', term_id=term_id))


# Phase 2: Manual Adjustment Routes (Issue #45)

@scheduler_bp.route('/edit-schedule')
@login_required
def edit_schedule():
    """Interactive schedule editing interface"""
    if current_user.role == 'student':
        flash('Access denied. Only supervisors can edit schedules.', 'error')
        return redirect(url_for('auth.shiftManagement'))
    
    # Get term from query param
    term_id = request.args.get('term_id', type=int)
    
    if not term_id:
        # Default to most recent term
        term = Term.query.order_by(Term.start_date.desc()).first()
        if term:
            return redirect(url_for('scheduler.edit_schedule', term_id=term.term_id))
        else:
            flash('No term found.', 'error')
            return redirect(url_for('scheduler.index'))
    
    term = Term.query.get_or_404(term_id)
    policy = Policy.get_policy_with_defaults(term_id)
    
    # Get week parameter or default to current week
    week_offset = request.args.get('week', 0, type=int)
    week_start = term.start_date + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)
    
    # Don't go past term end
    if week_end > term.end_date:
        week_end = term.end_date
    
    # Get shifts for this week
    shifts = Shift.query.filter(
        Shift.term_id == term_id,
        Shift.date >= week_start,
        Shift.date <= week_end
    ).order_by(Shift.date, Shift.start_time).all()
    
    # Get all students
    students = User.query.filter_by(role='student', is_active=True).order_by(User.name).all()
    
    # Calculate total weeks
    days_in_term = (term.end_date - term.start_date).days + 1
    total_weeks = (days_in_term + 6) // 7
    
    # Calculate dates for each day of the week
    week_dates = [week_start + timedelta(days=i) for i in range(7)]
    
    return render_template('edit_schedule.html',
                         term=term,
                         policy=policy,
                         week_start=week_start,
                         week_end=week_end,
                         week_offset=week_offset,
                         total_weeks=total_weeks,
                         week_dates=week_dates,
                         shifts=shifts,
                         students=students)


@scheduler_bp.route('/edit-shift/<int:shift_id>', methods=['GET', 'POST'])
@login_required
def edit_shift(shift_id):
    """Edit an existing shift"""
    if current_user.role == 'student':
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    shift = Shift.query.get_or_404(shift_id)
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Update shift fields
            if 'user_id' in data:
                shift.user_id = int(data['user_id'])
            
            if 'date' in data:
                shift.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
            
            if 'start_time' in data:
                start_hour, start_min = map(int, data['start_time'].split(':'))
                shift.start_time = time(start_hour, start_min)
            
            if 'end_time' in data:
                end_hour, end_min = map(int, data['end_time'].split(':'))
                shift.end_time = time(end_hour, end_min)
            
            # Mark as manually adjusted
            shift.was_manually_adjusted = True
            
            # Validate the shift
            is_valid, error = shift.validate_duration_constraints()
            if not is_valid:
                return jsonify({'success': False, 'error': error, 'warning': True}), 200
            
            db.session.commit()
            
            # Detect violations and gaps
            ShiftViolation.detect_violations_for_shift(shift)
            ShiftGap.detect_gaps_for_user_date(shift.user_id, shift.date, shift.term_id)
            
            return jsonify({
                'success': True,
                'shift': {
                    'shift_id': shift.shift_id,
                    'user_name': shift.user.name,
                    'date': shift.date.strftime('%Y-%m-%d'),
                    'start_time': shift.start_time.strftime('%H:%M'),
                    'end_time': shift.end_time.strftime('%H:%M')
                }
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
    
    # GET request - return shift data
    return jsonify({
        'shift': {
            'shift_id': shift.shift_id,
            'user_id': shift.user_id,
            'user_name': shift.user.name,
            'date': shift.date.strftime('%Y-%m-%d'),
            'start_time': shift.start_time.strftime('%H:%M'),
            'end_time': shift.end_time.strftime('%H:%M')
        }
    })


@scheduler_bp.route('/create-shift', methods=['POST'])
@login_required
def create_shift():
    """Create a new shift"""
    if current_user.role == 'student':
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        
        # Required fields
        term_id = int(data['term_id'])
        user_id = int(data['user_id'])
        date_str = data['date']
        start_time_str = data['start_time']
        end_time_str = data['end_time']
        
        # Parse date and times
        shift_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        start_hour, start_min = map(int, start_time_str.split(':'))
        end_hour, end_min = map(int, end_time_str.split(':'))
        start_time_obj = time(start_hour, start_min)
        end_time_obj = time(end_hour, end_min)
        
        # Create shift
        new_shift = Shift(
            term_id=term_id,
            user_id=user_id,
            date=shift_date,
            start_time=start_time_obj,
            end_time=end_time_obj,
            was_manually_adjusted=True
        )
        
        # Validate
        is_valid, error = new_shift.validate_duration_constraints()
        if not is_valid:
            return jsonify({'success': False, 'error': error, 'warning': True}), 200
        
        db.session.add(new_shift)
        db.session.commit()
        
        # Detect violations and gaps
        ShiftViolation.detect_violations_for_shift(new_shift)
        ShiftGap.detect_gaps_for_user_date(new_shift.user_id, new_shift.date, new_shift.term_id)
        
        return jsonify({
            'success': True,
            'shift': {
                'shift_id': new_shift.shift_id,
                'user_name': new_shift.user.name,
                'date': new_shift.date.strftime('%Y-%m-%d'),
                'start_time': new_shift.start_time.strftime('%H:%M'),
                'end_time': new_shift.end_time.strftime('%H:%M')
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@scheduler_bp.route('/delete-shift/<int:shift_id>', methods=['POST'])
@login_required
def delete_shift(shift_id):
    """Delete a shift"""
    if current_user.role == 'student':
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        shift = Shift.query.get_or_404(shift_id)
        user_id = shift.user_id
        shift_date = shift.date
        term_id = shift.term_id
        
        db.session.delete(shift)
        db.session.commit()
        
        # Re-detect gaps for this user/date after deletion
        ShiftGap.detect_gaps_for_user_date(user_id, shift_date, term_id)
        
        return jsonify({'success': True, 'message': 'Shift deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@scheduler_bp.route('/reassign-shift/<int:shift_id>', methods=['POST'])
@login_required
def reassign_shift(shift_id):
    """Reassign a shift to a different student"""
    if current_user.role == 'student':
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        shift = Shift.query.get_or_404(shift_id)
        data = request.get_json()
        
        new_user_id = int(data['user_id'])
        old_user_id = shift.user_id
        
        # Update user
        shift.user_id = new_user_id
        shift.was_manually_adjusted = True
        
        db.session.commit()
        
        # Re-detect gaps for both old and new users
        ShiftGap.detect_gaps_for_user_date(old_user_id, shift.date, shift.term_id)
        ShiftGap.detect_gaps_for_user_date(new_user_id, shift.date, shift.term_id)
        
        return jsonify({
            'success': True,
            'shift': {
                'shift_id': shift.shift_id,
                'user_name': shift.user.name
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@scheduler_bp.route('/validate-shift-edit', methods=['POST'])
@login_required
def validate_shift_edit():
    """Real-time validation endpoint for shift edits"""
    if current_user.role == 'student':
        return jsonify({'valid': False, 'error': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        
        term_id = int(data['term_id'])
        user_id = int(data.get('user_id', 0))
        date_str = data['date']
        start_time_str = data['start_time']
        end_time_str = data['end_time']
        shift_id = data.get('shift_id')  # Optional for edits
        
        # Parse date and times
        shift_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        start_hour, start_min = map(int, start_time_str.split(':'))
        end_hour, end_min = map(int, end_time_str.split(':'))
        start_time_obj = time(start_hour, start_min)
        end_time_obj = time(end_hour, end_min)
        
        warnings = []
        errors = []
        
        # Get policy
        policy = Policy.get_policy_with_defaults(term_id)
        
        # Validate duration
        is_valid, error = policy.validate_shift_times(start_time_obj, end_time_obj)
        if not is_valid:
            errors.append(error)
        
        # Check for gaps if user_id provided
        if user_id > 0:
            # Get other shifts for this user on this date
            other_shifts = Shift.query.filter(
                Shift.user_id == user_id,
                Shift.date == shift_date,
                Shift.term_id == term_id
            )
            
            # Exclude current shift if editing
            if shift_id:
                other_shifts = other_shifts.filter(Shift.shift_id != shift_id)
            
            other_shifts = other_shifts.all()
            
            # Check for overlaps and gaps
            for other_shift in other_shifts:
                # Check overlap
                if (start_time_obj < other_shift.end_time and end_time_obj > other_shift.start_time):
                    errors.append(f'Shift overlaps with existing shift at {other_shift.start_time.strftime("%H:%M")}-{other_shift.end_time.strftime("%H:%M")}')
                else:
                    # Check gap
                    if start_time_obj > other_shift.end_time:
                        gap_minutes = (datetime.combine(shift_date, start_time_obj) - 
                                     datetime.combine(shift_date, other_shift.end_time)).seconds // 60
                    else:
                        gap_minutes = (datetime.combine(shift_date, other_shift.start_time) - 
                                     datetime.combine(shift_date, end_time_obj)).seconds // 60
                    
                    if 0 < gap_minutes < policy.max_gap_threshold:
                        warnings.append(f'Creates {gap_minutes}-minute gap (problematic)')
                    elif gap_minutes < policy.min_transition_time:
                        errors.append(f'Insufficient transition time: {gap_minutes} min (minimum: {policy.min_transition_time} min)')
        
        # Check if time is in undesirable window
        start_hour_int = start_time_obj.hour * 100 + start_time_obj.minute
        end_hour_int = end_time_obj.hour * 100 + end_time_obj.minute
        
        if start_hour_int < policy.undesireable_start or end_hour_int > policy.undesireable_end:
            warnings.append('Shift occurs during undesirable hours')
        
        return jsonify({
            'valid': len(errors) == 0,
            'warnings': warnings,
            'errors': errors
        })
        
    except Exception as e:
        return jsonify({'valid': False, 'errors': [str(e)]}), 500

