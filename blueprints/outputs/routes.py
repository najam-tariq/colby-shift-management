from flask import render_template, Response, abort, request, redirect, url_for
from flask_login import login_required, current_user
from models import Shift, User, Term, Policy, db
from . import outputs_bp
import csv
from io import StringIO
from datetime import datetime, date
try:
    from icalendar import Calendar, Event
    ICALENDAR_AVAILABLE = True
except ImportError:
    ICALENDAR_AVAILABLE = False

# Outputs & Access
# Features: Live preview, CSV export, iCal generation, student views, etc.

@outputs_bp.route('/')
@login_required
def index():
    """Main outputs page"""
    # Ensure current user has a calendar token (for students)
    if current_user.role == 'student':
        current_user.ensure_calendar_token()
    
    # Get current term and shift count
    term = Term.query.order_by(Term.start_date.desc()).first()
    shift_count = Shift.query.count() if term else 0
    student_count = User.query.filter_by(role='student').count()
    
    return render_template('outputs_index.html', 
                          term=term, 
                          shift_count=shift_count,
                          student_count=student_count,
                          icalendar_available=ICALENDAR_AVAILABLE)

@outputs_bp.route('/export/csv')
@login_required
def export_csv():
    """Export schedule as CSV"""
    if current_user.role.lower() != 'supervisor':
        abort(403)
    
    # Get term_id from query params or use latest
    term_id = request.args.get('term_id', type=int)
    if term_id:
        term = Term.query.get_or_404(term_id)
        shifts = Shift.query.filter_by(term_id=term_id).order_by(
            Shift.date, Shift.start_time
        ).all()
    else:
        term = Term.query.order_by(Term.start_date.desc()).first()
        shifts = Shift.query.order_by(Shift.date, Shift.start_time).all()
    
    # Get policy to apply constraints
    policy = Policy.query.filter_by(term_id=term.term_id).first() if term else None
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Add metadata rows
    writer.writerow(['# Colby Shift Management System - Schedule Export'])
    writer.writerow([f'# Export Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'])
    writer.writerow([f'# Export Version: 1.0'])
    if term:
        writer.writerow([f'# Term: {term.name}'])
        writer.writerow([f'# Term Period: {term.start_date} to {term.end_date}'])
    writer.writerow([f'# Total Shifts: {len(shifts)}'])
    writer.writerow([''])  # Empty row for separation
    
    # Header row
    writer.writerow([
        'Date', 'Day of Week', 'Student Name', 'Email', 
        'Start Time', 'End Time', 'Duration (hours)', 'Manually Adjusted', 'Constraint Status'
    ])
    
    for shift in shifts:
        # Calculate duration using actual shift date
        shift_start = datetime.combine(shift.date, shift.start_time)
        shift_end = datetime.combine(shift.date, shift.end_time)
        duration_minutes = (shift_end - shift_start).seconds / 60  # Duration in minutes
        duration = duration_minutes / 60  # Duration in hours for display
        
        # Apply constraint checks
        constraint_status = 'Valid'
        warnings = []
        
        if policy:
            if duration_minutes < policy.min_shift_length or duration_minutes > policy.max_shift_length:
                constraint_status = 'VIOLATION'
            # Convert time to HHMM format for comparison (e.g., 8:30 -> 830)
            start_time_int = shift.start_time.hour * 100 + shift.start_time.minute
            end_time_int = shift.end_time.hour * 100 + shift.end_time.minute
            if start_time_int < policy.undesireable_start or end_time_int > policy.undesireable_end:
                if constraint_status == 'Valid':
                    constraint_status = 'Warning'
                    warnings.append('Undesirable time')
        
        # Export ALL shifts with constraint status
        writer.writerow([
            shift.date.strftime('%Y-%m-%d'),
            shift.date.strftime('%A'),
            shift.user.name,
            shift.user.email,
            shift.start_time.strftime('%I:%M %p'),
            shift.end_time.strftime('%I:%M %p'),
            f'{duration:.1f}',
            'Yes' if shift.was_manually_adjusted else 'No',
            constraint_status
        ])
    
    filename = f'schedule_{term.name.replace(" ", "_")}.csv' if term else 'schedule.csv'
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename={filename}'}
    )

@outputs_bp.route('/export/ical')
@login_required
def export_ical():
    """Export schedule as iCal"""
    if not ICALENDAR_AVAILABLE:
        return "icalendar package not installed. Run: pip install icalendar", 500
    
    if current_user.role.lower() != 'supervisor':
        abort(403)
    
    # Get term_id from query params or use latest
    term_id = request.args.get('term_id', type=int)
    if term_id:
        term = Term.query.get_or_404(term_id)
        shifts = Shift.query.filter_by(term_id=term_id).order_by(
            Shift.date, Shift.start_time
        ).all()
    else:
        term = Term.query.order_by(Term.start_date.desc()).first()
        shifts = Shift.query.order_by(Shift.date, Shift.start_time).all()
    
    # Get policy to apply constraints
    policy = Policy.query.filter_by(term_id=term.term_id).first() if term else None
    
    # Create calendar
    cal = Calendar()
    cal.add('prodid', '-//Colby Shift Management System//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    cal.add('x-wr-calname', f'Shift Schedule - {term.name}' if term else 'Shift Schedule')
    cal.add('x-wr-timezone', 'America/New_York')
    
    # Add VTIMEZONE component
    from icalendar import Timezone, TimezoneStandard, TimezoneDaylight
    from datetime import timedelta
    
    tz = Timezone()
    tz.add('tzid', 'America/New_York')
    
    # Standard time (EST: UTC-5)
    standard = TimezoneStandard()
    standard.add('dtstart', datetime(1970, 11, 1, 2, 0, 0))
    standard.add('rrule', {'freq': 'yearly', 'bymonth': 11, 'byday': '1su'})
    standard.add('tzoffsetfrom', timedelta(hours=-4))  # From EDT (UTC-4)
    standard.add('tzoffsetto', timedelta(hours=-5))    # To EST (UTC-5)
    standard.add('tzname', 'EST')
    tz.add_component(standard)
    
    # Daylight time (EDT: UTC-4)
    daylight = TimezoneDaylight()
    daylight.add('dtstart', datetime(1970, 3, 8, 2, 0, 0))
    daylight.add('rrule', {'freq': 'yearly', 'bymonth': 3, 'byday': '2su'})
    daylight.add('tzoffsetfrom', timedelta(hours=-5))  # From EST (UTC-5)
    daylight.add('tzoffsetto', timedelta(hours=-4))    # To EDT (UTC-4)
    daylight.add('tzname', 'EDT')
    tz.add_component(daylight)
    
    cal.add_component(tz)
    
    for shift in shifts:
        # Calculate duration using actual shift date
        shift_start = datetime.combine(shift.date, shift.start_time)
        shift_end = datetime.combine(shift.date, shift.end_time)
        duration_minutes = (shift_end - shift_start).seconds / 60  # Duration in minutes
        duration = duration_minutes / 60  # Duration in hours for display
        
        # Apply constraint checks
        constraint_status = 'Valid'
        description_parts = [f'Shift for {shift.user.name} ({shift.user.email})']
        
        if policy:
            if duration_minutes < policy.min_shift_length or duration_minutes > policy.max_shift_length:
                constraint_status = 'VIOLATION'
                description_parts.append(f'⚠️ CONSTRAINT VIOLATION: Shift length {duration:.1f}h outside allowed range ({policy.min_shift_length/60:.1f}-{policy.max_shift_length/60:.1f}h)')
            # Convert time to HHMM format for comparison (e.g., 8:30 -> 830)
            start_time_int = shift.start_time.hour * 100 + shift.start_time.minute
            end_time_int = shift.end_time.hour * 100 + shift.end_time.minute
            if start_time_int < policy.undesireable_start or end_time_int > policy.undesireable_end:
                if constraint_status == 'Valid':
                    constraint_status = 'Warning'
                description_parts.append(f'⚠️ Warning: Shift occurs during undesirable hours')
        
        if shift.was_manually_adjusted:
            description_parts.append('✏️ This shift was manually adjusted')
        
        # Export ALL shifts with constraint information
        event = Event()
        event.add('summary', f'{shift.user.name} - Shift' + (' ⚠️' if constraint_status != 'Valid' else ''))
        event.add('description', '\n'.join(description_parts))
        event.add('dtstart', datetime.combine(shift.date, shift.start_time))
        event.add('dtend', datetime.combine(shift.date, shift.end_time))
        
        # Stable UID based on shift_id
        event.add('uid', f'shift-{shift.shift_id}@colby-shift-management.edu')
        
        # Add SEQUENCE for updates
        sequence = 1 if shift.was_manually_adjusted else 0
        event.add('sequence', sequence)
        
        event.add('location', 'Colby College')
        event.add('status', 'CONFIRMED')
        
        # Add categories for filtering
        if constraint_status == 'VIOLATION':
            event.add('categories', ['Work Shift', 'Constraint Violation'])
        elif constraint_status == 'Warning':
            event.add('categories', ['Work Shift', 'Warning'])
        else:
            event.add('categories', ['Work Shift'])
        
        # Add metadata
        event.add('created', datetime.now())
        event.add('last-modified', datetime.now())
        
        cal.add_component(event)
    
    filename = f'schedule_{term.name.replace(" ", "_")}.ics' if term else 'schedule.ics'
    
    return Response(
        cal.to_ical(),
        mimetype='text/calendar',
        headers={'Content-Disposition': f'attachment;filename={filename}'}
    )

@outputs_bp.route('/calendar/<token>')
def export_ical_student(token):
    """Public iCal feed for calendar subscriptions using secure token - no login required"""
    if not ICALENDAR_AVAILABLE:
        return "icalendar package not installed. Run: pip install icalendar", 500
    
    # Find student by calendar token (secure, stable URL for calendar subscriptions)
    student = User.query.filter_by(calendar_token=token).first_or_404()
    if student.role != 'student':
        abort(404, "User is not a student")
    
    # Get term_id from query params or use latest
    term_id = request.args.get('term_id', type=int)
    if term_id:
        term = Term.query.get_or_404(term_id)
        shifts = Shift.query.filter_by(term_id=term_id, user_id=student.user_id).order_by(
            Shift.date, Shift.start_time
        ).all()
    else:
        term = Term.query.order_by(Term.start_date.desc()).first()
        shifts = Shift.query.filter_by(user_id=student.user_id).order_by(Shift.date, Shift.start_time).all()
    
    # Get policy to apply constraints
    policy = Policy.query.filter_by(term_id=term.term_id).first() if term else None
    
    # Create calendar
    cal = Calendar()
    cal.add('prodid', '-//Colby Shift Management System//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    cal.add('x-wr-calname', f'{student.name} - Shift Schedule' + (f' - {term.name}' if term else ''))
    cal.add('x-wr-timezone', 'America/New_York')
    
    # Add VTIMEZONE component
    from icalendar import Timezone, TimezoneStandard, TimezoneDaylight
    from datetime import timedelta
    
    tz = Timezone()
    tz.add('tzid', 'America/New_York')
    
    # Standard time (EST: UTC-5)
    standard = TimezoneStandard()
    standard.add('dtstart', datetime(1970, 11, 1, 2, 0, 0))
    standard.add('rrule', {'freq': 'yearly', 'bymonth': 11, 'byday': '1su'})
    standard.add('tzoffsetfrom', timedelta(hours=-4))
    standard.add('tzoffsetto', timedelta(hours=-5))
    standard.add('tzname', 'EST')
    tz.add_component(standard)
    
    # Daylight time (EDT: UTC-4)
    daylight = TimezoneDaylight()
    daylight.add('dtstart', datetime(1970, 3, 8, 2, 0, 0))
    daylight.add('rrule', {'freq': 'yearly', 'bymonth': 3, 'byday': '2su'})
    daylight.add('tzoffsetfrom', timedelta(hours=-5))
    daylight.add('tzoffsetto', timedelta(hours=-4))
    daylight.add('tzname', 'EDT')
    tz.add_component(daylight)
    
    cal.add_component(tz)
    
    for shift in shifts:
        # Calculate duration using actual shift date
        shift_start = datetime.combine(shift.date, shift.start_time)
        shift_end = datetime.combine(shift.date, shift.end_time)
        duration_minutes = (shift_end - shift_start).seconds / 60  # Duration in minutes
        duration = duration_minutes / 60  # Duration in hours for display
        
        # Apply constraint checks
        constraint_status = 'Valid'
        description_parts = [f'Shift for {student.name} ({student.email})']
        
        if policy:
            if duration_minutes < policy.min_shift_length or duration_minutes > policy.max_shift_length:
                constraint_status = 'VIOLATION'
                description_parts.append(f'⚠️ CONSTRAINT VIOLATION: Shift length {duration:.1f}h outside allowed range ({policy.min_shift_length/60:.1f}-{policy.max_shift_length/60:.1f}h)')
            # Convert time to HHMM format for comparison (e.g., 8:30 -> 830)
            start_time_int = shift.start_time.hour * 100 + shift.start_time.minute
            end_time_int = shift.end_time.hour * 100 + shift.end_time.minute
            if start_time_int < policy.undesireable_start or end_time_int > policy.undesireable_end:
                if constraint_status == 'Valid':
                    constraint_status = 'Warning'
                description_parts.append(f'⚠️ Warning: Shift occurs during undesirable hours')
        
        if shift.was_manually_adjusted:
            description_parts.append('✏️ This shift was manually adjusted')
        
        # Export ALL shifts with constraint information
        event = Event()
        event.add('summary', f'Work Shift - {student.name}' + (' ⚠️' if constraint_status != 'Valid' else ''))
        event.add('description', '\n'.join(description_parts))
        event.add('dtstart', datetime.combine(shift.date, shift.start_time))
        event.add('dtend', datetime.combine(shift.date, shift.end_time))
        
        # Stable UID based on shift_id
        event.add('uid', f'shift-{shift.shift_id}@colby-shift-management.edu')
        
        # Add SEQUENCE for updates
        sequence = 1 if shift.was_manually_adjusted else 0
        event.add('sequence', sequence)
        
        event.add('location', 'Colby College')
        event.add('status', 'CONFIRMED')
        
        # Add categories for filtering
        if constraint_status == 'VIOLATION':
            event.add('categories', ['Work Shift', 'Constraint Violation'])
        elif constraint_status == 'Warning':
            event.add('categories', ['Work Shift', 'Warning'])
        else:
            event.add('categories', ['Work Shift'])
        
        # Add metadata
        event.add('created', datetime.now())
        event.add('last-modified', datetime.now())
        
        cal.add_component(event)
    
    filename = f'schedule_{student.name.replace(" ", "_")}'
    if term:
        filename += f'_{term.name.replace(" ", "_")}'
    filename += '.ics'
    
    return Response(
        cal.to_ical(),
        mimetype='text/calendar',
        headers={'Content-Disposition': f'attachment;filename={filename}'}
    )

@outputs_bp.route('/student/<int:user_id>')
@login_required
def student_view(user_id):
    """Read-only web view for student schedules"""
    # Security: Students can only view their own schedule
    if current_user.role == 'student' and current_user.user_id != user_id:
        abort(403, "You can only view your own schedule")
    
    student = User.query.get_or_404(user_id)
    if student.role != 'student':
        abort(404, "User is not a student")
    
    # Ensure student has a calendar token
    student.ensure_calendar_token()
    
    # Get supervisor contact information
    supervisors = User.query.filter_by(role='supervisor').all()
    
    # Get student's shifts
    shifts = Shift.query.filter_by(user_id=user_id).order_by(
        Shift.date, Shift.start_time
    ).all()
    
    # Group shifts by week and prepare full week data
    from datetime import timedelta
    weeks_dict = {}
    for shift in shifts:
        # Get Monday of the week
        week_start = shift.date - timedelta(days=shift.date.weekday())
        if week_start not in weeks_dict:
            weeks_dict[week_start] = {
                'week_start': week_start,
                'week_end': week_start + timedelta(days=6),
                'week_dates': [week_start + timedelta(days=i) for i in range(7)],
                'shifts': []
            }
        weeks_dict[week_start]['shifts'].append(shift)
    
    # Convert to sorted list
    all_weeks = sorted(weeks_dict.values(), key=lambda x: x['week_start'])
    
    # Get week index from query param (default to 0)
    week_index = request.args.get('week', 0, type=int)
    week_index = max(0, min(week_index, len(all_weeks) - 1)) if all_weeks else 0
    
    current_week = all_weeks[week_index] if all_weeks else None
    
    # Calculate weekly stats for current week only
    weekly_hours = 0
    weekly_shift_count = 0
    if current_week:
        for shift in current_week['shifts']:
            shift_start = datetime.combine(shift.date, shift.start_time)
            shift_end = datetime.combine(shift.date, shift.end_time)
            weekly_hours += (shift_end - shift_start).seconds / 3600
        weekly_shift_count = len(current_week['shifts'])
    
    return render_template('student_view.html', 
                          student=student,
                          current_week=current_week,
                          all_weeks=all_weeks,
                          week_index=week_index,
                          weekly_hours=weekly_hours,
                          weekly_shift_count=weekly_shift_count,
                          supervisors=supervisors)

@outputs_bp.route('/public/schedule/<token>')
def public_schedule_view(token):
    """Public web view for student schedules using secure token - no login required"""
    # Find student by calendar token (secure, stable URL for public sharing)
    student = User.query.filter_by(calendar_token=token).first_or_404()
    if student.role != 'student':
        abort(404, "User is not a student")
    
    # Get student's shifts
    shifts = Shift.query.filter_by(user_id=student.user_id).order_by(
        Shift.date, Shift.start_time
    ).all()
    
    # Group shifts by week and prepare full week data
    from datetime import timedelta
    weeks_dict = {}
    for shift in shifts:
        # Get Monday of the week
        week_start = shift.date - timedelta(days=shift.date.weekday())
        if week_start not in weeks_dict:
            weeks_dict[week_start] = {
                'week_start': week_start,
                'week_end': week_start + timedelta(days=6),
                'week_dates': [week_start + timedelta(days=i) for i in range(7)],
                'shifts': []
            }
        weeks_dict[week_start]['shifts'].append(shift)
    
    # Convert to sorted list
    all_weeks = sorted(weeks_dict.values(), key=lambda x: x['week_start'])
    
    # Get week index from query param (default to 0)
    week_index = request.args.get('week', 0, type=int)
    week_index = max(0, min(week_index, len(all_weeks) - 1)) if all_weeks else 0
    
    current_week = all_weeks[week_index] if all_weeks else None
    
    # Calculate weekly stats for current week only
    weekly_hours = 0
    weekly_shift_count = 0
    if current_week:
        for shift in current_week['shifts']:
            shift_start = datetime.combine(shift.date, shift.start_time)
            shift_end = datetime.combine(shift.date, shift.end_time)
            weekly_hours += (shift_end - shift_start).seconds / 3600
        weekly_shift_count = len(current_week['shifts'])
    
    return render_template('public_schedule_view.html', 
                          student=student,
                          current_week=current_week,
                          all_weeks=all_weeks,
                          week_index=week_index,
                          weekly_hours=weekly_hours,
                          weekly_shift_count=weekly_shift_count)

@outputs_bp.route('/all-students')
@login_required
def all_students_view():
    """View all students' individual schedules"""
    if current_user.role.lower() != 'supervisor':
        abort(403, "Only supervisors can view all student schedules")
    
    # Get search and filter parameters
    search_query = request.args.get('search', '').strip()
    shift_filter = request.args.get('filter', 'all')
    week_index = request.args.get('week', 0, type=int)
    
    # Get all students
    students = User.query.filter_by(role='student').order_by(User.name).all()
    
    # Get all weeks from all shifts to establish common week range
    from datetime import timedelta
    all_shifts = Shift.query.order_by(Shift.date).all()
    weeks_set = set()
    for shift in all_shifts:
        week_start = shift.date - timedelta(days=shift.date.weekday())
        weeks_set.add(week_start)
    all_weeks = sorted(list(weeks_set))
    
    # Ensure week_index is valid
    week_index = max(0, min(week_index, len(all_weeks) - 1)) if all_weeks else 0
    current_week_start = all_weeks[week_index] if all_weeks else None
    current_week_end = current_week_start + timedelta(days=6) if current_week_start else None
    
    # Calculate weekly stats for each student
    students_with_counts = []
    for student in students:
        # Get shifts for current week only
        if current_week_start:
            weekly_shifts = [s for s in student.shifts 
                           if current_week_start <= s.date <= current_week_end]
        else:
            weekly_shifts = []
        
        # Calculate weekly hours
        weekly_hours = 0
        for shift in weekly_shifts:
            shift_start = datetime.combine(shift.date, shift.start_time)
            shift_end = datetime.combine(shift.date, shift.end_time)
            weekly_hours += (shift_end - shift_start).seconds / 3600
        
        students_with_counts.append({
            'student': student,
            'shift_count': len(weekly_shifts),
            'weekly_hours': weekly_hours
        })
    
    # Apply search filter
    if search_query:
        students_with_counts = [
            s for s in students_with_counts 
            if search_query.lower() in s['student'].name.lower() 
            or search_query.lower() in s['student'].email.lower()
        ]
    
    # Apply shift count filter
    if shift_filter == '0-5':
        students_with_counts = [s for s in students_with_counts if s['shift_count'] <= 5]
    elif shift_filter == '6-10':
        students_with_counts = [s for s in students_with_counts if 6 <= s['shift_count'] <= 10]
    elif shift_filter == '11+':
        students_with_counts = [s for s in students_with_counts if s['shift_count'] >= 11]
    
    return render_template('all_students.html', 
                          students_with_counts=students_with_counts,
                          search_query=search_query,
                          shift_filter=shift_filter,
                          all_weeks=all_weeks,
                          week_index=week_index,
                          current_week_start=current_week_start,
                          current_week_end=current_week_end)

@outputs_bp.route('/compare-students')
@login_required
def compare_students():
    """Compare schedules of multiple students side-by-side"""
    if current_user.role.lower() != 'supervisor':
        abort(403, "Only supervisors can compare student schedules")
    
    # Get student IDs from query params (comma-separated)
    student_ids_str = request.args.get('ids', '')
    if not student_ids_str:
        return redirect(url_for('outputs.all_students_view'))
    
    try:
        student_ids = [int(id.strip()) for id in student_ids_str.split(',') if id.strip()]
    except ValueError:
        abort(400, "Invalid student IDs")
    
    # Limit to 3 students for side-by-side comparison
    student_ids = student_ids[:3]
    
    if not student_ids:
        return redirect(url_for('outputs.all_students_view'))
    
    # Get students and their shifts
    students_data = []
    for student_id in student_ids:
        student = User.query.get_or_404(student_id)
        if student.role != 'student':
            abort(404, "User is not a student")
        
        shifts = Shift.query.filter_by(user_id=student_id).order_by(
            Shift.date, Shift.start_time
        ).all()
        
        # Group shifts by week
        from datetime import timedelta
        weeks_dict = {}
        for shift in shifts:
            week_start = shift.date - timedelta(days=shift.date.weekday())
            if week_start not in weeks_dict:
                weeks_dict[week_start] = {
                    'week_start': week_start,
                    'week_end': week_start + timedelta(days=6),
                    'week_dates': [week_start + timedelta(days=i) for i in range(7)],
                    'shifts': []
                }
            weeks_dict[week_start]['shifts'].append(shift)
        
        all_weeks = sorted(weeks_dict.values(), key=lambda x: x['week_start'])
        
        students_data.append({
            'student': student,
            'shifts': shifts,
            'all_weeks': all_weeks
        })
    
    # Get week index from query param
    week_index = request.args.get('week', 0, type=int)
    
    # Calculate weekly stats for each student at the current week
    for student_data in students_data:
        student_data['week_index'] = min(week_index, len(student_data['all_weeks']) - 1) if student_data['all_weeks'] else 0
        current_week = student_data['all_weeks'][student_data['week_index']] if student_data['all_weeks'] else None
        
        weekly_hours = 0
        weekly_shift_count = 0
        if current_week:
            for shift in current_week['shifts']:
                shift_start = datetime.combine(shift.date, shift.start_time)
                shift_end = datetime.combine(shift.date, shift.end_time)
                weekly_hours += (shift_end - shift_start).seconds / 3600
            weekly_shift_count = len(current_week['shifts'])
        
        student_data['weekly_hours'] = weekly_hours
        student_data['weekly_shift_count'] = weekly_shift_count
        student_data['current_week'] = current_week
    
    return render_template('compare_students.html', 
                          students_data=students_data,
                          week_index=week_index)

@outputs_bp.route('/preview')
@login_required
def preview():
    """Live preview of all schedules"""
    # Only supervisors can see full preview
    if current_user.role.lower() != 'supervisor':
        abort(403, "Only supervisors can view the full schedule preview")
    
    # Get term
    term_id = request.args.get('term_id', type=int)
    if term_id:
        term = Term.query.get_or_404(term_id)
    else:
        term = Term.query.order_by(Term.start_date.desc()).first()
    
    if not term:
        return render_template('preview.html', current_week=None, all_weeks=[], 
                             week_index=0, term=None, policy=None, students=[])
    
    # Get policy for constraints
    policy = Policy.query.filter_by(term_id=term.term_id).first()
    
    # Get all shifts for the term
    shifts = Shift.query.filter_by(term_id=term.term_id).order_by(
        Shift.date, Shift.start_time
    ).all()
    
    # Get all students
    students = User.query.filter_by(role='student').order_by(User.name).all()
    
    # Group shifts by week
    from datetime import timedelta
    weeks_dict = {}
    
    for shift in shifts:
        # Get Monday of the week
        week_start = shift.date - timedelta(days=shift.date.weekday())
        
        if week_start not in weeks_dict:
            weeks_dict[week_start] = {
                'week_start': week_start,
                'week_end': week_start + timedelta(days=6),
                'week_dates': [week_start + timedelta(days=i) for i in range(7)],
                'days': {}
            }
        
        if shift.date not in weeks_dict[week_start]['days']:
            weeks_dict[week_start]['days'][shift.date] = []
        
        # Calculate duration and check constraints
        shift_start = datetime.combine(date.today(), shift.start_time)
        shift_end = datetime.combine(date.today(), shift.end_time)
        duration_minutes = (shift_end - shift_start).seconds / 60  # Duration in minutes to match policy units
        duration = duration_minutes / 60  # Duration in hours for display
        
        constraint_passed = True
        constraint_warnings = []
        
        if policy:
            if duration_minutes < policy.min_shift_length:
                constraint_passed = False
                constraint_warnings.append(f'Short')
            if duration_minutes > policy.max_shift_length:
                constraint_passed = False
                constraint_warnings.append(f'Long')
            # Convert time to HHMM format for comparison (e.g., 8:30 -> 830)
            start_time_int = shift.start_time.hour * 100 + shift.start_time.minute
            end_time_int = shift.end_time.hour * 100 + shift.end_time.minute
            if start_time_int < policy.undesireable_start:
                constraint_warnings.append('Early')
            if end_time_int > policy.undesireable_end:
                constraint_warnings.append('Late')
        
        weeks_dict[week_start]['days'][shift.date].append({
            'shift': shift,
            'duration': duration,
            'constraint_passed': constraint_passed,
            'warnings': constraint_warnings
        })
    
    # Calculate overlaps for each day
    for week_data in weeks_dict.values():
        for day_date, day_shifts in week_data['days'].items():
            # Convert times to minutes for each shift
            shift_times = []
            for shift_data in day_shifts:
                shift = shift_data['shift']
                start_minutes = shift.start_time.hour * 60 + shift.start_time.minute
                end_minutes = shift.end_time.hour * 60 + shift.end_time.minute
                shift_times.append({
                    'shift_data': shift_data,
                    'shift_id': shift.shift_id,
                    'start_minutes': start_minutes,
                    'end_minutes': end_minutes
                })
            
            # Detect overlaps
            for i, shift_time in enumerate(shift_times):
                overlap_count = 0
                position_in_group = 0
                
                for j, other_shift_time in enumerate(shift_times):
                    if i != j:  # Don't compare with itself
                        # Check if shifts overlap
                        if (shift_time['start_minutes'] < other_shift_time['end_minutes'] and 
                            shift_time['end_minutes'] > other_shift_time['start_minutes']):
                            overlap_count += 1
                            # Determine position: if other starts earlier, this goes to the right
                            if other_shift_time['start_minutes'] < shift_time['start_minutes']:
                                position_in_group += 1
                            elif (other_shift_time['start_minutes'] == shift_time['start_minutes'] and 
                                  other_shift_time['shift_id'] < shift_time['shift_id']):
                                position_in_group += 1
                
                # Add overlap info to shift_data
                shift_times[i]['shift_data']['has_overlap'] = overlap_count > 0
                shift_times[i]['shift_data']['overlap_position'] = position_in_group if position_in_group < 2 else 1
    
    # Convert to sorted list
    all_weeks = sorted(weeks_dict.values(), key=lambda x: x['week_start'])
    
    # Get week index from query param (default to 0)
    week_index = request.args.get('week', 0, type=int)
    week_index = max(0, min(week_index, len(all_weeks) - 1)) if all_weeks else 0
    
    current_week = all_weeks[week_index] if all_weeks else None
    
    return render_template('preview.html', 
                          current_week=current_week,
                          all_weeks=all_weeks,
                          week_index=week_index,
                          term=term,
                          policy=policy,
                          students=students)
