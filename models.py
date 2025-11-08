from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import uuid

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    email = db.Column(db.Text, nullable=False, unique=True)
    role = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    password_hash = db.Column(db.Text, nullable=False)
    calendar_token = db.Column(db.Text, nullable=True, unique=True)  # UUID for secure calendar feed access
    
    availability = db.relationship('Availability', back_populates='user', cascade='all, delete')
    shifts = db.relationship('Shift', back_populates='user', cascade='all, delete')
    policies_updated = db.relationship('Policy', back_populates='updated_by_user', cascade='all, delete')
    policy_audit_logs = db.relationship('PolicyAuditLog', foreign_keys='PolicyAuditLog.changed_by', cascade='all, delete')
    undesirable_shifts = db.relationship('UndesirableShiftTracking', foreign_keys='UndesirableShiftTracking.user_id', back_populates='user', cascade='all, delete')
    
    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password against hash"""
        return check_password_hash(self.password_hash, password)
    
    def get_id(self):
        """Return user ID as string for Flask-Login"""
        return str(self.user_id)
    
    def ensure_calendar_token(self):
        """Generate calendar token if it doesn't exist"""
        if not self.calendar_token:
            self.calendar_token = str(uuid.uuid4())
            db.session.commit()
        return self.calendar_token
    
    @property
    def calendar_token_or_create(self):
        """Property that ensures calendar token exists before returning it"""
        return self.ensure_calendar_token()
    
    def __repr__(self):
        return f'<User {self.email}>'
    
class Availability(db.Model):
    __tablename__ = "availability"
    
    availiability_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    term_id = db.Column(db.Integer, db.ForeignKey('terms.term_id'))
    day_of_week = db.Column(db.Text, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_exception = db.Column(db.Boolean, nullable=False, default=False)
    
    user = db.relationship('User', back_populates='availability')
    term = db.relationship('Term', back_populates='availability')
    
    def __repr__(self):
        return f'<Availability {self.availiability_id} for User {self.user_id}>'

class Term(db.Model):
    __tablename__ = 'terms'
    
    term_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    availability_deadline = db.Column(db.Date, nullable=False)
    locked = db.Column(db.Boolean, nullable=False, default=False)
    
    availability = db.relationship('Availability', back_populates='term', cascade='all, delete')
    staffing_needs = db.relationship('StaffingNeeds', back_populates='term', cascade='all, delete')
    shifts = db.relationship('Shift', back_populates='term', cascade='all, delete')
    policies = db.relationship('Policy', back_populates='term', cascade='all, delete')
    undesirable_shift_tracking = db.relationship('UndesirableShiftTracking', back_populates='term', cascade='all, delete')
    
    def __repr__(self):
        return f'<Term {self.name}>'

class Policy(db.Model):
    __tablename__ = 'policy'
    
    policy_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.term_id'), nullable=False)
    min_shift_length = db.Column(db.Integer, nullable=False)
    max_shift_length = db.Column(db.Integer, nullable=False)
    min_break_length = db.Column(db.Integer, nullable=False)
    max_break_length = db.Column(db.Integer, nullable=False)
    undesireable_start = db.Column(db.Integer, nullable=False)
    undesireable_end = db.Column(db.Integer, nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    
    # Issue #32: Gap management settings to avoid fragmented 15-30 minute slots
    min_gap_threshold = db.Column(db.Integer, nullable=False, default=15)  # Minimum gap to be considered problematic (minutes)
    max_gap_threshold = db.Column(db.Integer, nullable=False, default=30)  # Maximum gap to be considered small (minutes)
    allow_gap_merging = db.Column(db.Boolean, nullable=False, default=True)  # Allow automatic gap merging
    gap_warning_enabled = db.Column(db.Boolean, nullable=False, default=True)  # Enable gap warnings
    prefer_longer_shifts = db.Column(db.Boolean, nullable=False, default=True)  # Prefer longer shifts over fragmented ones
    
    # Issue #35: Minimum break time between consecutive shifts for the same student
    min_transition_time = db.Column(db.Integer, nullable=False, default=10)  # Minimum minutes between consecutive shifts
    transition_warning_enabled = db.Column(db.Boolean, nullable=False, default=True)  # Enable transition time warnings
    
    term = db.relationship('Term', back_populates='policies')
    updated_by_user = db.relationship('User', back_populates='policies_updated')
    undesirable_windows = db.relationship('UndesirableTimeWindow', back_populates='policy', cascade='all, delete')
    
    def __repr__(self):
        return f'<Policy {self.policy_id} for Term {self.term_id}>'
    
    def validate_shift_duration(self, duration_minutes):
        """
        Validate if a shift duration meets policy constraints (Issue #26)
        
        Args:
            duration_minutes (int): Duration of the shift in minutes
            
        Returns:
            tuple: (is_valid, error_message)
        """
        if duration_minutes < self.min_shift_length:
            return False, f"Shift duration ({duration_minutes} min) is below minimum ({self.min_shift_length} min)"
        
        if duration_minutes > self.max_shift_length:
            return False, f"Shift duration ({duration_minutes} min) exceeds maximum ({self.max_shift_length} min)"
            
        return True, None
    
    def validate_shift_times(self, start_time, end_time):
        """
        Validate shift start and end times meet policy constraints
        
        Args:
            start_time (time): Start time of the shift
            end_time (time): End time of the shift
            
        Returns:
            tuple: (is_valid, error_message)
        """
        from datetime import datetime, time
        
        # Convert times to datetime objects for calculation
        start_dt = datetime.combine(datetime.today(), start_time)
        end_dt = datetime.combine(datetime.today(), end_time)
        
        # Handle overnight shifts
        if end_dt < start_dt:
            end_dt = end_dt.replace(day=end_dt.day + 1)
        
        # Calculate duration in minutes
        duration = (end_dt - start_dt).total_seconds() / 60
        
        return self.validate_shift_duration(int(duration))
    
    @classmethod
    def get_policy_for_term(cls, term_id):
        """Get the active policy for a specific term"""
        return cls.query.filter_by(term_id=term_id).first()
    
    @classmethod
    def get_policy_with_defaults(cls, term_id):
        """Get policy for term or return default values if none exists (Issue #29)"""
        policy = cls.get_policy_for_term(term_id)
        if policy:
            return policy
            
        # Return a policy object with default values (not saved to DB)
        default_policy = cls(
            term_id=term_id,
            min_shift_length=60,    # 1 hour minimum
            max_shift_length=180,   # 3 hour maximum
            min_break_length=60,    # 1 hour break minimum
            max_break_length=480,   # 8 hour break maximum
            undesireable_start=600, # 6:00 AM
            undesireable_end=800,   # 8:00 AM
            updated_by=0,           # System default
            # Issue #32: Gap management defaults
            min_gap_threshold=15,
            max_gap_threshold=30,
            allow_gap_merging=True,
            gap_warning_enabled=True,
            prefer_longer_shifts=True,
            # Issue #35: Transition time defaults
            min_transition_time=10,
            transition_warning_enabled=True
        )
        return default_policy
    
    @classmethod
    def get_default_values(cls):
        """Get default policy values for new policies (Issue #29)"""
        return {
            'min_shift_length': 60,    # 1 hour minimum
            'max_shift_length': 180,   # 3 hour maximum  
            'min_break_length': 60,    # 1 hour break minimum
            'max_break_length': 480,   # 8 hour break maximum
            'undesireable_start': 600, # 6:00 AM
            'undesireable_end': 800,   # 8:00 AM
            # Issue #32: Gap management defaults
            'min_gap_threshold': 15,
            'max_gap_threshold': 30,
            'allow_gap_merging': True,
            'gap_warning_enabled': True,
            'prefer_longer_shifts': True,
            # Issue #35: Transition time defaults
            'min_transition_time': 10,
            'transition_warning_enabled': True
        }
    
    @classmethod
    def enforce_duration_constraints(cls, term_id, start_time, end_time):
        """
        Enforce shift duration constraints for a term (Issue #26)
        
        Returns:
            tuple: (is_valid, error_message, policy)
        """
        policy = cls.get_policy_for_term(term_id)
        if not policy:
            return False, f"No policy found for term {term_id}", None
            
        is_valid, error = policy.validate_shift_times(start_time, end_time)
        return is_valid, error, policy
    
    def validate_transition_time(self, first_shift_end, second_shift_start, date=None):
        """
        Validate if there's adequate transition time between consecutive shifts (Issue #35)
        
        Args:
            first_shift_end (time): End time of the first shift
            second_shift_start (time): Start time of the second shift
            date (date, optional): Date for the shifts (for overnight handling)
            
        Returns:
            tuple: (is_valid, transition_minutes, error_message)
        """
        from datetime import datetime, timedelta, time
        
        # Convert times to datetime objects for calculation
        if date:
            first_end_dt = datetime.combine(date, first_shift_end)
            second_start_dt = datetime.combine(date, second_shift_start)
        else:
            first_end_dt = datetime.combine(datetime.today(), first_shift_end)
            second_start_dt = datetime.combine(datetime.today(), second_shift_start)
        
        # Handle overnight transition (second shift starts next day)
        if second_start_dt <= first_end_dt:
            second_start_dt = second_start_dt + timedelta(days=1)
        
        # Calculate transition time in minutes
        transition_time = (second_start_dt - first_end_dt).total_seconds() / 60
        
        if transition_time < self.min_transition_time:
            return False, int(transition_time), f"Insufficient transition time ({int(transition_time)} min) between shifts. Minimum required: {self.min_transition_time} min"
        
        return True, int(transition_time), None
    
    @classmethod
    def validate_shifts_transition_time(cls, term_id, shifts_list):
        """
        Validate transition times for a list of shifts for the same student (Issue #35)
        
        Args:
            term_id (int): Term ID to get policy
            shifts_list (list): List of shift dictionaries with keys: start_time, end_time, date
            
        Returns:
            list: List of validation results with transition time violations
        """
        policy = cls.get_policy_for_term(term_id)
        if not policy:
            return [{"error": f"No policy found for term {term_id}"}]
        
        violations = []
        
        # Sort shifts by date and start time
        sorted_shifts = sorted(shifts_list, key=lambda x: (x['date'], x['start_time']))
        
        for i in range(len(sorted_shifts) - 1):
            current_shift = sorted_shifts[i]
            next_shift = sorted_shifts[i + 1]
            
            # Only check transitions on the same day or consecutive days
            day_diff = (next_shift['date'] - current_shift['date']).days
            if day_diff > 1:
                continue
                
            is_valid, transition_minutes, error = policy.validate_transition_time(
                current_shift['end_time'],
                next_shift['start_time'],
                current_shift['date']
            )
            
            if not is_valid:
                violations.append({
                    'shift_1': current_shift,
                    'shift_2': next_shift,
                    'transition_minutes': transition_minutes,
                    'required_minutes': policy.min_transition_time,
                    'error': error
                })
        
        return violations

class UndesirableTimeWindow(db.Model):
    __tablename__ = 'undesirable_time_windows'
    
    window_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    policy_id = db.Column(db.Integer, db.ForeignKey('policy.policy_id'), nullable=False)
    name = db.Column(db.Text, nullable=False)  # e.g., "Early Morning", "Late Evening", "Weekend"
    day_of_week = db.Column(db.Integer, nullable=True)  # 0-6 for Mon-Sun, NULL for all days
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    weight = db.Column(db.Float, nullable=False, default=1.0)  # Higher weight = more undesirable
    window_type = db.Column(db.Text, nullable=False)  # "early_morning", "late_evening", "weekend", "custom"
    
    policy = db.relationship('Policy', back_populates='undesirable_windows')
    
    def __repr__(self):
        return f'<UndesirableTimeWindow {self.name} for Policy {self.policy_id}>'

class UndesirableShiftTracking(db.Model):
    """Model for tracking undesirable shifts per student (Issue #37)"""
    __tablename__ = 'undesirable_shift_tracking'
    
    tracking_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.term_id'), nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('shift.shift_id'), nullable=False)
    undesirable_type = db.Column(db.Text, nullable=False)  # 'early_morning', 'late_evening', 'weekend', 'custom'
    undesirable_weight = db.Column(db.Float, nullable=False)  # Weight of undesirability
    assigned_date = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    manual_override = db.Column(db.Boolean, nullable=False, default=False)
    override_justification = db.Column(db.Text, nullable=True)
    override_by = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    
    user = db.relationship('User', foreign_keys=[user_id], back_populates='undesirable_shifts')
    term = db.relationship('Term', back_populates='undesirable_shift_tracking')
    shift = db.relationship('Shift', back_populates='undesirable_tracking')
    override_by_user = db.relationship('User', foreign_keys=[override_by])
    
    def __repr__(self):
        return f'<UndesirableShiftTracking {self.undesirable_type} for User {self.user_id}>'

class StaffingNeeds(db.Model):
    __tablename__ = 'staffing_needs'
    
    need_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.term_id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    role_required = db.Column(db.Text, nullable=False)
    required_count = db.Column(db.Integer, nullable=False)
    
    term = db.relationship('Term', back_populates='staffing_needs')
    
    @property
    def student_capacity(self):
        """Backward compatibility property - maps to required_count"""
        return self.required_count
    
    @student_capacity.setter
    def student_capacity(self, value):
        """Backward compatibility setter - maps to required_count"""
        self.required_count = value
    
    def __repr__(self):
        return f'<StaffingNeeds {self.need_id} for Term {self.term_id}>'

class Shift(db.Model):
    __tablename__ = 'shift'
    
    shift_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.term_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    was_manually_adjusted = db.Column(db.Boolean, nullable=False, default=False)
    
    term = db.relationship('Term', back_populates='shifts')
    user = db.relationship('User', back_populates='shifts')
    undesirable_tracking = db.relationship('UndesirableShiftTracking', back_populates='shift', cascade='all, delete')
    
    def __repr__(self):
        return f'<Shift {self.shift_id} for User {self.user_id} on {self.date}>'
    
    def get_duration_minutes(self):
        """Get the duration of this shift in minutes"""
        from datetime import datetime, timedelta
        
        start_dt = datetime.combine(self.date, self.start_time)
        end_dt = datetime.combine(self.date, self.end_time)
        
        # Handle overnight shifts
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
        
        duration = (end_dt - start_dt).total_seconds() / 60
        return int(duration)
    
    def validate_duration_constraints(self):
        """
        Validate this shift meets policy duration constraints (Issue #26)
        
        Returns:
            tuple: (is_valid, error_message)
        """
        policy = Policy.get_policy_for_term(self.term_id)
        if not policy:
            return False, f"No policy found for term {self.term_id}"
            
        return policy.validate_shift_times(self.start_time, self.end_time)
    
    @classmethod
    def validate_before_save(cls, term_id, start_time, end_time):
        """
        Validate shift constraints before saving (Issue #26)
        Used by forms and schedule generators
        """
        return Policy.enforce_duration_constraints(term_id, start_time, end_time)

class VolunteerPreference(db.Model):
    """Model to track students who volunteer for early or late shifts (Issue #14)"""
    __tablename__ = 'volunteer_preferences'
    
    preference_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.term_id'), nullable=False)
    preference_type = db.Column(db.Text, nullable=False)  # 'early', 'late', 'both'
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_date = db.Column(db.Date, nullable=False, default=db.func.current_date())
    notes = db.Column(db.Text, nullable=True)  # Optional notes about the preference
    
    user = db.relationship('User', backref='volunteer_preferences')
    term = db.relationship('Term', backref='volunteer_preferences')
    
    def __repr__(self):
        return f'<VolunteerPreference {self.preference_type} for User {self.user_id}>'

class RejectedShift(db.Model):
    """Model to track automatically rejected shifts for debugging (Issue #27)"""
    __tablename__ = 'rejected_shifts'
    
    rejection_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.term_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)  # Might be null during generation
    proposed_start_time = db.Column(db.Time, nullable=False)
    proposed_end_time = db.Column(db.Time, nullable=False)
    proposed_date = db.Column(db.Date, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    rejection_reason = db.Column(db.Text, nullable=False)
    rejection_type = db.Column(db.Text, nullable=False)  # 'duration', 'policy', 'coverage'
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    schedule_generation_session = db.Column(db.Text, nullable=True)  # To group rejections by generation run
    
    term = db.relationship('Term', backref='rejected_shifts')
    user = db.relationship('User', backref='rejected_shifts')
    
    def __repr__(self):
        return f'<RejectedShift {self.rejection_id}: {self.duration_minutes}min - {self.rejection_reason}>'

class SplitShift(db.Model):
    """Model to track automatically split shifts for logging (Issue #28)"""
    __tablename__ = 'split_shifts'
    
    split_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.term_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)  # Might be null during generation
    original_start_time = db.Column(db.Time, nullable=False)
    original_end_time = db.Column(db.Time, nullable=False)
    original_duration_minutes = db.Column(db.Integer, nullable=False)
    proposed_date = db.Column(db.Date, nullable=False)
    split_count = db.Column(db.Integer, nullable=False)  # How many shifts it was split into
    break_minutes = db.Column(db.Integer, nullable=False)  # Break time inserted between splits
    split_reason = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    schedule_generation_session = db.Column(db.Text, nullable=True)  # To group splits by generation run
    
    term = db.relationship('Term', backref='split_shifts')
    user = db.relationship('User', backref='split_shifts')
    
    def __repr__(self):
        return f'<SplitShift {self.split_id}: {self.original_duration_minutes}min → {self.split_count} shifts>'

class PolicyAuditLog(db.Model):
    """Model to track all policy changes for audit purposes (Issue #29)"""
    __tablename__ = 'policy_audit_logs'
    
    audit_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    policy_id = db.Column(db.Integer, db.ForeignKey('policy.policy_id'), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    change_type = db.Column(db.Text, nullable=False)  # 'create', 'update', 'delete'
    field_name = db.Column(db.Text, nullable=True)  # Specific field changed (for updates)
    old_value = db.Column(db.Text, nullable=True)  # Previous value (for updates)
    new_value = db.Column(db.Text, nullable=True)  # New value (for updates/creates)
    change_reason = db.Column(db.Text, nullable=True)  # Optional reason for change
    ip_address = db.Column(db.Text, nullable=True)  # IP address of requester
    user_agent = db.Column(db.Text, nullable=True)  # Browser/client info
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    
    policy = db.relationship('Policy', backref='audit_logs')
    changed_by_user = db.relationship('User', foreign_keys=[changed_by], overlaps="policy_audit_logs")
    
    def __repr__(self):
        return f'<PolicyAuditLog {self.audit_id}: {self.change_type} by User {self.changed_by}>'
    
    @classmethod
    def log_policy_change(cls, policy_id, changed_by_id, change_type, field_name=None, 
                         old_value=None, new_value=None, change_reason=None, 
                         ip_address=None, user_agent=None):
        """Helper method to create audit log entries"""
        audit_log = cls(
            policy_id=policy_id,
            changed_by=changed_by_id,
            change_type=change_type,
            field_name=field_name,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            change_reason=change_reason,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.session.add(audit_log)
        return audit_log

class ShiftViolation(db.Model):
    """Model to track shift duration violations for visual alerts (Issue #30)"""
    __tablename__ = 'shift_violations'
    
    violation_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    shift_id = db.Column(db.Integer, db.ForeignKey('shift.shift_id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.term_id'), nullable=False)
    violation_type = db.Column(db.Text, nullable=False)  # 'too_short', 'too_long', 'break_too_short'
    current_duration = db.Column(db.Integer, nullable=False)  # Actual duration in minutes
    expected_min = db.Column(db.Integer, nullable=True)  # Expected minimum duration
    expected_max = db.Column(db.Integer, nullable=True)  # Expected maximum duration
    violation_message = db.Column(db.Text, nullable=False)  # Human-readable violation description
    severity = db.Column(db.Text, nullable=False, default='warning')  # 'warning', 'error', 'critical'
    is_resolved = db.Column(db.Boolean, nullable=False, default=False)  # Has this been fixed/overridden?
    override_applied = db.Column(db.Boolean, nullable=False, default=False)  # Manual override approved?
    override_justification = db.Column(db.Text, nullable=True)  # Reason for override
    override_by = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)  # Who approved override
    detected_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    resolved_at = db.Column(db.DateTime, nullable=True)  # When violation was fixed
    
    shift = db.relationship('Shift', backref='violations')
    term = db.relationship('Term', backref='shift_violations')
    override_by_user = db.relationship('User', foreign_keys=[override_by])
    
    def __repr__(self):
        return f'<ShiftViolation {self.violation_id}: {self.violation_type} for Shift {self.shift_id}>'
    
    @classmethod
    def detect_violations_for_shift(cls, shift):
        """
        Detect and create violation records for a shift (Issue #30)
        
        Args:
            shift (Shift): The shift to check for violations
            
        Returns:
            list: List of violations found
        """
        violations = []
        
        # Clear existing violations for this shift
        cls.query.filter_by(shift_id=shift.shift_id, is_resolved=False).delete()
        
        # Get policy for this shift's term
        policy = Policy.get_policy_with_defaults(shift.term_id)
        if not policy:
            return violations
        
        duration = shift.get_duration_minutes()
        
        # Check for too short
        if duration < policy.min_shift_length:
            violation = cls(
                shift_id=shift.shift_id,
                term_id=shift.term_id,
                violation_type='too_short',
                current_duration=duration,
                expected_min=policy.min_shift_length,
                expected_max=policy.max_shift_length,
                violation_message=f'Shift is {duration} minutes but minimum is {policy.min_shift_length} minutes',
                severity='error'
            )
            violations.append(violation)
        
        # Check for too long
        elif duration > policy.max_shift_length:
            violation = cls(
                shift_id=shift.shift_id,
                term_id=shift.term_id,
                violation_type='too_long',
                current_duration=duration,
                expected_min=policy.min_shift_length,
                expected_max=policy.max_shift_length,
                violation_message=f'Shift is {duration} minutes but maximum is {policy.max_shift_length} minutes',
                severity='warning'
            )
            violations.append(violation)
        
        # Add violations to database
        for violation in violations:
            db.session.add(violation)
        
        return violations
    
    @classmethod
    def get_violation_summary(cls, term_id=None):
        """Get summary of violations for dashboard display (Issue #30)"""
        query = cls.query.filter_by(is_resolved=False)
        if term_id:
            query = query.filter_by(term_id=term_id)
        
        violations = query.all()
        
        summary = {
            'total_violations': len(violations),
            'by_severity': {
                'critical': len([v for v in violations if v.severity == 'critical']),
                'error': len([v for v in violations if v.severity == 'error']),
                'warning': len([v for v in violations if v.severity == 'warning'])
            },
            'by_type': {
                'too_short': len([v for v in violations if v.violation_type == 'too_short']),
                'too_long': len([v for v in violations if v.violation_type == 'too_long']),
                'break_too_short': len([v for v in violations if v.violation_type == 'break_too_short'])
            }
        }
        
        return summary
    
    def get_quick_fix_suggestions(self):
        """Get quick-fix suggestions for this violation (Issue #30)"""
        suggestions = []
        
        if self.violation_type == 'too_short':
            # Suggest extending the shift
            needed_extension = self.expected_min - self.current_duration
            suggestions.append({
                'type': 'extend',
                'description': f'Extend shift by {needed_extension} minutes to meet minimum duration',
                'action': 'extend_shift',
                'parameters': {'extension_minutes': needed_extension}
            })
            
            # Suggest removing the shift
            suggestions.append({
                'type': 'remove',
                'description': 'Remove this shift if it cannot be extended',
                'action': 'remove_shift',
                'parameters': {}
            })
            
        elif self.violation_type == 'too_long':
            # Suggest splitting the shift
            max_duration = self.expected_max
            needed_split = self.current_duration - max_duration
            suggestions.append({
                'type': 'split',
                'description': f'Split shift into shorter segments (reduce by {needed_split} minutes)',
                'action': 'split_shift',
                'parameters': {'max_duration': max_duration}
            })
            
            # Suggest truncating the shift
            suggestions.append({
                'type': 'truncate',
                'description': f'Reduce shift length to {max_duration} minutes',
                'action': 'truncate_shift',
                'parameters': {'new_duration': max_duration}
            })
        
        return suggestions
    
    def apply_override(self, justification, user_id):
        """Apply manual override with justification (Issue #30)"""
        self.override_applied = True
        self.override_justification = justification
        self.override_by = user_id
        self.is_resolved = True
        self.resolved_at = db.func.current_timestamp()
        db.session.commit()


# Issue #32: Gap Detection and Management Models

class ShiftGap(db.Model):
    """Model to track gaps between shifts for students (Issue #32)"""
    __tablename__ = 'shift_gaps'
    
    gap_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.term_id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    
    # First shift information
    first_shift_id = db.Column(db.Integer, db.ForeignKey('shift.shift_id'), nullable=False)
    first_shift_end = db.Column(db.Time, nullable=False)
    
    # Second shift information  
    second_shift_id = db.Column(db.Integer, db.ForeignKey('shift.shift_id'), nullable=False)
    second_shift_start = db.Column(db.Time, nullable=False)
    
    # Gap details
    gap_duration_minutes = db.Column(db.Integer, nullable=False)
    gap_type = db.Column(db.Text, nullable=False)  # 'small_gap', 'fragmented', 'impractical'
    severity = db.Column(db.Text, nullable=False, default='warning')  # 'warning', 'error'
    
    # Resolution tracking
    is_resolved = db.Column(db.Boolean, nullable=False, default=False)
    resolution_method = db.Column(db.Text, nullable=True)  # 'merged', 'extended', 'manual_override'
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    
    # Detection metadata
    detected_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    auto_merge_attempted = db.Column(db.Boolean, nullable=False, default=False)
    merge_blocked_reason = db.Column(db.Text, nullable=True)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='shift_gaps')
    term = db.relationship('Term', backref='shift_gaps')
    first_shift = db.relationship('Shift', foreign_keys=[first_shift_id], backref='gaps_as_first')
    second_shift = db.relationship('Shift', foreign_keys=[second_shift_id], backref='gaps_as_second')
    resolved_by_user = db.relationship('User', foreign_keys=[resolved_by])
    
    def __repr__(self):
        return f'<ShiftGap {self.gap_id}: {self.gap_duration_minutes}min gap for User {self.user_id}>'
    
    @classmethod
    def detect_gaps_for_user_date(cls, user_id, date, term_id=None):
        """
        Detect gaps in shifts for a specific user on a specific date (Issue #32)
        
        Args:
            user_id: User to check gaps for
            date: Date to check
            term_id: Optional term filter
            
        Returns:
            list: List of detected gaps
        """
        from datetime import datetime, timedelta
        
        # Get all shifts for this user on this date, ordered by start time
        shifts_query = Shift.query.filter_by(user_id=user_id, date=date)
        if term_id:
            shifts_query = shifts_query.filter_by(term_id=term_id)
        
        shifts = shifts_query.order_by(Shift.start_time).all()
        
        if len(shifts) < 2:
            return []  # No gaps possible with less than 2 shifts
        
        gaps = []
        
        # Clear existing gaps for this user/date to avoid duplicates
        cls.query.filter_by(user_id=user_id, date=date).delete()
        
        # Check each consecutive pair of shifts
        for i in range(len(shifts) - 1):
            current_shift = shifts[i]
            next_shift = shifts[i + 1]
            
            # Calculate gap duration
            current_end = datetime.combine(date, current_shift.end_time)
            next_start = datetime.combine(date, next_shift.start_time)
            
            # Handle day boundary crossings
            if next_start < current_end:
                next_start += timedelta(days=1)
            
            gap_duration = (next_start - current_end).total_seconds() / 60
            
            # Only create gap records for gaps that exist
            if gap_duration > 0:
                # Get policy for gap thresholds
                policy = Policy.get_policy_with_defaults(current_shift.term_id)
                
                # Determine gap type and severity
                gap_type = 'normal_gap'
                severity = 'info'
                
                if gap_duration <= policy.max_gap_threshold:
                    if gap_duration >= policy.min_gap_threshold:
                        gap_type = 'small_gap'
                        severity = 'warning'
                    else:
                        gap_type = 'very_small_gap'
                        severity = 'error'
                
                # Create gap record for any problematic gap
                if gap_duration <= policy.max_gap_threshold:
                    gap = cls(
                        user_id=user_id,
                        term_id=current_shift.term_id,
                        date=date,
                        first_shift_id=current_shift.shift_id,
                        first_shift_end=current_shift.end_time,
                        second_shift_id=next_shift.shift_id,
                        second_shift_start=next_shift.start_time,
                        gap_duration_minutes=int(gap_duration),
                        gap_type=gap_type,
                        severity=severity
                    )
                    gaps.append(gap)
        
        # Add gaps to database
        for gap in gaps:
            db.session.add(gap)
        
        if gaps:
            db.session.commit()
        
        return gaps
    
    @classmethod
    def detect_all_gaps_for_term(cls, term_id):
        """Detect all gaps for all users in a term (Issue #32)"""
        from datetime import date, timedelta
        
        # Get all shifts for this term
        shifts = Shift.query.filter_by(term_id=term_id).all()
        
        # Group by user and date
        user_dates = {}
        for shift in shifts:
            key = (shift.user_id, shift.date)
            if key not in user_dates:
                user_dates[key] = []
            user_dates[key].append(shift)
        
        all_gaps = []
        
        # Check gaps for each user/date combination
        for (user_id, shift_date), user_shifts in user_dates.items():
            if len(user_shifts) >= 2:  # Only check if multiple shifts exist
                gaps = cls.detect_gaps_for_user_date(user_id, shift_date, term_id)
                all_gaps.extend(gaps)
        
        return all_gaps
    
    def get_merge_suggestion(self):
        """Get suggestion for merging this gap (Issue #32)"""
        policy = Policy.get_policy_with_defaults(self.term_id)
        
        if not policy.allow_gap_merging:
            return None
        
        # Calculate what the merged shift would look like
        merged_start = self.first_shift.start_time
        merged_end = self.second_shift.end_time
        
        # Calculate merged duration
        from datetime import datetime, timedelta
        start_dt = datetime.combine(self.date, merged_start)
        end_dt = datetime.combine(self.date, merged_end)
        
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
        
        merged_duration = (end_dt - start_dt).total_seconds() / 60
        
        # Check if merged shift would violate duration constraints
        is_valid, error = policy.validate_shift_times(merged_start, merged_end)
        
        suggestion = {
            'can_merge': is_valid,
            'merged_start': merged_start.strftime('%H:%M'),
            'merged_end': merged_end.strftime('%H:%M'),
            'merged_duration': int(merged_duration),
            'gap_eliminated': self.gap_duration_minutes,
            'error_message': error if not is_valid else None
        }
        
        if is_valid:
            suggestion['benefits'] = [
                f"Eliminates {self.gap_duration_minutes}-minute gap",
                f"Creates {int(merged_duration)}-minute continuous shift",
                "Improves scheduling efficiency"
            ]
        else:
            suggestion['alternatives'] = [
                "Extend first shift slightly",
                "Start second shift slightly earlier", 
                "Accept gap with manual override"
            ]
        
        return suggestion
    
    def attempt_auto_merge(self, user_id):
        """Attempt to automatically merge shifts to eliminate this gap (Issue #32)"""
        merge_suggestion = self.get_merge_suggestion()
        
        if not merge_suggestion or not merge_suggestion['can_merge']:
            self.auto_merge_attempted = True
            self.merge_blocked_reason = merge_suggestion.get('error_message', 'Merge not possible')
            db.session.commit()
            return False
        
        try:
            # Update first shift to extend to second shift's end time
            self.first_shift.end_time = self.second_shift.end_time
            self.first_shift.was_manually_adjusted = True
            
            # Delete the second shift
            db.session.delete(self.second_shift)
            
            # Mark gap as resolved
            self.is_resolved = True
            self.resolution_method = 'merged'
            self.resolved_by = user_id
            self.resolved_at = db.func.current_timestamp()
            self.auto_merge_attempted = True
            
            db.session.commit()
            return True
            
        except Exception as e:
            db.session.rollback()
            self.auto_merge_attempted = True
            self.merge_blocked_reason = f"Merge failed: {str(e)}"
            db.session.commit()
            return False
    
    @classmethod
    def get_gap_summary(cls, term_id=None, user_id=None):
        """Get summary of gaps for dashboard display (Issue #32)"""
        query = cls.query.filter_by(is_resolved=False)
        
        if term_id:
            query = query.filter_by(term_id=term_id)
        if user_id:
            query = query.filter_by(user_id=user_id)
        
        gaps = query.all()
        
        summary = {
            'total_gaps': len(gaps),
            'by_severity': {
                'error': len([g for g in gaps if g.severity == 'error']),
                'warning': len([g for g in gaps if g.severity == 'warning']),
                'info': len([g for g in gaps if g.severity == 'info'])
            },
            'by_type': {
                'very_small_gap': len([g for g in gaps if g.gap_type == 'very_small_gap']),
                'small_gap': len([g for g in gaps if g.gap_type == 'small_gap']),
                'normal_gap': len([g for g in gaps if g.gap_type == 'normal_gap'])
            },
            'avg_gap_duration': sum(g.gap_duration_minutes for g in gaps) / len(gaps) if gaps else 0,
            'mergeable_gaps': len([g for g in gaps if g.get_merge_suggestion() and g.get_merge_suggestion()['can_merge']])
        }
        
        return summary


# Issue #35: Minimum break time between shifts - Transition Time Violation Model

class TransitionTimeViolation(db.Model):
    """Model to track violations of minimum transition time between consecutive shifts (Issue #35)"""
    __tablename__ = 'transition_time_violations'
    
    violation_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.term_id'), nullable=False)
    
    # First shift information
    first_shift_id = db.Column(db.Integer, db.ForeignKey('shift.shift_id'), nullable=False)
    first_shift_date = db.Column(db.Date, nullable=False)
    first_shift_end = db.Column(db.Time, nullable=False)
    
    # Second shift information  
    second_shift_id = db.Column(db.Integer, db.ForeignKey('shift.shift_id'), nullable=False)
    second_shift_date = db.Column(db.Date, nullable=False)
    second_shift_start = db.Column(db.Time, nullable=False)
    
    # Violation details
    actual_transition_minutes = db.Column(db.Integer, nullable=False)  # Actual time between shifts
    required_transition_minutes = db.Column(db.Integer, nullable=False)  # Required minimum time
    severity = db.Column(db.String(20), nullable=False)  # 'critical', 'warning', 'minor'
    
    # Status tracking
    detected_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    resolution_method = db.Column(db.String(100), nullable=True)  # 'shift_moved', 'break_extended', 'manual_override'
    notes = db.Column(db.Text, nullable=True)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='transition_violations')
    term = db.relationship('Term', backref='transition_violations')
    first_shift = db.relationship('Shift', foreign_keys=[first_shift_id], backref='transition_violations_as_first')
    second_shift = db.relationship('Shift', foreign_keys=[second_shift_id], backref='transition_violations_as_second')
    resolved_by_user = db.relationship('User', foreign_keys=[resolved_by])
    
    def __repr__(self):
        return f'<TransitionTimeViolation {self.violation_id}: {self.actual_transition_minutes}min transition for User {self.user_id}>'
    
    @classmethod
    def detect_violations_for_user_date_range(cls, user_id, start_date, end_date, term_id):
        """
        Detect transition time violations for a specific user in a date range (Issue #35)
        
        Args:
            user_id: User to check violations for
            start_date: Start date for analysis
            end_date: End date for analysis  
            term_id: Term to get policy from
            
        Returns:
            list: List of detected violations
        """
        from models import Shift, Policy
        
        # Get policy for transition time requirements
        policy = Policy.get_policy_for_term(term_id)
        if not policy:
            return []
        
        # Get all shifts for the user in the date range, ordered by date and start time
        shifts = Shift.query.filter(
            Shift.user_id == user_id,
            Shift.date >= start_date,
            Shift.date <= end_date
        ).order_by(Shift.date, Shift.start_time).all()
        
        violations = []
        
        for i in range(len(shifts) - 1):
            current_shift = shifts[i]
            next_shift = shifts[i + 1]
            
            # Only check transitions on the same day or consecutive days
            day_diff = (next_shift.date - current_shift.date).days
            if day_diff > 1:
                continue
                
            # Validate transition time
            is_valid, transition_minutes, error = policy.validate_transition_time(
                current_shift.end_time,
                next_shift.start_time,
                current_shift.date
            )
            
            if not is_valid:
                # Determine severity
                shortage = policy.min_transition_time - transition_minutes
                if shortage >= 15:  # More than 15 minutes short
                    severity = 'critical'
                elif shortage >= 5:  # 5-14 minutes short
                    severity = 'warning' 
                else:  # Less than 5 minutes short
                    severity = 'minor'
                
                violation = {
                    'user_id': user_id,
                    'term_id': term_id,
                    'first_shift_id': current_shift.shift_id,
                    'first_shift_date': current_shift.date,
                    'first_shift_end': current_shift.end_time,
                    'second_shift_id': next_shift.shift_id,
                    'second_shift_date': next_shift.date,
                    'second_shift_start': next_shift.start_time,
                    'actual_transition_minutes': transition_minutes,
                    'required_transition_minutes': policy.min_transition_time,
                    'severity': severity,
                    'error_message': error
                }
                violations.append(violation)
        
        return violations
    
    @classmethod
    def detect_all_violations_for_term(cls, term_id):
        """
        Detect all transition time violations for all users in a term (Issue #35)
        
        Args:
            term_id: Term to analyze
            
        Returns:
            dict: Summary of violations by severity and user
        """
        from models import User, Shift
        from datetime import datetime, timedelta
        
        # Get all users with shifts in this term
        users_with_shifts = db.session.query(Shift.user_id).filter(
            Shift.term_id == term_id
        ).distinct().all()
        
        all_violations = []
        summary = {
            'total_violations': 0,
            'critical_violations': 0,
            'warning_violations': 0,
            'minor_violations': 0,
            'users_affected': 0,
            'violations_by_user': {}
        }
        
        for (user_id,) in users_with_shifts:
            # Get date range for this user's shifts
            user_shifts = Shift.query.filter(
                Shift.user_id == user_id,
                Shift.term_id == term_id
            ).order_by(Shift.date).all()
            
            if len(user_shifts) < 2:  # Need at least 2 shifts to have transitions
                continue
                
            start_date = user_shifts[0].date
            end_date = user_shifts[-1].date
            
            violations = cls.detect_violations_for_user_date_range(
                user_id, start_date, end_date, term_id
            )
            
            if violations:
                all_violations.extend(violations)
                summary['users_affected'] += 1
                summary['violations_by_user'][user_id] = len(violations)
                
                for violation in violations:
                    if violation['severity'] == 'critical':
                        summary['critical_violations'] += 1
                    elif violation['severity'] == 'warning':
                        summary['warning_violations'] += 1
                    else:
                        summary['minor_violations'] += 1
        
        summary['total_violations'] = len(all_violations)
        
        return {
            'violations': all_violations,
            'summary': summary
        }


# Issue #31: Validation Summary Report Model

class ValidationReport(db.Model):
    """Model for tracking validation summary reports (Issue #31)"""
    __tablename__ = 'validation_reports'
    
    report_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.term_id'), nullable=False)
    report_type = db.Column(db.String(50), nullable=False, default='duration_violations')  # Type of validation report
    generated_by = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    generated_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    
    # Report metadata
    total_shifts_analyzed = db.Column(db.Integer, nullable=False, default=0)
    total_violations_found = db.Column(db.Integer, nullable=False, default=0)
    violations_by_severity = db.Column(db.JSON, nullable=True)  # {'critical': 0, 'error': 5, 'warning': 2}
    violations_by_type = db.Column(db.JSON, nullable=True)     # {'too_short': 3, 'too_long': 4}
    
    # Export options
    pdf_generated = db.Column(db.Boolean, nullable=False, default=False)
    csv_generated = db.Column(db.Boolean, nullable=False, default=False)
    
    # Report summary
    report_summary = db.Column(db.Text, nullable=True)  # Brief text summary
    report_status = db.Column(db.String(20), nullable=False, default='completed')  # completed, failed, in_progress
    
    # Relationships
    term = db.relationship('Term', backref='validation_reports')
    generated_by_user = db.relationship('User', backref='generated_validation_reports')
    
    def __repr__(self):
        return f'<ValidationReport {self.report_id} for Term {self.term_id}>'
    
    @classmethod
    def generate_validation_report(cls, term_id, user_id, include_resolved=False):
        """
        Generate a comprehensive validation report for a term (Issue #31)
        
        Args:
            term_id: Term to generate report for
            user_id: User generating the report
            include_resolved: Whether to include resolved violations
            
        Returns:
            ValidationReport instance with generated data
        """
        from datetime import datetime
        
        # Get all violations for this term
        violations_query = ShiftViolation.query.filter_by(term_id=term_id)
        
        if not include_resolved:
            violations_query = violations_query.filter_by(is_resolved=False)
        
        violations = violations_query.all()
        
        # Get all shifts for this term to calculate total analyzed
        total_shifts = Shift.query.filter_by(term_id=term_id).count()
        
        # Calculate statistics
        total_violations = len(violations)
        violations_by_severity = {}
        violations_by_type = {}
        
        for violation in violations:
            # Count by severity
            severity = violation.severity
            violations_by_severity[severity] = violations_by_severity.get(severity, 0) + 1
            
            # Count by type
            vtype = violation.violation_type
            violations_by_type[vtype] = violations_by_type.get(vtype, 0) + 1
        
        # Generate summary text
        if total_violations == 0:
            summary = f"No duration violations found across {total_shifts} shifts analyzed."
        else:
            summary = f"Found {total_violations} duration violations across {total_shifts} shifts. "
            if violations_by_severity.get('critical', 0) > 0:
                summary += f"CRITICAL: {violations_by_severity['critical']} violations require immediate attention. "
            if violations_by_severity.get('error', 0) > 0:
                summary += f"ERRORS: {violations_by_severity['error']} violations need resolution. "
            if violations_by_severity.get('warning', 0) > 0:
                summary += f"WARNINGS: {violations_by_severity['warning']} minor issues detected."
        
        # Create report record
        report = cls(
            term_id=term_id,
            generated_by=user_id,
            total_shifts_analyzed=total_shifts,
            total_violations_found=total_violations,
            violations_by_severity=violations_by_severity,
            violations_by_type=violations_by_type,
            report_summary=summary,
            report_status='completed'
        )
        
        db.session.add(report)
        db.session.commit()
        
        return report
    
    def get_detailed_violations(self, group_by_type=True):
        """
        Get detailed violation data for this report (Issue #31)
        
        Args:
            group_by_type: Whether to group violations by type
            
        Returns:
            Dictionary with violation details, optionally grouped
        """
        violations_query = db.session.query(ShiftViolation, Shift, User).join(
            Shift, ShiftViolation.shift_id == Shift.shift_id
        ).join(
            User, Shift.user_id == User.user_id
        ).filter(ShiftViolation.term_id == self.term_id)
        
        violations_data = []
        for violation, shift, user in violations_query.all():
            violation_info = {
                'violation_id': violation.violation_id,
                'violation_type': violation.violation_type,
                'severity': violation.severity,
                'message': violation.violation_message,
                'shift_id': shift.shift_id,
                'user_name': user.name,
                'user_id': user.user_id,
                'date': shift.date.strftime('%Y-%m-%d'),
                'start_time': shift.start_time.strftime('%H:%M'),
                'end_time': shift.end_time.strftime('%H:%M'),
                'current_duration': violation.current_duration,
                'expected_min': violation.expected_min,
                'expected_max': violation.expected_max,
                'is_resolved': violation.is_resolved,
                'detected_at': violation.detected_at.strftime('%Y-%m-%d %H:%M:%S'),
                'ui_link': f"/constraints/violation-alerts?shift_id={shift.shift_id}"
            }
            violations_data.append(violation_info)
        
        if group_by_type:
            grouped = {}
            for violation in violations_data:
                vtype = violation['violation_type']
                if vtype not in grouped:
                    grouped[vtype] = []
                grouped[vtype].append(violation)
            return grouped
        
        return violations_data
    
    def generate_pdf_export(self):
        """Generate PDF export of validation report (Issue #31)"""
        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib import colors
            import io
            import os
            
            # Create PDF buffer
            buffer = io.BytesIO()
            
            # Create PDF document
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                spaceAfter=30,
                textColor=colors.darkblue
            )
            
            story.append(Paragraph("Shift Duration Validation Report", title_style))
            story.append(Spacer(1, 12))
            
            # Report metadata
            metadata = [
                ['Report ID:', str(self.report_id)],
                ['Generated:', self.generated_at.strftime('%Y-%m-%d %H:%M:%S')],
                ['Generated by:', self.generated_by_user.name],
                ['Term:', self.term.name if self.term else 'Unknown'],
                ['Total Shifts Analyzed:', str(self.total_shifts_analyzed)],
                ['Total Violations Found:', str(self.total_violations_found)]
            ]
            
            meta_table = Table(metadata, colWidths=[2*inch, 3*inch])
            meta_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            
            story.append(meta_table)
            story.append(Spacer(1, 20))
            
            # Summary
            story.append(Paragraph("Executive Summary", styles['Heading2']))
            story.append(Paragraph(self.report_summary, styles['Normal']))
            story.append(Spacer(1, 20))
            
            # Violations by severity
            if self.violations_by_severity:
                story.append(Paragraph("Violations by Severity", styles['Heading2']))
                severity_data = [['Severity', 'Count']]
                for severity, count in self.violations_by_severity.items():
                    severity_data.append([severity.title(), str(count)])
                
                severity_table = Table(severity_data)
                severity_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                
                story.append(severity_table)
                story.append(Spacer(1, 20))
            
            # Detailed violations
            violations = self.get_detailed_violations(group_by_type=True)
            
            if violations:
                story.append(Paragraph("Detailed Violations", styles['Heading2']))
                
                for violation_type, violation_list in violations.items():
                    story.append(Paragraph(f"{violation_type.replace('_', ' ').title()} ({len(violation_list)} violations)", styles['Heading3']))
                    
                    # Create table for this violation type
                    headers = ['User', 'Date', 'Time', 'Duration (min)', 'Expected Range', 'Severity']
                    violation_data = [headers]
                    
                    for violation in violation_list[:10]:  # Limit to first 10 per type
                        violation_data.append([
                            violation['user_name'],
                            violation['date'],
                            f"{violation['start_time']}-{violation['end_time']}",
                            str(violation['current_duration']),
                            f"{violation['expected_min']}-{violation['expected_max']}",
                            violation['severity']
                        ])
                    
                    v_table = Table(violation_data, colWidths=[1.2*inch, 1*inch, 1.2*inch, 0.8*inch, 1*inch, 0.8*inch])
                    v_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ]))
                    
                    story.append(v_table)
                    
                    if len(violation_list) > 10:
                        story.append(Paragraph(f"... and {len(violation_list) - 10} more violations of this type", styles['Italic']))
                    
                    story.append(Spacer(1, 12))
            
            # Build PDF
            doc.build(story)
            
            # Save PDF file
            pdf_content = buffer.getvalue()
            buffer.close()
            
            # Save to file system
            os.makedirs('reports', exist_ok=True)
            pdf_filename = f'reports/validation_report_{self.report_id}_{self.generated_at.strftime("%Y%m%d_%H%M")}.pdf'
            
            with open(pdf_filename, 'wb') as f:
                f.write(pdf_content)
            
            # Update report status
            self.pdf_generated = True
            db.session.commit()
            
            return pdf_filename, pdf_content
            
        except ImportError:
            raise Exception("ReportLab library not installed. Run: pip install reportlab")
        except Exception as e:
            raise Exception(f"PDF generation failed: {str(e)}")
    
    def generate_csv_export(self):
        """Generate CSV export of validation report (Issue #31)"""
        import csv
        import io
        import os
        
        try:
            # Create CSV buffer
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write headers
            headers = [
                'Violation ID', 'Violation Type', 'Severity', 'Message',
                'User Name', 'Date', 'Start Time', 'End Time',
                'Current Duration (min)', 'Expected Min (min)', 'Expected Max (min)',
                'Is Resolved', 'Detected At', 'Shift ID'
            ]
            writer.writerow(headers)
            
            # Get violation details
            violations = self.get_detailed_violations(group_by_type=False)
            
            # Write data rows
            for violation in violations:
                writer.writerow([
                    violation['violation_id'],
                    violation['violation_type'],
                    violation['severity'],
                    violation['message'],
                    violation['user_name'],
                    violation['date'],
                    violation['start_time'],
                    violation['end_time'],
                    violation['current_duration'],
                    violation['expected_min'],
                    violation['expected_max'],
                    violation['is_resolved'],
                    violation['detected_at'],
                    violation['shift_id']
                ])
            
            # Get CSV content
            csv_content = output.getvalue()
            output.close()
            
            # Save to file system
            os.makedirs('reports', exist_ok=True)
            csv_filename = f'reports/validation_report_{self.report_id}_{self.generated_at.strftime("%Y%m%d_%H%M")}.csv'
            
            with open(csv_filename, 'w', newline='') as f:
                f.write(csv_content)
            
            # Update report status
            self.csv_generated = True
            db.session.commit()
            
            return csv_filename, csv_content
            
        except Exception as e:
            raise Exception(f"CSV generation failed: {str(e)}")
    
    @classmethod
    def get_recent_reports(cls, limit=10):
        """Get recent validation reports for dashboard (Issue #31)"""
        return cls.query.order_by(cls.generated_at.desc()).limit(limit).all()