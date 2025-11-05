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
    __tablename__ = "Availability"
    
    availiability_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    term_id = db.Column(db.Integer, db.ForeignKey('terms.term_id'))
    day_of_week = db.Column(db.Text, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_exception = db.Column(db.Boolean, nullable=False, default=False)
    
    user = db.relationship('User', back_populates='availability')
    term = db.relationship('Term', back_populates='availability')

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
    
    def __repr__(self):
        return f'<Term {self.name}>'

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