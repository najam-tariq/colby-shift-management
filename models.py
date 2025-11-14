from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import uuid
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # Use bounded-length strings for MySQL-compatible unique indexes
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    role = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    password_hash = db.Column(db.Text, nullable=False)
    calendar_token = db.Column(db.String(255), nullable=True, unique=True)  # UUID for secure calendar feed access
    
    availability = db.relationship('Availability', back_populates='user', cascade='all, delete')
    shifts = db.relationship('Shift', back_populates='user', cascade='all, delete')
    policies_updated = db.relationship('Policy', back_populates='updated_by_user', cascade='all, delete')
    
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
    
    # Consolidated constraint and validation data stored as JSON
    undesirable_windows = db.Column(db.JSON, nullable=True)  # List of undesirable time windows
    shift_violations = db.Column(db.JSON, nullable=True)     # Current violations data
    shift_gaps = db.Column(db.JSON, nullable=True)           # Gap analysis data
    transition_violations = db.Column(db.JSON, nullable=True) # Transition time violations
    undesirable_tracking = db.Column(db.JSON, nullable=True)  # Undesirable shift tracking
    volunteer_preferences = db.Column(db.JSON, nullable=True) # Student volunteer preferences
    validation_reports = db.Column(db.JSON, nullable=True)    # Validation report history
    rejected_shifts = db.Column(db.JSON, nullable=True)       # Automatically rejected shifts log
    split_shifts = db.Column(db.JSON, nullable=True)          # Automatically split shifts log
    audit_log = db.Column(db.JSON, nullable=True)             # Policy change audit log
    
    term = db.relationship('Term', back_populates='policies')
    updated_by_user = db.relationship('User', back_populates='policies_updated')
    
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
    
    # ====== CONSOLIDATED CONSTRAINT AND VALIDATION METHODS ======
    
    def add_undesirable_window(self, name, start_time, end_time, day_of_week=None, weight=1.0, window_type="custom"):
        """Add an undesirable time window to this policy"""
        if not self.undesirable_windows:
            self.undesirable_windows = []
        
        window_data = {
            'window_id': len(self.undesirable_windows) + 1,
            'name': name,
            'day_of_week': day_of_week,
            'start_time': start_time.strftime('%H:%M') if hasattr(start_time, 'strftime') else start_time,
            'end_time': end_time.strftime('%H:%M') if hasattr(end_time, 'strftime') else end_time,
            'weight': weight,
            'window_type': window_type
        }
        self.undesirable_windows.append(window_data)
        db.session.commit()
    
    def get_undesirable_windows(self):
        """Get all undesirable time windows for this policy"""
        return self.undesirable_windows or []
    
    def remove_undesirable_window(self, window_id):
        """Remove an undesirable time window by ID"""
        if self.undesirable_windows:
            self.undesirable_windows = [w for w in self.undesirable_windows if w.get('window_id') != window_id]
            db.session.commit()
    
    def detect_violations_for_shift(self, shift):
        """Detect and store violations for a specific shift"""
        violations = []
        
        if not self.shift_violations:
            self.shift_violations = []
        
        # Clear existing violations for this shift
        self.shift_violations = [v for v in self.shift_violations if v.get('shift_id') != shift.shift_id]
        
        duration = shift.get_duration_minutes()
        
        # Check for too short
        if duration < self.min_shift_length:
            violation = {
                'violation_id': len(self.shift_violations) + 1,
                'shift_id': shift.shift_id,
                'term_id': shift.term_id,
                'violation_type': 'too_short',
                'current_duration': duration,
                'expected_min': self.min_shift_length,
                'expected_max': self.max_shift_length,
                'violation_message': f'Shift is {duration} minutes but minimum is {self.min_shift_length} minutes',
                'severity': 'error',
                'is_resolved': False,
                'detected_at': datetime.now().isoformat()
            }
            violations.append(violation)
            self.shift_violations.append(violation)
        
        # Check for too long
        elif duration > self.max_shift_length:
            violation = {
                'violation_id': len(self.shift_violations) + 1,
                'shift_id': shift.shift_id,
                'term_id': shift.term_id,
                'violation_type': 'too_long',
                'current_duration': duration,
                'expected_min': self.min_shift_length,
                'expected_max': self.max_shift_length,
                'violation_message': f'Shift is {duration} minutes but maximum is {self.max_shift_length} minutes',
                'severity': 'warning',
                'is_resolved': False,
                'detected_at': datetime.now().isoformat()
            }
            violations.append(violation)
            self.shift_violations.append(violation)
        
        if violations:
            db.session.commit()
        
        return violations
    
    def get_violation_summary(self, include_resolved=False):
        """Get summary of violations for this policy"""
        violations = self.shift_violations or []
        
        if not include_resolved:
            violations = [v for v in violations if not v.get('is_resolved', False)]
        
        summary = {
            'total_violations': len(violations),
            'by_severity': {
                'critical': len([v for v in violations if v.get('severity') == 'critical']),
                'error': len([v for v in violations if v.get('severity') == 'error']),
                'warning': len([v for v in violations if v.get('severity') == 'warning'])
            },
            'by_type': {
                'too_short': len([v for v in violations if v.get('violation_type') == 'too_short']),
                'too_long': len([v for v in violations if v.get('violation_type') == 'too_long'])
            }
        }
        
        return summary
    
    def detect_gaps_for_user_date(self, user_id, date, shifts_list):
        """Detect and store gaps in shifts for a specific user on a specific date"""
        from datetime import datetime, timedelta
        
        if not self.shift_gaps:
            self.shift_gaps = []
        
        # Clear existing gaps for this user/date
        self.shift_gaps = [g for g in self.shift_gaps if not (g.get('user_id') == user_id and g.get('date') == date.isoformat())]
        
        if len(shifts_list) < 2:
            return []
        
        gaps = []
        sorted_shifts = sorted(shifts_list, key=lambda x: x.start_time)
        
        for i in range(len(sorted_shifts) - 1):
            current_shift = sorted_shifts[i]
            next_shift = sorted_shifts[i + 1]
            
            current_end = datetime.combine(date, current_shift.end_time)
            next_start = datetime.combine(date, next_shift.start_time)
            
            if next_start < current_end:
                next_start += timedelta(days=1)
            
            gap_duration = (next_start - current_end).total_seconds() / 60
            
            if 0 < gap_duration <= self.max_gap_threshold:
                gap_type = 'small_gap' if gap_duration >= self.min_gap_threshold else 'very_small_gap'
                severity = 'warning' if gap_duration >= self.min_gap_threshold else 'error'
                
                gap = {
                    'gap_id': len(self.shift_gaps) + 1,
                    'user_id': user_id,
                    'term_id': self.term_id,
                    'date': date.isoformat(),
                    'first_shift_id': current_shift.shift_id,
                    'first_shift_end': current_shift.end_time.strftime('%H:%M'),
                    'second_shift_id': next_shift.shift_id,
                    'second_shift_start': next_shift.start_time.strftime('%H:%M'),
                    'gap_duration_minutes': int(gap_duration),
                    'gap_type': gap_type,
                    'severity': severity,
                    'is_resolved': False,
                    'detected_at': datetime.now().isoformat()
                }
                gaps.append(gap)
                self.shift_gaps.append(gap)
        
        if gaps:
            db.session.commit()
        
        return gaps
    
    def get_gap_summary(self, user_id=None):
        """Get summary of gaps for this policy"""
        gaps = self.shift_gaps or []
        
        if user_id:
            gaps = [g for g in gaps if g.get('user_id') == user_id]
        
        unresolved_gaps = [g for g in gaps if not g.get('is_resolved', False)]
        
        summary = {
            'total_gaps': len(unresolved_gaps),
            'by_severity': {
                'error': len([g for g in unresolved_gaps if g.get('severity') == 'error']),
                'warning': len([g for g in unresolved_gaps if g.get('severity') == 'warning'])
            },
            'avg_gap_duration': sum(g.get('gap_duration_minutes', 0) for g in unresolved_gaps) / len(unresolved_gaps) if unresolved_gaps else 0,
            'mergeable_gaps': len([g for g in unresolved_gaps if self._can_merge_gap(g)])
        }
        
        return summary
    
    def _can_merge_gap(self, gap):
        """Check if a gap can be merged"""
        return self.allow_gap_merging and gap.get('gap_duration_minutes', 0) <= self.max_gap_threshold
    
    def validate_transition_times_for_user(self, user_id, shifts_list):
        """Validate transition times for a user's shifts and store violations"""
        if not self.transition_violations:
            self.transition_violations = []
        
        # Clear existing violations for this user
        self.transition_violations = [v for v in self.transition_violations if v.get('user_id') != user_id]
        
        violations = []
        sorted_shifts = sorted(shifts_list, key=lambda x: (x.date, x.start_time))
        
        for i in range(len(sorted_shifts) - 1):
            current_shift = sorted_shifts[i]
            next_shift = sorted_shifts[i + 1]
            
            day_diff = (next_shift.date - current_shift.date).days
            if day_diff > 1:
                continue
                
            is_valid, transition_minutes, error = self.validate_transition_time(
                current_shift.end_time,
                next_shift.start_time,
                current_shift.date
            )
            
            if not is_valid:
                shortage = self.min_transition_time - transition_minutes
                severity = 'critical' if shortage >= 15 else 'warning' if shortage >= 5 else 'minor'
                
                violation = {
                    'violation_id': len(self.transition_violations) + 1,
                    'user_id': user_id,
                    'term_id': self.term_id,
                    'first_shift_id': current_shift.shift_id,
                    'first_shift_date': current_shift.date.isoformat(),
                    'first_shift_end': current_shift.end_time.strftime('%H:%M'),
                    'second_shift_id': next_shift.shift_id,
                    'second_shift_date': next_shift.date.isoformat(),
                    'second_shift_start': next_shift.start_time.strftime('%H:%M'),
                    'actual_transition_minutes': transition_minutes,
                    'required_transition_minutes': self.min_transition_time,
                    'severity': severity,
                    'detected_at': datetime.now().isoformat()
                }
                violations.append(violation)
                self.transition_violations.append(violation)
        
        if violations:
            db.session.commit()
        
        return violations
    
    def track_undesirable_shift(self, user_id, shift_id, undesirable_type, weight=1.0):
        """Track when a student gets an undesirable shift"""
        if not self.undesirable_tracking:
            self.undesirable_tracking = []
        
        tracking_entry = {
            'tracking_id': len(self.undesirable_tracking) + 1,
            'user_id': user_id,
            'term_id': self.term_id,
            'shift_id': shift_id,
            'undesirable_type': undesirable_type,
            'undesirable_weight': weight,
            'assigned_date': datetime.now().isoformat(),
            'manual_override': False
        }
        
        self.undesirable_tracking.append(tracking_entry)
        db.session.commit()
    
    def add_volunteer_preference(self, user_id, preference_type, notes=None):
        """Add a volunteer preference for a student"""
        if not self.volunteer_preferences:
            self.volunteer_preferences = []
        
        preference = {
            'preference_id': len(self.volunteer_preferences) + 1,
            'user_id': user_id,
            'term_id': self.term_id,
            'preference_type': preference_type,  # 'early', 'late', 'both'
            'is_active': True,
            'created_date': datetime.now().isoformat(),
            'notes': notes
        }
        
        self.volunteer_preferences.append(preference)
        db.session.commit()
    
    def log_rejected_shift(self, user_id, start_time, end_time, date, reason, duration_minutes):
        """Log a rejected shift for debugging"""
        if not self.rejected_shifts:
            self.rejected_shifts = []
        
        rejected_shift = {
            'rejection_id': len(self.rejected_shifts) + 1,
            'term_id': self.term_id,
            'user_id': user_id,
            'proposed_start_time': start_time.strftime('%H:%M') if hasattr(start_time, 'strftime') else start_time,
            'proposed_end_time': end_time.strftime('%H:%M') if hasattr(end_time, 'strftime') else end_time,
            'proposed_date': date.isoformat() if hasattr(date, 'isoformat') else str(date),
            'duration_minutes': duration_minutes,
            'rejection_reason': reason,
            'rejection_type': 'duration' if 'duration' in reason.lower() else 'policy',
            'created_at': datetime.now().isoformat()
        }
        
        self.rejected_shifts.append(rejected_shift)
        db.session.commit()
    
    def log_split_shift(self, user_id, original_start, original_end, date, split_count, break_minutes, reason):
        """Log a split shift for tracking"""
        if not self.split_shifts:
            self.split_shifts = []
        
        duration = ((datetime.combine(datetime.today(), original_end) - 
                    datetime.combine(datetime.today(), original_start)).total_seconds() / 60)
        
        split_shift = {
            'split_id': len(self.split_shifts) + 1,
            'term_id': self.term_id,
            'user_id': user_id,
            'original_start_time': original_start.strftime('%H:%M') if hasattr(original_start, 'strftime') else original_start,
            'original_end_time': original_end.strftime('%H:%M') if hasattr(original_end, 'strftime') else original_end,
            'original_duration_minutes': int(duration),
            'proposed_date': date.isoformat() if hasattr(date, 'isoformat') else str(date),
            'split_count': split_count,
            'break_minutes': break_minutes,
            'split_reason': reason,
            'created_at': datetime.now().isoformat()
        }
        
        self.split_shifts.append(split_shift)
        db.session.commit()
    
    def log_policy_change(self, user_id, change_type, field_name=None, old_value=None, new_value=None, reason=None):
        """Log a policy change for audit purposes"""
        if not self.audit_log:
            self.audit_log = []
        
        audit_entry = {
            'audit_id': len(self.audit_log) + 1,
            'policy_id': self.policy_id,
            'changed_by': user_id,
            'change_type': change_type,  # 'create', 'update', 'delete'
            'field_name': field_name,
            'old_value': str(old_value) if old_value is not None else None,
            'new_value': str(new_value) if new_value is not None else None,
            'change_reason': reason,
            'created_at': datetime.now().isoformat()
        }
        
        self.audit_log.append(audit_entry)
        db.session.commit()
    
    def generate_validation_report(self, user_id):
        """Generate a validation report and store it in the policy"""
        if not self.validation_reports:
            self.validation_reports = []
        
        violations = [v for v in (self.shift_violations or []) if not v.get('is_resolved', False)]
        gaps = [g for g in (self.shift_gaps or []) if not g.get('is_resolved', False)]
        transition_violations = [tv for tv in (self.transition_violations or [])]
        
        total_violations = len(violations) + len(gaps) + len(transition_violations)
        
        report = {
            'report_id': len(self.validation_reports) + 1,
            'term_id': self.term_id,
            'generated_by': user_id,
            'generated_at': datetime.now().isoformat(),
            'total_violations_found': total_violations,
            'shift_violations': len(violations),
            'gap_issues': len(gaps),
            'transition_violations': len(transition_violations),
            'report_summary': f"Found {total_violations} total issues: {len(violations)} shift violations, {len(gaps)} gap issues, {len(transition_violations)} transition violations",
            'report_status': 'completed'
        }
        
        self.validation_reports.append(report)
        db.session.commit()
        
        return report
    
    @classmethod
    def get_consolidated_violation_summary(cls, term_id=None):
        """Get violation summary across all policies (for compatibility with existing code)"""
        query = cls.query
        if term_id:
            query = query.filter_by(term_id=term_id)
        
        policies = query.all()
        
        total_summary = {
            'total_violations': 0,
            'by_severity': {'critical': 0, 'error': 0, 'warning': 0},
            'by_type': {'too_short': 0, 'too_long': 0}
        }
        
        for policy in policies:
            summary = policy.get_violation_summary()
            total_summary['total_violations'] += summary['total_violations']
            for severity in ['critical', 'error', 'warning']:
                total_summary['by_severity'][severity] += summary['by_severity'][severity]
            for vtype in ['too_short', 'too_long']:
                total_summary['by_type'][vtype] += summary['by_type'][vtype]
        
        return total_summary


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


# ====== COMPATIBILITY WRAPPERS FOR LEGACY CODE ======

class ShiftViolation:
    """Compatibility wrapper - uses Policy.shift_violations JSON field"""
    
    @classmethod
    def detect_violations_for_shift(cls, shift):
        policy = Policy.get_policy_for_term(shift.term_id)
        if policy:
            return policy.detect_violations_for_shift(shift)
        return []
    
    @classmethod
    def get_violation_summary(cls, term_id=None):
        return Policy.get_consolidated_violation_summary(term_id)

class ShiftGap:
    """Compatibility wrapper - uses Policy.shift_gaps JSON field"""
    
    @classmethod
    def detect_gaps_for_user_date(cls, user_id, date, term_id):
        policy = Policy.get_policy_for_term(term_id)
        if policy:
            # Get shifts for this user on this date
            shifts = Shift.query.filter_by(user_id=user_id, date=date, term_id=term_id).all()
            return policy.detect_gaps_for_user_date(user_id, date, shifts)
        return []
    
    @classmethod
    def detect_all_gaps_for_term(cls, term_id):
        # Get all users with shifts in this term
        user_dates = {}
        shifts = Shift.query.filter_by(term_id=term_id).all()
        
        for shift in shifts:
            key = (shift.user_id, shift.date)
            if key not in user_dates:
                user_dates[key] = []
            user_dates[key].append(shift)
        
        all_gaps = []
        policy = Policy.get_policy_for_term(term_id)
        
        if policy:
            for (user_id, shift_date), user_shifts in user_dates.items():
                if len(user_shifts) >= 2:
                    gaps = policy.detect_gaps_for_user_date(user_id, shift_date, user_shifts)
                    all_gaps.extend(gaps)
        
        return all_gaps
    
    @classmethod
    def get_gap_summary(cls, term_id=None, user_id=None):
        policy = Policy.get_policy_for_term(term_id)
        if policy:
            return policy.get_gap_summary(user_id)
        return {'total_gaps': 0, 'by_severity': {'error': 0, 'warning': 0}, 'avg_gap_duration': 0, 'mergeable_gaps': 0}

class UndesirableTimeWindow:
    """Compatibility wrapper - uses Policy.undesirable_windows JSON field"""
    
    def __init__(self, policy_id, name, start_time, end_time, day_of_week=None, weight=1.0, window_type="custom"):
        self.policy_id = policy_id
        self.name = name
        self.start_time = start_time
        self.end_time = end_time
        self.day_of_week = day_of_week
        self.weight = weight
        self.window_type = window_type
    
    @classmethod
    def query_by_policy(cls, policy_id):
        policy = Policy.query.get(policy_id)
        if policy:
            windows = policy.get_undesirable_windows()
            return [cls(**window) for window in windows]
        return []

class TransitionTimeViolation:
    """Compatibility wrapper - uses Policy.transition_violations JSON field"""
    
    @classmethod
    def detect_violations_for_user_date_range(cls, user_id, start_date, end_date, term_id):
        policy = Policy.get_policy_for_term(term_id)
        if policy:
            shifts = Shift.query.filter(
                Shift.user_id == user_id,
                Shift.date >= start_date,
                Shift.date <= end_date,
                Shift.term_id == term_id
            ).all()
            return policy.validate_transition_times_for_user(user_id, shifts)
        return []

class UndesirableShiftTracking:
    """Compatibility wrapper - uses Policy.undesirable_tracking JSON field"""
    
    @classmethod
    def track_shift(cls, user_id, shift_id, term_id, undesirable_type, weight=1.0):
        policy = Policy.get_policy_for_term(term_id)
        if policy:
            policy.track_undesirable_shift(user_id, shift_id, undesirable_type, weight)

class VolunteerPreference:
    """Compatibility wrapper - uses Policy.volunteer_preferences JSON field"""
    
    @classmethod
    def add_preference(cls, user_id, term_id, preference_type, notes=None):
        policy = Policy.get_policy_for_term(term_id)
        if policy:
            policy.add_volunteer_preference(user_id, preference_type, notes)

class RejectedShift:
    """Compatibility wrapper - uses Policy.rejected_shifts JSON field"""
    
    @classmethod
    def log_rejection(cls, term_id, user_id, start_time, end_time, date, reason, duration_minutes):
        policy = Policy.get_policy_for_term(term_id)
        if policy:
            policy.log_rejected_shift(user_id, start_time, end_time, date, reason, duration_minutes)

class SplitShift:
    """Compatibility wrapper - uses Policy.split_shifts JSON field"""
    
    @classmethod
    def log_split(cls, term_id, user_id, original_start, original_end, date, split_count, break_minutes, reason):
        policy = Policy.get_policy_for_term(term_id)
        if policy:
            policy.log_split_shift(user_id, original_start, original_end, date, split_count, break_minutes, reason)

class PolicyAuditLog:
    """Compatibility wrapper - uses Policy.audit_log JSON field"""
    
    @classmethod
    def log_policy_change(cls, policy_id, changed_by_id, change_type, field_name=None, 
                         old_value=None, new_value=None, change_reason=None, **kwargs):
        policy = Policy.query.get(policy_id)
        if policy:
            policy.log_policy_change(changed_by_id, change_type, field_name, old_value, new_value, change_reason)

class ValidationReport:
    """Compatibility wrapper - uses Policy.validation_reports JSON field"""
    
    @classmethod
    def generate_validation_report(cls, term_id, user_id, include_resolved=False):
        policy = Policy.get_policy_for_term(term_id)
        if policy:
            return policy.generate_validation_report(user_id)
        return None