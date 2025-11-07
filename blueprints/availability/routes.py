from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from . import availability_bp
from models import db, User, Availability, Term
import requests
import csv
import io
from dotenv import load_dotenv
from datetime import datetime

# GitHub Issues #1-12: Availability & Inputs
# Features: Availability management, CSV import, templates, deadlines, etc.

@availability_bp.route('/', methods=['GET', 'POST'])
def availability():
    # Term selection similar to staffing: query param term_id selects active term, else latest
    selected_term_id = request.args.get('term_id', type=int)
    available_terms = Term.query.order_by(Term.start_date.desc()).all()
    if selected_term_id:
        active_term = Term.query.get(selected_term_id)
    else:
        active_term = available_terms[0] if available_terms else None
    if not active_term:
        # No term exists yet; instruct user to create one on staffing page
        return redirect(url_for('staffing.index'))

    if request.method == 'POST':
        action = request.form.get('action')

        # -------------------
        # CSV UPLOAD
        # -------------------
        if action == 'upload':
            file = request.files.get('csv_file')
            if not file or not file.filename.endswith('.csv'):
                flash('Please upload a valid CSV file.', 'error')
                return redirect(url_for('availability.availability', term_id=active_term.term_id))

            try:
                stream = io.StringIO(file.stream.read().decode('UTF8'))
                reader = csv.DictReader(stream)

                for row in reader:
                    user = User.query.filter_by(name=row['name']).first()
                    if not user:
                        continue

                    # Normalize day names to 3-letter format
                    day = row['day_of_week'].strip().capitalize()[:3]

                    start_time = datetime.strptime(row['start_time'], '%H:%M').time()
                    end_time = datetime.strptime(row['end_time'], '%H:%M').time()

                    new_avail = Availability(
                        user_id=user.user_id,
                        term_id=active_term.term_id,
                        day_of_week=day,
                        start_time=start_time,
                        end_time=end_time
                    )
                    db.session.add(new_avail)

                db.session.commit()
                flash('CSV data uploaded successfully!', 'success')

            except Exception as e:
                db.session.rollback()
                flash(f'Error uploading CSV: {e}', 'error')

            return redirect(url_for('availability.availability', term_id=active_term.term_id))

        # -------------------
        # MANUAL UPDATES
        # -------------------
        elif action == 'update':
            try:
                student_names = request.form.getlist('student_name[]')
                days = ['mon','tue','wed','thu','fri','sat','sun']

                for i, name in enumerate(student_names):
                    if not name.strip():
                        continue

                    user = User.query.filter_by(name=name.strip()).first()
                    if not user:
                        continue

                    for day in days:
                        block = request.form.getlist(f'{day}[]')[i]
                        if not block.strip():
                            Availability.query.filter_by(user_id=user.user_id, term_id=active_term.term_id, day_of_week=day.capitalize()[:3]).delete()
                            continue

                        try:
                            start, end = [t.strip() for t in block.split('-')]

                            try:
                                start_time = datetime.strptime(start, '%I:%M %p').time()
                            except ValueError:
                                start_time = datetime.strptime(start, '%I%p').time()

                            try:
                                end_time = datetime.strptime(end, '%I:%M %p').time()
                            except ValueError:
                                end_time = datetime.strptime(end, '%I%p').time()

                            Availability.query.filter_by(user_id=user.user_id, term_id=active_term.term_id, day_of_week=day.capitalize()[:3]).delete()

                            new_avail = Availability(
                                user_id=user.user_id,
                                term_id=active_term.term_id,
                                day_of_week=day.capitalize()[:3],
                                start_time=start_time,
                                end_time=end_time
                            )
                            db.session.add(new_avail)

                        except ValueError:
                            flash(f"Invalid time format for {name}'s {day.capitalize()} entry.", 'error')

                db.session.commit()
                flash('Availability updated successfully!', 'success')

            except Exception as e:
                db.session.rollback()
                flash(f'Error updating availability: {e}', 'error')

        # After any POST, redirect to preserve PRG pattern
        return redirect(url_for('availability.availability', term_id=active_term.term_id))

    # -------------------
    # GET REQUEST — SHOW CURRENT AVAILABILITY
    # -------------------
    # Filter availability by active term
    if current_user.role.lower() == 'supervisor':
        all_availability = Availability.query.join(User).filter(Availability.term_id == active_term.term_id).all()
    else:
        all_availability = Availability.query.filter_by(user_id=current_user.user_id, term_id=active_term.term_id).all()



    # Organize data by user → day (3-letter format)
    availability_data = {}
    for a in all_availability:
        user = a.user
        if user.name not in availability_data:
            availability_data[user.name] = {d: "" for d in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']}

        day_key = a.day_of_week[:3].capitalize()
        start_str = a.start_time.strftime("%I:%M %p").lstrip("0")
        end_str = a.end_time.strftime("%I:%M %p").lstrip("0")
        availability_data[user.name][day_key] = f"{start_str} - {end_str}" if a.start_time and a.end_time else ""
        print(availability_data)
    return render_template('availability_index.html', availability_data=availability_data, active_term=active_term, available_terms=available_terms)




    return render_template('availability_index.html',
                           availability_data=availability_data,
                           active_term=active_term,
                           available_terms=available_terms)



