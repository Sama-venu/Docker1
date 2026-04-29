import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, DateTimeField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length, NumberRange
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///restaurant.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_email = db.Column(db.String(120), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    guests = db.Column(db.Integer, nullable=False)
    booking_date = db.Column(db.DateTime, nullable=False)
    special_requests = db.Column(db.Text)
    status = db.Column(db.String(20), default='confirmed')  # confirmed, cancelled, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'customer_name': self.customer_name,
            'customer_email': self.customer_email,
            'customer_phone': self.customer_phone,
            'guests': self.guests,
            'booking_date': self.booking_date.strftime('%Y-%m-%d %H:%M'),
            'special_requests': self.special_requests,
            'status': self.status
        }

class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.Integer, unique=True, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    is_available = db.Column(db.Boolean, default=True)

# Forms
class BookingForm(FlaskForm):
    customer_name = StringField('Name', validators=[DataRequired(), Length(min=2, max=100)])
    customer_email = StringField('Email', validators=[DataRequired(), Email()])
    customer_phone = StringField('Phone', validators=[DataRequired(), Length(min=10, max=20)])
    guests = IntegerField('Number of Guests', validators=[DataRequired(), NumberRange(min=1, max=20)])
    booking_date = StringField('Date & Time', validators=[DataRequired()])
    special_requests = StringField('Special Requests')
    submit = SubmitField('Book Table')

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('//book', methods=['GET', 'POST'])
def book():
    form = BookingForm()
    
    if request.method == 'POST' and form.validate_on_submit():
        try:
            # Parse the booking date
            booking_datetime = datetime.strptime(form.booking_date.data, '%Y-%m-%dT%H:%M')
            
            # Check if booking time is within working hours (10 AM to 10 PM)
            if booking_datetime.hour < 10 or booking_datetime.hour >= 22:
                flash('Bookings are only available between 10:00 AM and 10:00 PM', 'error')
                return render_template('book.html', form=form)
            
            # Check if booking is at least 1 hour in advance
            if booking_datetime < datetime.now() + timedelta(hours=1):
                flash('Bookings must be made at least 1 hour in advance', 'error')
                return render_template('book.html', form=form)
            
            # Create new booking
            booking = Booking(
                customer_name=form.customer_name.data,
                customer_email=form.customer_email.data,
                customer_phone=form.customer_phone.data,
                guests=form.guests.data,
                booking_date=booking_datetime,
                special_requests=form.special_requests.data
            )
            
            db.session.add(booking)
            db.session.commit()
            
            flash(f'Booking confirmed! Your booking ID is {booking.id}', 'success')
            return redirect(url_for('view_booking', booking_id=booking.id))
            
        except ValueError:
            flash('Invalid date format', 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating booking: {str(e)}', 'error')
    
    return render_template('book.html', form=form)

@app.route('/booking/<int:booking_id>')
def view_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    return render_template('view_booking.html', booking=booking)

@app.route('/cancel/<int:booking_id>')
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    
    if booking.status == 'confirmed':
        booking.status = 'cancelled'
        db.session.commit()
        flash(f'Booking {booking_id} has been cancelled', 'success')
    else:
        flash('This booking cannot be cancelled', 'error')
    
    return redirect(url_for('view_booking', booking_id=booking_id))

@app.route('/my-bookings')
def my_bookings():
    # For demo purposes, show recent bookings
    # In production, you'd want email/phone verification
    bookings = Booking.query.order_by(Booking.booking_date.desc()).limit(50).all()
    return render_template('my_bookings.html', bookings=bookings)

@app.route('/api/available-slots')
def available_slots():
    date_str = request.args.get('date')
    guests = int(request.args.get('guests', 1))
    
    if not date_str:
        return jsonify({'error': 'Date required'}), 400
    
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Generate available time slots (every hour from 10 AM to 9 PM)
        available_slots = []
        for hour in range(10, 22):
            slot_time = target_date.replace(hour=hour, minute=0)
            
            # Check if slot is in the past
            if slot_time < datetime.now():
                continue
            
            # Count existing bookings for this slot
            existing_bookings = Booking.query.filter(
                Booking.booking_date.between(slot_time, slot_time + timedelta(hours=1)),
                Booking.status == 'confirmed'
            ).count()
            
            # Assume 10 tables, each can seat up to 6 people
            max_bookings = 10 if guests <= 6 else 5
            is_available = existing_bookings < max_bookings
            
            available_slots.append({
                'time': f'{hour:02d}:00',
                'available': is_available
            })
        
        return jsonify({'slots': available_slots})
        
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

# Admin routes
@app.route('/admin')
def admin_dashboard():
    # In production, add authentication here
    total_bookings = Booking.query.count()
    confirmed_bookings = Booking.query.filter_by(status='confirmed').count()
    cancelled_bookings = Booking.query.filter_by(status='cancelled').count()
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_bookings = Booking.query.filter(
        Booking.booking_date >= today,
        Booking.booking_date < today + timedelta(days=1)
    ).count()
    
    upcoming_bookings = Booking.query.filter(
        Booking.booking_date > datetime.now(),
        Booking.status == 'confirmed'
    ).order_by(Booking.booking_date).limit(20).all()
    
    return render_template('admin.html', 
                         total_bookings=total_bookings,
                         confirmed_bookings=confirmed_bookings,
                         cancelled_bookings=cancelled_bookings,
                         today_bookings=today_bookings,
                         upcoming_bookings=upcoming_bookings)

@app.route('/admin/booking/<int:booking_id>/complete')
def complete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    booking.status = 'completed'
    db.session.commit()
    flash(f'Booking {booking_id} marked as completed', 'success')
    return redirect(url_for('admin_dashboard'))

# Initialize database
with app.app_context():
    db.create_all()
    
    # Create sample tables if none exist
    if Table.query.count() == 0:
        tables_data = [
            (1, 2), (2, 2), (3, 4), (4, 4), (5, 4),
            (6, 6), (7, 6), (8, 8), (9, 8), (10, 10)
        ]
        for table_num, capacity in tables_data:
            table = Table(table_number=table_num, capacity=capacity)
            db.session.add(table)
        db.session.commit()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
