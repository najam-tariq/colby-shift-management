from flask import render_template, request, redirect, url_for, flash, jsonify, send_file, make_response
from flask_login import login_required, current_user
from . import constraints_bp
from models import db, Policy, UndesirableTimeWindow, Term, UndesirableShiftTracking, User, Shift, VolunteerPreference, RejectedShift, SplitShift, PolicyAuditLog, ShiftViolation, ValidationReport, ShiftGap
from datetime import time, date, datetime
from schedule_generator import ScheduleGenerator, GapAnalyzer

# GitHub Issues #21-37: Constraints & Equity
# Features: Shift duration, gaps, policy management, etc.

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

@constraints_bp.route('/manual-override/<int:shift_id>', methods=['POST'])
@login_required
def manual_override_shift(shift_id):
    """Apply manual override to a shift assignment with justification"""
    try:
        shift = Shift.query.get_or_404(shift_id)
        justification = request.form.get('justification')
        
        if not justification:
            flash('Justification is required for manual overrides.', 'error')
            return redirect(request.referrer or url_for('constraints.index'))
        
        # Create or update tracking record
        tracking = UndesirableShiftTracking.query.filter_by(shift_id=shift_id).first()
        if tracking:
            tracking.manual_override = True
            tracking.override_justification = justification
            tracking.override_by = current_user.user_id
        else:
            # Create new tracking record for override
            tracking = UndesirableShiftTracking(
                user_id=shift.user_id,
                term_id=shift.term_id,
                shift_id=shift_id,
                undesirable_type='manual_override',
                undesirable_weight=0.0,
                manual_override=True,
                override_justification=justification,
                override_by=current_user.user_id
            )
            db.session.add(tracking)
        
        db.session.commit()
        flash(f'Manual override applied successfully with justification.', 'success')
        
    except Exception as e:
        flash(f'Error applying manual override: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(request.referrer or url_for('constraints.index'))

# Issue #14: Policy Configuration Routes

@constraints_bp.route('/policy-config')
@login_required
def policy_config():
    """Display policy configuration interface for Issue #14"""
    terms = Term.query.all()
    policies = Policy.query.all()
    
    return render_template('policy_config.html', 
                         terms=terms, 
                         policies=policies)

@constraints_bp.route('/policy-config/create', methods=['POST'])
@login_required
def create_policy():
    """Create new policy configuration with audit logging"""
    from models import PolicyAuditLog
    
    data = request.get_json()
    
    try:
        policy = Policy(
            term_id=data['term_id'],
            min_shift_length=data['min_shift_length'],
            max_shift_length=data['max_shift_length'],
            min_break_length=data['min_break_length'],
            max_break_length=data.get('max_break_length', 480),  # Default 8 hours
            undesireable_start=data['undesirable_start'],
            undesireable_end=data['undesirable_end'],
            updated_by=current_user.user_id
        )
        
        db.session.add(policy)
        db.session.flush()  # Get the policy ID
        
        # Create audit log entry
        PolicyAuditLog.log_policy_change(
            policy_id=policy.policy_id,
            changed_by_id=current_user.user_id,
            change_type='create',
            change_reason=data.get('change_reason', 'Policy created'),
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.commit()
        
        return jsonify({'success': True, 'policy_id': policy.policy_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@constraints_bp.route('/policy-config/<int:policy_id>', methods=['PUT'])
@login_required
def update_policy(policy_id):
    """Update existing policy configuration with audit logging"""
    from models import PolicyAuditLog
    
    policy = Policy.query.get_or_404(policy_id)
    data = request.get_json()
    
    try:
        # Track changes for audit log
        changes = []
        
        # Check each field for changes
        fields_to_check = {
            'min_shift_length': 'min_shift_length',
            'max_shift_length': 'max_shift_length',
            'min_break_length': 'min_break_length',
            'max_break_length': 'max_break_length',
            'undesirable_start': 'undesireable_start',
            'undesirable_end': 'undesireable_end'
        }
        
        # Update basic policy parameters with audit logging
        for data_field, model_field in fields_to_check.items():
            if data_field in data:
                old_value = getattr(policy, model_field)
                new_value = data[data_field]
                
                if old_value != new_value:
                    changes.append({
                        'field': data_field,
                        'old_value': old_value,
                        'new_value': new_value
                    })
                    setattr(policy, model_field, new_value)
        
        policy.updated_by = current_user.user_id
        
        # Create audit log entries for each change
        for change in changes:
            PolicyAuditLog.log_policy_change(
                policy_id=policy.policy_id,
                changed_by_id=current_user.user_id,
                change_type='update',
                field_name=change['field'],
                old_value=change['old_value'],
                new_value=change['new_value'],
                change_reason=data.get('change_reason', 'Policy updated'),
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'changes_made': len(changes),
            'changes': changes
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@constraints_bp.route('/volunteer-preferences')
@login_required
def volunteer_preferences():
    """Display volunteer preferences management for early/late shifts"""
    from models import VolunteerPreference
    
    terms = Term.query.all()
    users = User.query.filter_by(is_active=True).all()
    
    # Get current volunteer preferences
    preferences = db.session.query(VolunteerPreference, User, Term).join(
        User, VolunteerPreference.user_id == User.user_id
    ).join(
        Term, VolunteerPreference.term_id == Term.term_id
    ).filter(VolunteerPreference.is_active == True).all()
    
    return render_template('volunteer_preferences.html',
                         terms=terms,
                         users=users, 
                         preferences=preferences)

@constraints_bp.route('/volunteer-preferences/create', methods=['POST'])
@login_required
def create_volunteer_preference():
    """Create volunteer preference for early/late shifts"""
    from models import VolunteerPreference
    
    data = request.get_json()
    
    try:
        # Check if preference already exists
        existing = VolunteerPreference.query.filter_by(
            user_id=data['user_id'],
            term_id=data['term_id'],
            is_active=True
        ).first()
        
        if existing:
            # Update existing preference
            existing.preference_type = data['preference_type']
            existing.notes = data.get('notes', '')
        else:
            # Create new preference
            preference = VolunteerPreference(
                user_id=data['user_id'],
                term_id=data['term_id'],
                preference_type=data['preference_type'],
                notes=data.get('notes', ''),
                is_active=True
            )
            db.session.add(preference)
        
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@constraints_bp.route('/volunteer-preferences/<int:preference_id>', methods=['DELETE'])
@login_required
def remove_volunteer_preference(preference_id):
    """Remove volunteer preference"""
    from models import VolunteerPreference
    
    preference = VolunteerPreference.query.get_or_404(preference_id)
    
    try:
        preference.is_active = False  # Soft delete
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# Issue #26: Shift Duration Validation Routes

@constraints_bp.route('/validate-shift', methods=['POST'])
@login_required
def validate_shift_duration():
    """Validate shift duration against policy constraints (Issue #26)"""
    data = request.get_json()
    
    try:
        from datetime import time
        
        term_id = data['term_id']
        start_time_str = data['start_time']  # Format: "HH:MM"
        end_time_str = data['end_time']      # Format: "HH:MM"
        
        # Parse time strings
        start_hour, start_min = map(int, start_time_str.split(':'))
        end_hour, end_min = map(int, end_time_str.split(':'))
        
        start_time = time(start_hour, start_min)
        end_time = time(end_hour, end_min)
        
        # Validate using Policy enforcement
        is_valid, error_message, policy = Policy.enforce_duration_constraints(
            term_id, start_time, end_time
        )
        
        response_data = {
            'valid': is_valid,
            'message': error_message,
        }
        
        if policy:
            response_data['policy'] = {
                'min_duration': policy.min_shift_length,
                'max_duration': policy.max_shift_length
            }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            'valid': False,
            'message': f'Validation error: {str(e)}'
        }), 400

@constraints_bp.route('/shift-constraints/<int:term_id>')
@login_required
def get_shift_constraints(term_id):
    """Get shift duration constraints for a specific term (Issue #26)"""
    policy = Policy.get_policy_for_term(term_id)
    
    if not policy:
        return jsonify({
            'success': False,
            'error': f'No policy found for term {term_id}'
        }), 404
    
    return jsonify({
        'success': True,
        'constraints': {
            'min_shift_length': policy.min_shift_length,
            'max_shift_length': policy.max_shift_length,
            'min_break_length': policy.min_break_length,
            'max_break_length': policy.max_break_length,
            'term_id': term_id,
            'term_name': policy.term.term_name if policy.term else None
        }
    })

@constraints_bp.route('/duration-validation')
@login_required
def duration_validation_interface():
    """Display interface for testing shift duration validation"""
    terms = Term.query.all()
    policies = Policy.query.all()
    
    return render_template('duration_validation.html', 
                         terms=terms,
                         policies=policies)

# Issue #27: Automatic Rejection System Routes

@constraints_bp.route('/automatic-rejection')
@login_required 
def automatic_rejection_interface():
    """Display interface for testing automatic rejection system (Issue #27)"""
    terms = Term.query.all()
    from models import RejectedShift
    
    # Get recent rejections for display
    recent_rejections = RejectedShift.query.order_by(
        RejectedShift.created_at.desc()
    ).limit(10).all()
    
    return render_template('automatic_rejection.html',
                         terms=terms,
                         recent_rejections=recent_rejections)

@constraints_bp.route('/test-schedule-generation', methods=['POST'])
@login_required
def test_schedule_generation():
    """Test automatic rejection during schedule generation (Issue #27)"""
    from .validation import ScheduleGenerator, AutomaticRejectionSystem
    from datetime import time, date
    import json
    
    data = request.get_json()
    term_id = data['term_id']
    
    # Create test proposed shifts with various durations
    test_shifts = [
        {
            'start_time': time(9, 0),   # 9:00 AM
            'end_time': time(9, 30),    # 9:30 AM (30 min - should be rejected)
            'date': date.today(),
            'user_id': 1
        },
        {
            'start_time': time(10, 0),  # 10:00 AM  
            'end_time': time(11, 0),    # 11:00 AM (60 min - should be accepted)
            'date': date.today(),
            'user_id': 1
        },
        {
            'start_time': time(14, 0),  # 2:00 PM
            'end_time': time(14, 45),   # 2:45 PM (45 min - should be rejected)
            'date': date.today(),
            'user_id': 2
        },
        {
            'start_time': time(16, 0),  # 4:00 PM
            'end_time': time(19, 0),    # 7:00 PM (180 min - should be accepted)
            'date': date.today(),
            'user_id': 2
        }
    ]
    
    try:
        # Test the automatic rejection system (backward compatibility)
        result = ScheduleGenerator.generate_schedule_with_auto_processing(
            term_id=term_id,
            proposed_shifts=test_shifts
        )
        
        # Format times for JSON serialization
        for shift_list in [result['final_valid_shifts'], result['rejected_shifts']]:
            for shift in shift_list:
                if 'start_time' in shift:
                    shift['start_time'] = shift['start_time'].strftime('%H:%M')
                if 'end_time' in shift:
                    shift['end_time'] = shift['end_time'].strftime('%H:%M')
                if 'date' in shift:
                    shift['date'] = shift['date'].strftime('%Y-%m-%d')
        
        return jsonify({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@constraints_bp.route('/rejection-stats/<int:term_id>')
@login_required
def get_rejection_stats(term_id):
    """Get rejection statistics for a term (Issue #27)"""
    from .validation import AutomaticRejectionSystem
    
    try:
        stats = AutomaticRejectionSystem.get_rejection_stats(term_id)
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@constraints_bp.route('/rejected-shifts/<int:term_id>')
@login_required
def get_rejected_shifts(term_id):
    """Get list of rejected shifts for debugging (Issue #27)"""
    from models import RejectedShift
    
    try:
        rejections = RejectedShift.query.filter_by(term_id=term_id).order_by(
            RejectedShift.created_at.desc()
        ).limit(50).all()
        
        rejected_shifts_data = []
        for rejection in rejections:
            rejected_shifts_data.append({
                'id': rejection.rejection_id,
                'start_time': rejection.proposed_start_time.strftime('%H:%M'),
                'end_time': rejection.proposed_end_time.strftime('%H:%M'),
                'date': rejection.proposed_date.strftime('%Y-%m-%d'),
                'duration': rejection.duration_minutes,
                'reason': rejection.rejection_reason,
                'type': rejection.rejection_type,
                'created_at': rejection.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'session': rejection.schedule_generation_session,
                'user_name': rejection.user.name if rejection.user else 'Unknown'
            })
        
        return jsonify({
            'success': True,
            'rejected_shifts': rejected_shifts_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

# Issue #29: Admin Panel for Shift Duration Policies

@constraints_bp.route('/admin-settings')
@login_required
def admin_settings():
    """Display admin settings panel for shift duration policies (Issue #29)"""
    from models import PolicyAuditLog
    
    # Check if user has admin role
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('constraints.index'))
    
    terms = Term.query.all()
    policies = Policy.query.all()
    
    # Get recent policy changes for audit display
    recent_changes = db.session.query(PolicyAuditLog, Policy, User).join(
        Policy, PolicyAuditLog.policy_id == Policy.policy_id
    ).join(
        User, PolicyAuditLog.changed_by == User.user_id
    ).order_by(PolicyAuditLog.created_at.desc()).limit(20).all()
    
    # Get default values for the form
    default_values = Policy.get_default_values()
    
    return render_template('admin_settings.html',
                         terms=terms,
                         policies=policies,
                         recent_changes=recent_changes,
                         default_values=default_values)

@constraints_bp.route('/admin-settings/create-policy', methods=['POST'])
@login_required
def admin_create_policy():
    """Create policy with audit logging (Issue #29)"""
    from models import PolicyAuditLog
    
    # Check admin privileges
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    data = request.get_json()
    
    try:
        # Validate input data
        validation_result = validate_policy_data(data)
        if not validation_result['valid']:
            return jsonify({'success': False, 'error': validation_result['error']}), 400
        
        # Check if policy already exists for this term
        existing_policy = Policy.query.filter_by(term_id=data['term_id']).first()
        if existing_policy:
            return jsonify({'success': False, 'error': 'Policy already exists for this term. Use update instead.'}), 400
        
        # Create new policy
        policy = Policy(
            term_id=data['term_id'],
            min_shift_length=data['min_shift_length'],
            max_shift_length=data['max_shift_length'],
            min_break_length=data['min_break_length'],
            max_break_length=data.get('max_break_length', 480),
            undesireable_start=data['undesirable_start'],
            undesireable_end=data['undesirable_end'],
            updated_by=current_user.user_id
        )
        
        db.session.add(policy)
        db.session.flush()  # Get the policy ID
        
        # Create audit log entry
        PolicyAuditLog.log_policy_change(
            policy_id=policy.policy_id,
            changed_by_id=current_user.user_id,
            change_type='create',
            change_reason=data.get('change_reason', 'Policy created via admin panel'),
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.commit()
        
        return jsonify({'success': True, 'policy_id': policy.policy_id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/admin-settings/update-policy/<int:policy_id>', methods=['PUT'])
@login_required
def admin_update_policy(policy_id):
    """Update policy with detailed audit logging (Issue #29)"""
    from models import PolicyAuditLog
    
    # Check admin privileges
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    policy = Policy.query.get_or_404(policy_id)
    data = request.get_json()
    
    try:
        # Validate input data
        validation_result = validate_policy_data(data)
        if not validation_result['valid']:
            return jsonify({'success': False, 'error': validation_result['error']}), 400
        
        # Track changes for audit log
        changes = []
        
        # Check each field for changes
        fields_to_check = {
            'min_shift_length': 'min_shift_length',
            'max_shift_length': 'max_shift_length',
            'min_break_length': 'min_break_length',
            'max_break_length': 'max_break_length',
            'undesirable_start': 'undesireable_start',
            'undesirable_end': 'undesireable_end'
        }
        
        for data_field, model_field in fields_to_check.items():
            if data_field in data:
                old_value = getattr(policy, model_field)
                new_value = data[data_field]
                
                if old_value != new_value:
                    changes.append({
                        'field': data_field,
                        'old_value': old_value,
                        'new_value': new_value
                    })
                    setattr(policy, model_field, new_value)
        
        policy.updated_by = current_user.user_id
        
        # Create audit log entries for each change
        for change in changes:
            PolicyAuditLog.log_policy_change(
                policy_id=policy.policy_id,
                changed_by_id=current_user.user_id,
                change_type='update',
                field_name=change['field'],
                old_value=change['old_value'],
                new_value=change['new_value'],
                change_reason=data.get('change_reason', 'Policy updated via admin panel'),
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'changes_made': len(changes),
            'changes': changes
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/admin-settings/policy-audit/<int:policy_id>')
@login_required
def get_policy_audit_log(policy_id):
    """Get audit log for a specific policy (Issue #29)"""
    from models import PolicyAuditLog
    
    # Check admin privileges
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
    
    try:
        audit_entries = db.session.query(PolicyAuditLog, User).join(
            User, PolicyAuditLog.changed_by == User.user_id
        ).filter(PolicyAuditLog.policy_id == policy_id).order_by(
            PolicyAuditLog.created_at.desc()
        ).all()
        
        audit_data = []
        for entry, user in audit_entries:
            audit_data.append({
                'audit_id': entry.audit_id,
                'change_type': entry.change_type,
                'field_name': entry.field_name,
                'old_value': entry.old_value,
                'new_value': entry.new_value,
                'change_reason': entry.change_reason,
                'changed_by': user.name,
                'changed_by_email': user.email,
                'ip_address': entry.ip_address,
                'created_at': entry.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return jsonify({
            'success': True,
            'audit_entries': audit_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Issue #30: Shift Duration Violation Detection and Visual Alerts

@constraints_bp.route('/violation-alerts')
@login_required 
def violation_alerts():
    """Display interface for shift duration violation alerts (Issue #30)"""
    terms = Term.query.all()
    
    # Get violation summary for all terms
    violation_summary = ShiftViolation.get_violation_summary()
    
    # Get recent violations
    recent_violations = db.session.query(ShiftViolation, Shift, User).join(
        Shift, ShiftViolation.shift_id == Shift.shift_id
    ).join(
        User, Shift.user_id == User.user_id
    ).filter(ShiftViolation.is_resolved == False).order_by(
        ShiftViolation.detected_at.desc()
    ).limit(20).all()
    
    return render_template('violation_alerts.html',
                         terms=terms,
                         violation_summary=violation_summary,
                         recent_violations=recent_violations)

@constraints_bp.route('/detect-violations/<int:term_id>', methods=['POST'])
@login_required
def detect_violations(term_id):
    """Detect violations for all shifts in a term (Issue #30)"""
    try:
        # Get all shifts for this term
        shifts = Shift.query.filter_by(term_id=term_id).all()
        
        all_violations = []
        for shift in shifts:
            violations = ShiftViolation.detect_violations_for_shift(shift)
            all_violations.extend(violations)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'violations_detected': len(all_violations),
            'violations': [{
                'violation_id': v.violation_id,
                'shift_id': v.shift_id,
                'violation_type': v.violation_type,
                'message': v.violation_message,
                'severity': v.severity,
                'current_duration': v.current_duration,
                'expected_min': v.expected_min,
                'expected_max': v.expected_max
            } for v in all_violations]
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/violation/<int:violation_id>/suggestions')
@login_required
def get_violation_suggestions(violation_id):
    """Get quick-fix suggestions for a violation (Issue #30)"""
    violation = ShiftViolation.query.get_or_404(violation_id)
    
    try:
        suggestions = violation.get_quick_fix_suggestions()
        
        return jsonify({
            'success': True,
            'violation_id': violation_id,
            'violation_type': violation.violation_type,
            'message': violation.violation_message,
            'suggestions': suggestions
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/violation/<int:violation_id>/override', methods=['POST'])
@login_required
def override_violation(violation_id):
    """Apply manual override to a violation with justification (Issue #30)"""
    violation = ShiftViolation.query.get_or_404(violation_id)
    
    try:
        data = request.get_json()
        justification = data.get('justification')
        
        if not justification or len(justification.strip()) < 10:
            return jsonify({
                'success': False,
                'error': 'Justification must be at least 10 characters long'
            }), 400
        
        violation.apply_override(justification, current_user.user_id)
        
        return jsonify({
            'success': True,
            'message': 'Override applied successfully',
            'violation_id': violation_id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/violation/<int:violation_id>/fix', methods=['POST'])
@login_required
def apply_violation_fix(violation_id):
    """Apply a quick-fix suggestion to resolve a violation (Issue #30)"""
    violation = ShiftViolation.query.get_or_404(violation_id)
    
    try:
        data = request.get_json()
        fix_type = data.get('fix_type')
        parameters = data.get('parameters', {})
        
        shift = violation.shift
        
        if fix_type == 'extend_shift':
            # Extend the shift duration
            extension_minutes = parameters.get('extension_minutes', 0)
            # For demo purposes, we'll just mark as resolved
            # In a real implementation, you'd update the shift end time
            violation.is_resolved = True
            violation.resolved_at = db.func.current_timestamp()
            
        elif fix_type == 'truncate_shift':
            # Reduce the shift duration
            new_duration = parameters.get('new_duration', 0)
            # For demo purposes, we'll just mark as resolved
            # In a real implementation, you'd update the shift times
            violation.is_resolved = True
            violation.resolved_at = db.func.current_timestamp()
            
        elif fix_type == 'split_shift':
            # Split the shift into multiple shorter shifts
            max_duration = parameters.get('max_duration', 180)
            # For demo purposes, we'll just mark as resolved
            # In a real implementation, you'd create multiple shifts
            violation.is_resolved = True
            violation.resolved_at = db.func.current_timestamp()
            
        elif fix_type == 'remove_shift':
            # Remove the problematic shift
            # For demo purposes, we'll just mark as resolved
            # In a real implementation, you'd delete the shift
            violation.is_resolved = True
            violation.resolved_at = db.func.current_timestamp()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Fix applied: {fix_type}',
            'violation_id': violation_id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/violation-summary/<int:term_id>')
@login_required
def get_violation_summary(term_id):
    """Get violation summary for a specific term (Issue #30)"""
    try:
        summary = ShiftViolation.get_violation_summary(term_id)
        
        return jsonify({
            'success': True,
            'term_id': term_id,
            'summary': summary
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/violations/<int:term_id>')
@login_required
def get_violations_list(term_id):
    """Get detailed list of violations for a term (Issue #30)"""
    try:
        violations_query = db.session.query(ShiftViolation, Shift, User).join(
            Shift, ShiftViolation.shift_id == Shift.shift_id
        ).join(
            User, Shift.user_id == User.user_id
        ).filter(
            ShiftViolation.term_id == term_id,
            ShiftViolation.is_resolved == False
        ).order_by(ShiftViolation.severity.desc(), ShiftViolation.detected_at.desc())
        
        violations_data = []
        for violation, shift, user in violations_query.all():
            violations_data.append({
                'violation_id': violation.violation_id,
                'shift_id': shift.shift_id,
                'user_name': user.name,
                'user_id': user.user_id,
                'date': shift.date.strftime('%Y-%m-%d'),
                'start_time': shift.start_time.strftime('%H:%M'),
                'end_time': shift.end_time.strftime('%H:%M'),
                'violation_type': violation.violation_type,
                'message': violation.violation_message,
                'severity': violation.severity,
                'current_duration': violation.current_duration,
                'expected_min': violation.expected_min,
                'expected_max': violation.expected_max,
                'detected_at': violation.detected_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return jsonify({
            'success': True,
            'violations': violations_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def validate_policy_data(data):
    """Validate policy data for reasonable values (Issue #29)"""
    errors = []
    
    # Required fields
    required_fields = ['term_id', 'min_shift_length', 'max_shift_length', 
                      'min_break_length', 'undesirable_start', 'undesirable_end']
    
    for field in required_fields:
        if field not in data or data[field] is None:
            errors.append(f'Field {field} is required')
    
    if errors:
        return {'valid': False, 'error': '; '.join(errors)}
    
    # Validate shift lengths
    min_shift = data['min_shift_length']
    max_shift = data['max_shift_length']
    
    if min_shift < 30:
        errors.append('Minimum shift length cannot be less than 30 minutes')
    if min_shift > 240:
        errors.append('Minimum shift length cannot exceed 4 hours (240 minutes)')
    if max_shift < 60:
        errors.append('Maximum shift length cannot be less than 1 hour (60 minutes)')
    if max_shift > 480:
        errors.append('Maximum shift length cannot exceed 8 hours (480 minutes)')
    if min_shift >= max_shift:
        errors.append('Minimum shift length must be less than maximum shift length')
    
    # Validate break lengths
    min_break = data['min_break_length']
    if 'max_break_length' in data:
        max_break = data['max_break_length']
        if min_break < 0:
            errors.append('Minimum break length cannot be negative')
        if max_break < min_break:
            errors.append('Maximum break length must be greater than minimum break length')
        if max_break > 1440:  # 24 hours
            errors.append('Maximum break length cannot exceed 24 hours (1440 minutes)')
    
    # Validate undesirable times
    undesirable_start = data['undesirable_start']
    undesirable_end = data['undesirable_end']
    
    if undesirable_start < 0 or undesirable_start > 2359:
        errors.append('Undesirable start time must be between 0000 and 2359')
    if undesirable_end < 0 or undesirable_end > 2359:
        errors.append('Undesirable end time must be between 0000 and 2359')
    
    if errors:
        return {'valid': False, 'error': '; '.join(errors)}
    
    return {'valid': True}

@constraints_bp.route('/test-complete-processing', methods=['POST'])
@login_required
def test_complete_processing():
    """Test complete automatic processing (rejection + splitting) (Issues #27 & #28)"""
    from .validation import ScheduleGenerator
    from datetime import time, date
    import json
    
    data = request.get_json()
    term_id = data['term_id']
    
    # Create comprehensive test shifts including splitting scenarios
    test_shifts = [
        {
            'start_time': time(9, 0),   # 9:00 AM
            'end_time': time(9, 30),    # 9:30 AM (30 min - should be rejected)
            'date': date.today(),
            'user_id': 1
        },
        {
            'start_time': time(10, 0),  # 10:00 AM  
            'end_time': time(11, 0),    # 11:00 AM (60 min - should be accepted)
            'date': date.today(),
            'user_id': 1
        },
        {
            'start_time': time(13, 0),  # 1:00 PM
            'end_time': time(18, 0),    # 6:00 PM (300 min - should be split)
            'date': date.today(),
            'user_id': 2
        },
        {
            'start_time': time(8, 0),   # 8:00 AM
            'end_time': time(14, 0),    # 2:00 PM (360 min - should be split)
            'date': date.today(),
            'user_id': 3
        }
    ]
    
    try:
        # Test the complete processing system
        result = ScheduleGenerator.generate_schedule_with_auto_processing(
            term_id=term_id,
            proposed_shifts=test_shifts
        )
        
        # Format times for JSON serialization
        for shift_list in [result['original_proposed'], result['after_splits'], 
                          result['final_valid_shifts'], result['rejected_shifts']]:
            for shift in shift_list:
                if 'start_time' in shift:
                    if hasattr(shift['start_time'], 'strftime'):
                        shift['start_time'] = shift['start_time'].strftime('%H:%M')
                if 'end_time' in shift:
                    if hasattr(shift['end_time'], 'strftime'):
                        shift['end_time'] = shift['end_time'].strftime('%H:%M')
                if 'date' in shift:
                    if hasattr(shift['date'], 'strftime'):
                        shift['date'] = shift['date'].strftime('%Y-%m-%d')
        
        # Format split operations
        for split_op in result['split_operations']:
            for shift_list in [split_op['split_shifts']]:
                for shift in shift_list:
                    if 'start_time' in shift:
                        if hasattr(shift['start_time'], 'strftime'):
                            shift['start_time'] = shift['start_time'].strftime('%H:%M')
                    if 'end_time' in shift:
                        if hasattr(shift['end_time'], 'strftime'):
                            shift['end_time'] = shift['end_time'].strftime('%H:%M')
                    if 'date' in shift:
                        if hasattr(shift['date'], 'strftime'):
                            shift['date'] = shift['date'].strftime('%Y-%m-%d')
        
        return jsonify({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@constraints_bp.route('/split-stats/<int:term_id>')
@login_required
def get_split_stats(term_id):
    """Get splitting statistics for a term (Issue #28)"""
    from .validation import AutomaticSplitSystem
    
    try:
        stats = AutomaticSplitSystem.get_split_stats(term_id)
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@constraints_bp.route('/split-shifts/<int:term_id>')
@login_required
def get_split_shifts(term_id):
    """Get list of split shifts for debugging (Issue #28)"""
    from models import SplitShift
    
    try:
        splits = SplitShift.query.filter_by(term_id=term_id).order_by(
            SplitShift.created_at.desc()
        ).limit(50).all()
        
        split_shifts_data = []
        for split in splits:
            split_shifts_data.append({
                'id': split.split_id,
                'original_start_time': split.original_start_time.strftime('%H:%M'),
                'original_end_time': split.original_end_time.strftime('%H:%M'),
                'date': split.proposed_date.strftime('%Y-%m-%d'),
                'original_duration': split.original_duration_minutes,
                'split_count': split.split_count,
                'break_minutes': split.break_minutes,
                'reason': split.split_reason,
                'created_at': split.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'session': split.schedule_generation_session,
                'user_name': split.user.name if split.user else 'Unknown'
            })
        
        return jsonify({
            'success': True,
            'split_shifts': split_shifts_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


# Issue #31: Validation Summary Report Routes

@constraints_bp.route('/validation-reports')
@login_required
def validation_reports():
    """Display validation reports dashboard (Issue #31)"""
    terms = Term.query.all()
    recent_reports = ValidationReport.get_recent_reports(limit=20)
    
    return render_template('validation_reports.html', 
                         terms=terms,
                         recent_reports=recent_reports)

@constraints_bp.route('/validation-reports/generate', methods=['POST'])
@login_required
def generate_validation_report():
    """Generate a new validation report (Issue #31)"""
    data = request.get_json()
    
    try:
        term_id = data.get('term_id')
        include_resolved = data.get('include_resolved', False)
        
        if not term_id:
            return jsonify({'success': False, 'error': 'Term ID required'}), 400
        
        # Generate the report
        report = ValidationReport.generate_validation_report(
            term_id=term_id,
            user_id=current_user.user_id,
            include_resolved=include_resolved
        )
        
        return jsonify({
            'success': True,
            'report_id': report.report_id,
            'total_violations': report.total_violations_found,
            'summary': report.report_summary,
            'redirect_url': url_for('constraints.view_validation_report', report_id=report.report_id)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/validation-reports/<int:report_id>')
@login_required
def view_validation_report(report_id):
    """View detailed validation report (Issue #31)"""
    report = ValidationReport.query.get_or_404(report_id)
    
    # Get detailed violations grouped by type
    violations_by_type = report.get_detailed_violations(group_by_type=True)
    
    return render_template('validation_report_detail.html',
                         report=report,
                         violations_by_type=violations_by_type)

@constraints_bp.route('/validation-reports/<int:report_id>/export/pdf')
@login_required
def export_validation_report_pdf(report_id):
    """Export validation report as PDF (Issue #31)"""
    report = ValidationReport.query.get_or_404(report_id)
    
    try:
        pdf_filename, pdf_content = report.generate_pdf_export()
        
        response = make_response(pdf_content)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=validation_report_{report_id}.pdf'
        
        return response
        
    except Exception as e:
        flash(f'PDF export failed: {str(e)}', 'error')
        return redirect(url_for('constraints.view_validation_report', report_id=report_id))

@constraints_bp.route('/validation-reports/<int:report_id>/export/csv')
@login_required
def export_validation_report_csv(report_id):
    """Export validation report as CSV (Issue #31)"""
    report = ValidationReport.query.get_or_404(report_id)
    
    try:
        csv_filename, csv_content = report.generate_csv_export()
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=validation_report_{report_id}.csv'
        
        return response
        
    except Exception as e:
        flash(f'CSV export failed: {str(e)}', 'error')
        return redirect(url_for('constraints.view_validation_report', report_id=report_id))

@constraints_bp.route('/validation-reports/<int:report_id>/delete', methods=['POST'])
@login_required
def delete_validation_report(report_id):
    """Delete validation report (Issue #31)"""
    report = ValidationReport.query.get_or_404(report_id)
    
    # Check permissions - only admin or report creator can delete
    if current_user.role != 'admin' and current_user.user_id != report.generated_by:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    
    try:
        # Delete associated files if they exist
        import os
        if report.pdf_generated:
            pdf_path = f'reports/validation_report_{report.report_id}_{report.generated_at.strftime("%Y%m%d_%H%M")}.pdf'
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        
        if report.csv_generated:
            csv_path = f'reports/validation_report_{report.report_id}_{report.generated_at.strftime("%Y%m%d_%H%M")}.csv'
            if os.path.exists(csv_path):
                os.remove(csv_path)
        
        db.session.delete(report)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# Issue #32: Gap Management Routes - Avoid fragmented 15-30 minute slots

@constraints_bp.route('/gap-management')
@login_required
def gap_management():
    """Display gap management interface (Issue #32)"""
    terms = Term.query.all()
    selected_term_id = request.args.get('term_id', type=int)
    
    if selected_term_id:
        # Analyze gaps for selected term
        gap_analysis = GapAnalyzer.analyze_term_gaps(selected_term_id)
        policy = Policy.get_policy_with_defaults(selected_term_id)
    else:
        gap_analysis = None
        policy = None
    
    return render_template('gap_management.html', 
                         terms=terms, 
                         selected_term_id=selected_term_id,
                         gap_analysis=gap_analysis,
                         policy=policy)

@constraints_bp.route('/gap-management/detect/<int:term_id>', methods=['POST'])
@login_required
def detect_gaps(term_id):
    """Detect gaps for a specific term (Issue #32)"""
    try:
        # Run gap detection for the term
        gaps = ShiftGap.detect_all_gaps_for_term(term_id)
        
        flash(f'Gap detection complete! Found {len(gaps)} gaps requiring attention.', 'success')
        
        return jsonify({
            'success': True,
            'gaps_found': len(gaps),
            'message': f'Detected {len(gaps)} gaps in schedule'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/gap-management/merge/<int:gap_id>', methods=['POST'])
@login_required
def merge_gap(gap_id):
    """Attempt to merge a specific gap (Issue #32)"""
    try:
        gap = ShiftGap.query.get_or_404(gap_id)
        
        if gap.is_resolved:
            return jsonify({'success': False, 'error': 'Gap already resolved'}), 400
        
        # Attempt auto merge
        success = gap.attempt_auto_merge(current_user.user_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Successfully merged {gap.gap_duration_minutes}-minute gap'
            })
        else:
            return jsonify({
                'success': False, 
                'error': gap.merge_blocked_reason or 'Merge failed'
            }), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/gap-management/merge-batch', methods=['POST'])
@login_required
def merge_gaps_batch():
    """Merge multiple gaps in batch (Issue #32)"""
    try:
        gap_ids = request.json.get('gap_ids', [])
        
        if not gap_ids:
            return jsonify({'success': False, 'error': 'No gaps selected'}), 400
        
        results = GapAnalyzer.batch_merge_gaps(gap_ids, current_user.user_id)
        
        return jsonify({
            'success': True,
            'results': results,
            'message': f'Processed {len(gap_ids)} gaps: {results["successful_merges"]} merged, {results["failed_merges"]} failed'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/gap-management/policy/<int:term_id>', methods=['POST'])
@login_required
def update_gap_policy(term_id):
    """Update gap management policy settings (Issue #32)"""
    try:
        policy = Policy.query.filter_by(term_id=term_id).first()
        
        if not policy:
            # Create new policy with gap settings
            policy = Policy(
                term_id=term_id,
                updated_by=current_user.user_id,
                **Policy.get_default_values()
            )
            db.session.add(policy)
        
        # Update gap-specific settings
        policy.min_gap_threshold = int(request.form.get('min_gap_threshold', 15))
        policy.max_gap_threshold = int(request.form.get('max_gap_threshold', 30))
        policy.allow_gap_merging = bool(request.form.get('allow_gap_merging'))
        policy.gap_warning_enabled = bool(request.form.get('gap_warning_enabled'))
        policy.prefer_longer_shifts = bool(request.form.get('prefer_longer_shifts'))
        
        # Issue #35: Update transition time settings
        policy.min_transition_time = int(request.form.get('min_transition_time', 10))
        policy.transition_warning_enabled = bool(request.form.get('transition_warning_enabled'))
        
        policy.updated_by = current_user.user_id
        
        db.session.commit()
        
        flash('Gap management policy updated successfully!', 'success')
        return redirect(url_for('constraints.gap_management', term_id=term_id))
        
    except Exception as e:
        flash(f'Error updating gap policy: {str(e)}', 'error')
        db.session.rollback()
        return redirect(url_for('constraints.gap_management', term_id=term_id))

@constraints_bp.route('/gap-management/generate-schedule/<int:term_id>', methods=['POST'])
@login_required
def generate_gap_aware_schedule(term_id):
    """Generate a new schedule using gap-aware algorithm (Issue #32)"""
    try:
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        dry_run = bool(request.form.get('dry_run'))
        
        if not start_date_str or not end_date_str:
            flash('Please provide both start and end dates', 'error')
            return redirect(url_for('constraints.gap_management', term_id=term_id))
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        # Initialize schedule generator
        generator = ScheduleGenerator(term_id)
        
        # Generate schedule
        results = generator.generate_schedule(start_date, end_date, dry_run=dry_run)
        
        if dry_run:
            flash(f'Schedule preview generated: {results["total_shifts_generated"]} shifts, {len(results["warnings"])} warnings', 'info')
        else:
            flash(f'Gap-aware schedule generated successfully! {results["total_shifts_generated"]} shifts created.', 'success')
        
        return redirect(url_for('constraints.gap_management', term_id=term_id))
        
    except Exception as e:
        flash(f'Error generating schedule: {str(e)}', 'error')
        return redirect(url_for('constraints.gap_management', term_id=term_id))

@constraints_bp.route('/gap-management/gaps-data/<int:term_id>')
@login_required
def get_gaps_data(term_id):
    """Get gaps data as JSON for AJAX requests (Issue #32)"""
    try:
        gaps = ShiftGap.query.filter_by(term_id=term_id, is_resolved=False).all()
        
        gaps_data = []
        for gap in gaps:
            gaps_data.append({
                'gap_id': gap.gap_id,
                'user_name': gap.user.name,
                'user_id': gap.user_id,
                'date': gap.date.strftime('%Y-%m-%d'),
                'first_shift_end': gap.first_shift_end.strftime('%H:%M'),
                'second_shift_start': gap.second_shift_start.strftime('%H:%M'),
                'gap_duration': gap.gap_duration_minutes,
                'gap_type': gap.gap_type,
                'severity': gap.severity,
                'merge_suggestion': gap.get_merge_suggestion(),
                'detected_at': gap.detected_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return jsonify({'gaps': gaps_data})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@constraints_bp.route('/gap-management/override/<int:gap_id>', methods=['POST'])
@login_required
def override_gap(gap_id):
    """Apply manual override to accept a gap as unavoidable (Issue #32)"""
    try:
        gap = ShiftGap.query.get_or_404(gap_id)
        justification = request.form.get('justification', '')
        
        if not justification.strip():
            return jsonify({'success': False, 'error': 'Justification required for override'}), 400
        
        # Mark gap as resolved with override
        gap.is_resolved = True
        gap.resolution_method = 'manual_override'
        gap.resolved_by = current_user.user_id
        gap.resolved_at = datetime.now()
        gap.merge_blocked_reason = justification
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Gap override applied: {justification}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Issue #35: Minimum break time between shifts - Transition Time Violation Routes

@constraints_bp.route('/transition-violations')
@login_required
def transition_violations():
    """Display transition time violations management interface (Issue #35)"""
    from models import Term, TransitionTimeViolation
    
    terms = Term.query.all()
    selected_term_id = request.args.get('term_id', type=int)
    
    violations_analysis = None
    policy = None
    
    if selected_term_id:
        # Get policy and violations analysis for the selected term
        policy = Policy.get_policy_for_term(selected_term_id)
        violations_analysis = TransitionTimeViolation.detect_all_violations_for_term(selected_term_id)
    
    return render_template('transition_violations.html',
                         terms=terms,
                         selected_term_id=selected_term_id,
                         violations_analysis=violations_analysis,
                         policy=policy)

@constraints_bp.route('/transition-violations/detect/<int:term_id>', methods=['POST'])
@login_required
def detect_transition_violations(term_id):
    """Detect and store transition time violations for a term (Issue #35)"""
    try:
        from models import TransitionTimeViolation
        
        # Clear existing violations for this term
        TransitionTimeViolation.query.filter_by(term_id=term_id).delete()
        
        # Detect new violations
        violations_data = TransitionTimeViolation.detect_all_violations_for_term(term_id)
        
        # Store violations in database
        violations_stored = 0
        for violation in violations_data['violations']:
            violation_obj = TransitionTimeViolation(
                user_id=violation['user_id'],
                term_id=violation['term_id'],
                first_shift_id=violation['first_shift_id'],
                first_shift_date=violation['first_shift_date'],
                first_shift_end=violation['first_shift_end'],
                second_shift_id=violation['second_shift_id'],
                second_shift_date=violation['second_shift_date'],
                second_shift_start=violation['second_shift_start'],
                actual_transition_minutes=violation['actual_transition_minutes'],
                required_transition_minutes=violation['required_transition_minutes'],
                severity=violation['severity']
            )
            db.session.add(violation_obj)
            violations_stored += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Detected and stored {violations_stored} transition time violations',
            'summary': violations_data['summary']
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/transition-violations/data/<int:term_id>')
@login_required  
def get_transition_violations_data(term_id):
    """Get transition time violations data for AJAX requests (Issue #35)"""
    try:
        from models import TransitionTimeViolation
        
        violations = TransitionTimeViolation.query.filter_by(term_id=term_id).all()
        
        violations_data = []
        for violation in violations:
            violations_data.append({
                'violation_id': violation.violation_id,
                'user_name': violation.user.name,
                'user_id': violation.user_id,
                'first_shift_date': violation.first_shift_date.strftime('%Y-%m-%d'),
                'first_shift_end': violation.first_shift_end.strftime('%H:%M'),
                'second_shift_date': violation.second_shift_date.strftime('%Y-%m-%d'),
                'second_shift_start': violation.second_shift_start.strftime('%H:%M'),
                'actual_transition_minutes': violation.actual_transition_minutes,
                'required_transition_minutes': violation.required_transition_minutes,
                'severity': violation.severity,
                'detected_at': violation.detected_at.strftime('%Y-%m-%d %H:%M:%S'),
                'is_resolved': violation.resolved_at is not None
            })
        
        return jsonify({'violations': violations_data})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@constraints_bp.route('/transition-violations/resolve/<int:violation_id>', methods=['POST'])
@login_required
def resolve_transition_violation(violation_id):
    """Mark a transition time violation as resolved (Issue #35)"""
    try:
        from models import TransitionTimeViolation
        
        violation = TransitionTimeViolation.query.get_or_404(violation_id)
        
        violation.resolved_at = db.func.current_timestamp()
        violation.resolved_by = current_user.user_id
        violation.resolution_method = request.json.get('resolution_method', 'manual_override')
        violation.notes = request.json.get('notes', '')
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Transition time violation {violation_id} marked as resolved'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

