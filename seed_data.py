#!/usr/bin/env python3
"""
Seed script to populate database with test data for outputs-access features.
Run with: python seed_data.py
"""

from app import app
from models import db, User, Term, Policy, Shift
from datetime import date, time, timedelta, datetime
import random
import uuid

def seed_database():
    """Seed the database with test data"""
    with app.app_context():
        # Clear existing data (optional - comment out if you want to keep existing data)
        print("Clearing existing data...")
        Shift.query.delete()
        Policy.query.delete()
        Term.query.delete()
        User.query.filter_by(role='student').delete()
        User.query.filter_by(role='supervisor').delete()
        db.session.commit()
        
        # Create supervisor
        print("Creating supervisor...")
        supervisor = User.query.filter_by(email='supervisor@colby.edu').first()
        if not supervisor:
            supervisor = User(
                name='Dr. Sarah Johnson',
                email='supervisor@colby.edu',
                role='supervisor',
                is_active=True,
                calendar_token=str(uuid.uuid4())
            )
            supervisor.set_password('password123')
            db.session.add(supervisor)
            db.session.commit()
        elif not supervisor.calendar_token:
            supervisor.calendar_token = str(uuid.uuid4())
            db.session.commit()
        print(f"Supervisor created: {supervisor.name} (ID: {supervisor.user_id}, Token: {supervisor.calendar_token[:8]}...)")
        
        # Create students
        print("Creating students...")
        students_data = [
            {'name': 'Alex Chen', 'email': 'achen27@colby.edu'},
            {'name': 'Jordan Martinez', 'email': 'jmartinez28@colby.edu'},
            {'name': 'Taylor Williams', 'email': 'twilliams26@colby.edu'},
            {'name': 'Morgan Davis', 'email': 'mdavis29@colby.edu'},
            {'name': 'Casey Brown', 'email': 'cbrown27@colby.edu'},
            {'name': 'Riley Anderson', 'email': 'randerson28@colby.edu'},
            {'name': 'Quinn Thompson', 'email': 'qthompson26@colby.edu'},
            {'name': 'Sam Garcia', 'email': 'sgarcia29@colby.edu'},
        ]
        
        students = []
        for student_data in students_data:
            student = User.query.filter_by(email=student_data['email']).first()
            if not student:
                student = User(
                    name=student_data['name'],
                    email=student_data['email'],
                    role='student',
                    is_active=True,
                    calendar_token=str(uuid.uuid4())
                )
                student.set_password('password123')
                db.session.add(student)
                students.append(student)
            else:
                if not student.calendar_token:
                    student.calendar_token = str(uuid.uuid4())
                students.append(student)
        
        db.session.commit()
        print(f"Created {len(students)} students")
        
        # Create term (Starting from today - 17 weeks)
        print("Creating term...")
        today = date.today()
        # Start from the most recent Monday
        days_since_monday = today.weekday()  # 0 = Monday, 6 = Sunday
        term_start = today - timedelta(days=days_since_monday)  # This week's Monday
        term_end = term_start + timedelta(weeks=17)  # 17 weeks from start
        deadline = term_start - timedelta(days=7)  # Deadline 1 week before term starts
        
        # Determine term name based on month
        term_year = term_start.year
        term_month = term_start.month
        if term_month >= 9:  # September onwards
            term_name = f'Fall {term_year}'
        elif term_month >= 6:  # June-August
            term_name = f'Summer {term_year}'
        else:  # January-May
            term_name = f'Spring {term_year}'
        
        term = Term.query.filter_by(name=term_name).first()
        if not term:
            term = Term(
                name=term_name,
                start_date=term_start,
                end_date=term_end,
                availability_deadline=deadline,
                locked=False
            )
            db.session.add(term)
            db.session.commit()
        else:
            # Update existing term with new dates
            term.start_date = term_start
            term.end_date = term_end
            term.availability_deadline = deadline
            db.session.commit()
        print(f"Term created/updated: {term.name} ({term.start_date} to {term.end_date})")
        
        # Create policy
        print("Creating policy...")
        policy = Policy.query.filter_by(term_id=term.term_id).first()
        if not policy:
            policy = Policy(
                term_id=term.term_id,
                min_shift_length=60,  # 1 hour minimum (60 minutes)
                max_shift_length=180,  # 3 hours maximum (180 minutes)
                min_break_length=60,  # 1 hour minimum break (60 minutes)
                max_break_length=480,  # 8 hours maximum break (480 minutes)
                undesireable_start=600,  # Before 6:00 AM is undesirable (stored as HHMM format)
                undesireable_end=2200,  # After 10:00 PM is undesirable (stored as HHMM format)
                updated_by=supervisor.user_id
            )
            db.session.add(policy)
            db.session.commit()
        print("Policy created with constraints")
        
        # Create staffing needs (comprehensive coverage)
        print("Creating staffing needs...")
        from models import StaffingNeeds
        
        # Check if staffing needs already exist
        existing_needs = StaffingNeeds.query.filter_by(term_id=term.term_id).count()
        if existing_needs == 0:
            # Weekday coverage patterns
            weekday_needs = [
                # Morning shifts
                (time(8, 0), time(12, 0), 'student', 2),   # 8 AM - 12 PM, 2 students
                # Afternoon shifts
                (time(12, 0), time(17, 0), 'student', 2),  # 12 PM - 5 PM, 2 students
                # Evening shifts (less coverage)
                (time(17, 0), time(21, 0), 'student', 1),  # 5 PM - 9 PM, 1 student
            ]
            
            # Apply to Monday-Friday (0-4)
            for day in range(5):
                for start_t, end_t, role, count in weekday_needs:
                    need = StaffingNeeds(
                        term_id=term.term_id,
                        day_of_week=day,
                        start_time=start_t,
                        end_time=end_t,
                        role_required=role,
                        required_count=count
                    )
                    db.session.add(need)
            
            # Weekend coverage (reduced)
            weekend_needs = [
                (time(10, 0), time(14, 0), 'student', 1),  # 10 AM - 2 PM, 1 student
                (time(14, 0), time(18, 0), 'student', 1),  # 2 PM - 6 PM, 1 student
            ]
            
            # Apply to Saturday-Sunday (5-6)
            for day in range(5, 7):
                for start_t, end_t, role, count in weekend_needs:
                    need = StaffingNeeds(
                        term_id=term.term_id,
                        day_of_week=day,
                        start_time=start_t,
                        end_time=end_t,
                        role_required=role,
                        required_count=count
                    )
                    db.session.add(need)
            
            db.session.commit()
            print(f"Created {StaffingNeeds.query.filter_by(term_id=term.term_id).count()} staffing needs")
        
        # Create availability for all students
        print("Creating student availability...")
        from models import Availability
        
        # Check if availability already exists
        existing_avail = Availability.query.filter_by(term_id=term.term_id).count()
        if existing_avail == 0:
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            
            for student in students:
                # Each student has varied availability throughout the week
                # Some students available mornings, some afternoons, some both
                student_pattern = random.choice(['morning', 'afternoon', 'both', 'flexible'])
                
                for day_idx, day_name in enumerate(day_names):
                    # Weekdays (more availability)
                    if day_idx < 5:
                        if student_pattern == 'morning':
                            avail = Availability(
                                user_id=student.user_id,
                                term_id=term.term_id,
                                day_of_week=day_name,
                                start_time=time(8, 0),
                                end_time=time(13, 0),
                                is_exception=False
                            )
                            db.session.add(avail)
                        elif student_pattern == 'afternoon':
                            avail = Availability(
                                user_id=student.user_id,
                                term_id=term.term_id,
                                day_of_week=day_name,
                                start_time=time(12, 0),
                                end_time=time(18, 0),
                                is_exception=False
                            )
                            db.session.add(avail)
                        elif student_pattern == 'both':
                            # Morning block
                            avail1 = Availability(
                                user_id=student.user_id,
                                term_id=term.term_id,
                                day_of_week=day_name,
                                start_time=time(8, 0),
                                end_time=time(12, 0),
                                is_exception=False
                            )
                            db.session.add(avail1)
                            # Afternoon block
                            avail2 = Availability(
                                user_id=student.user_id,
                                term_id=term.term_id,
                                day_of_week=day_name,
                                start_time=time(13, 0),
                                end_time=time(17, 0),
                                is_exception=False
                            )
                            db.session.add(avail2)
                        else:  # flexible
                            avail = Availability(
                                user_id=student.user_id,
                                term_id=term.term_id,
                                day_of_week=day_name,
                                start_time=time(8, 0),
                                end_time=time(21, 0),
                                is_exception=False
                            )
                            db.session.add(avail)
                    
                    # Weekends (reduced availability - only some students)
                    else:
                        if random.random() < 0.5:  # 50% of students available on weekends
                            avail = Availability(
                                user_id=student.user_id,
                                term_id=term.term_id,
                                day_of_week=day_name,
                                start_time=time(10, 0),
                                end_time=time(18, 0),
                                is_exception=False
                            )
                            db.session.add(avail)
            
            db.session.commit()
            print(f"Created {Availability.query.filter_by(term_id=term.term_id).count()} availability records")
        
        # Create shifts for multiple weeks with comprehensive coverage
        print("Creating shifts...")
        
        # More comprehensive shift time patterns
        morning_shifts = [
            (time(8, 0), time(11, 0)),   # 8 AM - 11 AM (3 hours)
            (time(9, 0), time(12, 0)),   # 9 AM - 12 PM (3 hours)
            (time(8, 0), time(10, 0)),   # 8 AM - 10 AM (2 hours)
            (time(10, 0), time(12, 0)),  # 10 AM - 12 PM (2 hours)
            (time(9, 0), time(10, 0)),   # 9 AM - 10 AM (1 hour)
            (time(11, 0), time(12, 0)),  # 11 AM - 12 PM (1 hour)
        ]
        
        afternoon_shifts = [
            (time(12, 0), time(15, 0)),  # 12 PM - 3 PM (3 hours)
            (time(13, 0), time(16, 0)),  # 1 PM - 4 PM (3 hours)
            (time(14, 0), time(17, 0)),  # 2 PM - 5 PM (3 hours)
            (time(12, 0), time(14, 0)),  # 12 PM - 2 PM (2 hours)
            (time(13, 0), time(15, 0)),  # 1 PM - 3 PM (2 hours)
            (time(15, 0), time(17, 0)),  # 3 PM - 5 PM (2 hours)
        ]
        
        evening_shifts = [
            (time(17, 0), time(20, 0)),  # 5 PM - 8 PM (3 hours)
            (time(18, 0), time(21, 0)),  # 6 PM - 9 PM (3 hours)
            (time(17, 0), time(19, 0)),  # 5 PM - 7 PM (2 hours)
            (time(19, 0), time(21, 0)),  # 7 PM - 9 PM (2 hours)
            (time(17, 0), time(18, 0)),  # 5 PM - 6 PM (1 hour)
            (time(20, 0), time(21, 0)),  # 8 PM - 9 PM (1 hour)
        ]
        
        weekend_shifts = [
            (time(10, 0), time(13, 0)),  # 10 AM - 1 PM (3 hours)
            (time(13, 0), time(16, 0)),  # 1 PM - 4 PM (3 hours)
            (time(10, 0), time(12, 0)),  # 10 AM - 12 PM (2 hours)
            (time(14, 0), time(16, 0)),  # 2 PM - 4 PM (2 hours)
        ]
        
        # Generate shifts for all 17 weeks
        shifts_created = 0
        shifts_by_student = {student.user_id: 0 for student in students}
        
        for week_offset in range(17):
            week_start = term_start + timedelta(weeks=week_offset)
            
            # Weekdays (Mon-Fri) - Full coverage
            for day_offset in range(5):
                shift_date = week_start + timedelta(days=day_offset)
                
                # Morning coverage (2-3 students)
                num_morning = random.randint(2, 3)
                morning_selected = random.sample(morning_shifts, min(num_morning, len(morning_shifts)))
                
                for start_time, end_time in morning_selected:
                    # Distribute workload fairly - prefer students with fewer shifts
                    available_students = sorted(students, key=lambda s: shifts_by_student[s.user_id])
                    
                    for student in available_students:
                        # Check if student already has an overlapping shift
                        existing_shifts = Shift.query.filter_by(
                            user_id=student.user_id,
                            date=shift_date
                        ).all()
                        
                        has_conflict = False
                        for existing in existing_shifts:
                            # Check for time overlap
                            if (start_time < existing.end_time and end_time > existing.start_time):
                                has_conflict = True
                                break
                        
                        if not has_conflict:
                            # Randomly mark some shifts as manually adjusted (10% chance)
                            was_adjusted = random.random() < 0.1
                            
                            shift = Shift(
                                term_id=term.term_id,
                                user_id=student.user_id,
                                date=shift_date,
                                start_time=start_time,
                                end_time=end_time,
                                was_manually_adjusted=was_adjusted
                            )
                            db.session.add(shift)
                            shifts_created += 1
                            shifts_by_student[student.user_id] += 1
                            break
                
                # Afternoon coverage (2-3 students)
                num_afternoon = random.randint(2, 3)
                afternoon_selected = random.sample(afternoon_shifts, min(num_afternoon, len(afternoon_shifts)))
                
                for start_time, end_time in afternoon_selected:
                    available_students = sorted(students, key=lambda s: shifts_by_student[s.user_id])
                    
                    for student in available_students:
                        existing_shifts = Shift.query.filter_by(
                            user_id=student.user_id,
                            date=shift_date
                        ).all()
                        
                        has_conflict = False
                        for existing in existing_shifts:
                            if (start_time < existing.end_time and end_time > existing.start_time):
                                has_conflict = True
                                break
                        
                        if not has_conflict:
                            was_adjusted = random.random() < 0.1
                            
                            shift = Shift(
                                term_id=term.term_id,
                                user_id=student.user_id,
                                date=shift_date,
                                start_time=start_time,
                                end_time=end_time,
                                was_manually_adjusted=was_adjusted
                            )
                            db.session.add(shift)
                            shifts_created += 1
                            shifts_by_student[student.user_id] += 1
                            break
                
                # Evening coverage (1-2 students, less frequent)
                if random.random() < 0.6:  # 60% chance of evening shift
                    num_evening = random.randint(1, 2)
                    evening_selected = random.sample(evening_shifts, min(num_evening, len(evening_shifts)))
                    
                    for start_time, end_time in evening_selected:
                        available_students = sorted(students, key=lambda s: shifts_by_student[s.user_id])
                        
                        for student in available_students:
                            existing_shifts = Shift.query.filter_by(
                                user_id=student.user_id,
                                date=shift_date
                            ).all()
                            
                            has_conflict = False
                            for existing in existing_shifts:
                                if (start_time < existing.end_time and end_time > existing.start_time):
                                    has_conflict = True
                                    break
                            
                            if not has_conflict:
                                was_adjusted = random.random() < 0.1
                                
                                shift = Shift(
                                    term_id=term.term_id,
                                    user_id=student.user_id,
                                    date=shift_date,
                                    start_time=start_time,
                                    end_time=end_time,
                                    was_manually_adjusted=was_adjusted
                                )
                                db.session.add(shift)
                                shifts_created += 1
                                shifts_by_student[student.user_id] += 1
                                break
            
            # Weekend coverage (Sat-Sun) - Reduced coverage
            for day_offset in range(5, 7):  # Saturday and Sunday
                shift_date = week_start + timedelta(days=day_offset)
                
                # Only 40% chance of weekend shifts
                if random.random() < 0.4:
                    num_weekend = random.randint(1, 2)
                    weekend_selected = random.sample(weekend_shifts, min(num_weekend, len(weekend_shifts)))
                    
                    for start_time, end_time in weekend_selected:
                        available_students = sorted(students, key=lambda s: shifts_by_student[s.user_id])
                        
                        for student in available_students:
                            existing_shifts = Shift.query.filter_by(
                                user_id=student.user_id,
                                date=shift_date
                            ).all()
                            
                            has_conflict = False
                            for existing in existing_shifts:
                                if (start_time < existing.end_time and end_time > existing.start_time):
                                    has_conflict = True
                                    break
                            
                            if not has_conflict:
                                was_adjusted = random.random() < 0.1
                                
                                shift = Shift(
                                    term_id=term.term_id,
                                    user_id=student.user_id,
                                    date=shift_date,
                                    start_time=start_time,
                                    end_time=end_time,
                                    was_manually_adjusted=was_adjusted
                                )
                                db.session.add(shift)
                                shifts_created += 1
                                shifts_by_student[student.user_id] += 1
                                break
        
        db.session.commit()
        print(f"Created {shifts_created} shifts across 17 weeks")
        print(f"Shifts per student: {dict(sorted(shifts_by_student.items(), key=lambda x: x[1], reverse=True))}")
        
        # Calculate detailed statistics
        total_hours = 0
        for shift in Shift.query.filter_by(term_id=term.term_id).all():
            duration = (datetime.combine(shift.date, shift.end_time) - 
                       datetime.combine(shift.date, shift.start_time)).seconds / 3600
            total_hours += duration
        
        # Print comprehensive summary
        print("\n" + "="*70)
        print(" " * 20 + "SEED DATA SUMMARY")
        print("="*70)
        print(f"\n🔑 LOGIN CREDENTIALS")
        print("-" * 70)
        print(f"Supervisor: {supervisor.name} ({supervisor.email})")
        print(f"  Password: password123")
        print(f"  Calendar Token: {supervisor.calendar_token}")
        
        print(f"\n👥 STUDENTS ({len(students)} total):")
        print("-" * 70)
        for i, student in enumerate(students, 1):
            shift_count = Shift.query.filter_by(user_id=student.user_id).count()
            student_hours = sum(
                (datetime.combine(s.date, s.end_time) - datetime.combine(s.date, s.start_time)).seconds / 3600
                for s in Shift.query.filter_by(user_id=student.user_id).all()
            )
            print(f"  {i}. {student.name}")
            print(f"     Email: {student.email} | Password: password123")
            print(f"     Shifts: {shift_count} | Hours: {student_hours:.1f} | Avg: {student_hours/shift_count if shift_count > 0 else 0:.1f} hrs/shift")
            print(f"     Calendar Token: {student.calendar_token}")
        
        print(f"\n📅 TERM INFORMATION")
        print("-" * 70)
        print(f"Term: {term.name}")
        print(f"Period: {term.start_date} to {term.end_date}")
        print(f"Duration: 17 weeks ({(term.end_date - term.start_date).days + 1} days)")
        print(f"Availability Deadline: {term.availability_deadline}")
        print(f"Status: {'🔒 Locked' if term.locked else '🔓 Unlocked'}")
        
        print(f"\n📊 SCHEDULE STATISTICS")
        print("-" * 70)
        print(f"Total Shifts Created: {shifts_created}")
        print(f"Total Hours Scheduled: {total_hours:.1f} hours")
        print(f"Average Hours per Student: {total_hours / len(students):.1f} hours")
        print(f"Average Hours per Week: {total_hours / 17:.1f} hours")
        print(f"Manually Adjusted Shifts: {Shift.query.filter_by(was_manually_adjusted=True).count()}")
        
        print(f"\n⚙️ POLICY CONSTRAINTS")
        print("-" * 70)
        print(f"Min Shift Length: {policy.min_shift_length} minutes (1 hour)")
        print(f"Max Shift Length: {policy.max_shift_length} minutes (3 hours)")
        print(f"Min Break Length: {policy.min_break_length} minutes (1 hour)")
        print(f"Max Break Length: {policy.max_break_length} minutes (8 hours)")
        print(f"Undesirable Start: {policy.undesireable_start} (6:00 AM)")
        print(f"Undesirable End: {policy.undesireable_end} (10:00 PM)")
        print(f"Gap Prevention: {'✓ Enabled' if policy.allow_gap_merging else '✗ Disabled'}")
        print(f"Min Transition Time: {policy.min_transition_time} minutes")
        
        print(f"\n📋 STAFFING NEEDS")
        print("-" * 70)
        staffing_count = StaffingNeeds.query.filter_by(term_id=term.term_id).count()
        print(f"Total Coverage Windows: {staffing_count}")
        print(f"Weekday Coverage: 8 AM - 9 PM")
        print(f"Weekend Coverage: 10 AM - 6 PM")
        
        print(f"\n📅 AVAILABILITY DATA")
        print("-" * 70)
        avail_count = Availability.query.filter_by(term_id=term.term_id).count()
        print(f"Total Availability Records: {avail_count}")
        print(f"Students with Availability: {len(students)} / {len(students)}")
        
        # Calculate availability hours per student
        for student in students[:3]:  # Show first 3 as examples
            student_avail = Availability.query.filter_by(
                user_id=student.user_id,
                term_id=term.term_id
            ).all()
            total_avail_hours = sum(
                (datetime.combine(date.today(), a.end_time) - 
                 datetime.combine(date.today(), a.start_time)).seconds / 3600
                for a in student_avail
            )
            print(f"  • {student.name}: {len(student_avail)} windows, {total_avail_hours:.1f} hrs/week available")
        
        print("\n" + "="*70)
        print(" " * 15 + "🚀 READY TO DEMO - COMPLETE WORKFLOW")
        print("="*70)
        print("\n1️⃣  LOGIN")
        print("   → http://localhost:5000/login")
        print("   → Use: supervisor@colby.edu / password123")
        
        print("\n2️⃣  SCHEDULER (NEW! - Issues #44 & #45)")
        print("   → Navigate: Scheduler from navbar")
        print("   → See: 17-week overview with existing shifts")
        print("   → Action: Generate more weeks or edit existing shifts")
        
        print("\n3️⃣  EDIT SCHEDULE (NEW!)")
        print("   → Navigate: Scheduler → Edit Schedule")
        print("   → Features: Click shifts to edit, add new shifts, delete, reassign")
        print("   → Validation: Real-time constraint checking")
        
        print("\n4️⃣  PREVIEW & EXPORT")
        print("   → Navigate: Outputs → Preview")
        print("   → Export: CSV, iCal with VTIMEZONE")
        print("   → Student Views: Individual schedules with secure tokens")
        
        print("\n5️⃣  AVAILABILITY & STAFFING")
        print("   → Navigate: Availability → Upload CSV")
        print("   → Navigate: Staffing → Define coverage windows")
        
        print("\n6️⃣  CONSTRAINTS & VALIDATION")
        print("   → Navigate: Constraints → Gap Management")
        print("   → Navigate: Constraints → Validation Reports")
        print("   → Navigate: Constraints → Policy Configuration")
        
        print("\n" + "="*70)
        print(" " * 25 + "ALL FEATURES READY!")
        print("="*70 + "\n")

if __name__ == '__main__':
    seed_database()

