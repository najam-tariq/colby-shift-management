from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    email = db.Column(db.Text, nullable=False, unique=True)
    role = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    password_hash = db.Column(db.Text, nullable=False)
    
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
    
    term = db.relationship('Term', back_populates='policies')
    updated_by_user = db.relationship('User', back_populates='policies_updated')
    undesirable_windows = db.relationship('UndesirableTimeWindow', back_populates='policy', cascade='all, delete')
    
    def __repr__(self):
        return f'<Policy {self.policy_id} for Term {self.term_id}>'

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