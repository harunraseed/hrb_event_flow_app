import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from dotenv import load_dotenv
import csv
import io
from uuid import uuid4

load_dotenv()

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

db = SQLAlchemy(app)
mail = Mail(app)

# Database Models
class Event(db.Model):
    __tablename__ = 'events'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    participants = db.relationship('Participant', backref='event', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Event {self.name}>'

class Participant(db.Model):
    __tablename__ = 'participants'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    ticket_number = db.Column(db.String(50), unique=True, nullable=False)
    checked_in = db.Column(db.Boolean, default=False)
    checkin_time = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Participant {self.name}>'

# Routes
@app.route('/')
def index():
    events = Event.query.order_by(Event.date.desc()).all()
    return render_template('index.html', events=events)

@app.route('/create_event', methods=['GET', 'POST'])
def create_event():
    if request.method == 'POST':
        name = request.form.get('name')
        date_str = request.form.get('date')
        description = request.form.get('description')
        
        if not name or not date_str:
            flash('Event name and date are required!', 'error')
            return redirect(url_for('create_event'))
        
        try:
            event_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            event = Event(name=name, date=event_date, description=description)
            db.session.add(event)
            db.session.commit()
            flash(f'Event "{name}" created successfully!', 'success')
            return redirect(url_for('upload_participants', event_id=event.id))
        except Exception as e:
            flash(f'Error creating event: {str(e)}', 'error')
            return redirect(url_for('create_event'))
    
    return render_template('create_event.html')

@app.route('/upload_participants/<int:event_id>', methods=['GET', 'POST'])
def upload_participants(event_id):
    event = Event.query.get_or_404(event_id)
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(url_for('upload_participants', event_id=event_id))
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('upload_participants', event_id=event_id))
        
        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file', 'error')
            return redirect(url_for('upload_participants', event_id=event_id))
        
        try:
            stream = io.TextIOWrapper(file.stream, encoding='utf-8')
            csv_data = csv.DictReader(stream)
            
            for row in csv_data:
                name = row.get('name', '').strip()
                email = row.get('email', '').strip()
                
                if not name or not email:
                    continue
                
                ticket_number = str(uuid4())[:12].upper()
                participant = Participant(
                    event_id=event_id,
                    name=name,
                    email=email,
                    ticket_number=ticket_number
                )
                db.session.add(participant)
            
            db.session.commit()
            flash('Participants uploaded successfully!', 'success')
            return redirect(url_for('send_emails', event_id=event_id))
        except Exception as e:
            flash(f'Error uploading participants: {str(e)}', 'error')
            return redirect(url_for('upload_participants', event_id=event_id))
    
    return render_template('upload_participants.html', event=event)

@app.route('/event/<int:event_id>/dashboard')
def event_dashboard(event_id):
    event = Event.query.get_or_404(event_id)
    participants = Participant.query.filter_by(event_id=event_id).all()
    
    stats = {
        'total': len(participants),
        'checked_in': sum(1 for p in participants if p.checked_in),
        'pending': sum(1 for p in participants if not p.checked_in)
    }
    
    return render_template('event_dashboard.html', event=event, participants=participants, stats=stats)

@app.route('/participant/<int:participant_id>/checkin', methods=['POST'])
def toggle_checkin(participant_id):
    participant = Participant.query.get_or_404(participant_id)
    participant.checked_in = not participant.checked_in
    if participant.checked_in:
        participant.checkin_time = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True, 'status': participant.checked_in})

@app.route('/send_emails/<int:event_id>')
def send_emails(event_id):
    event = Event.query.get_or_404(event_id)
    participants = Participant.query.filter_by(event_id=event_id).all()
    
    try:
        for participant in participants:
            msg = Message(
                subject=f'Your Ticket for {event.name}',
                recipients=[participant.email],
                html=render_template('email/ticket_email.html', 
                                   event=event, 
                                   participant=participant)
            )
            mail.send(msg)
        
        flash(f'Emails sent to {len(participants)} participants!', 'success')
    except Exception as e:
        flash(f'Error sending emails: {str(e)}', 'error')
    
    return redirect(url_for('event_dashboard', event_id=event_id))

@app.route('/event/<int:event_id>/export')
def export_attendance(event_id):
    from flask import Response
    event = Event.query.get_or_404(event_id)
    participants = Participant.query.filter_by(event_id=event_id).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'Email', 'Ticket Number', 'Checked In', 'Check-in Time'])
    
    for p in participants:
        writer.writerow([
            p.name,
            p.email,
            p.ticket_number,
            'Yes' if p.checked_in else 'No',
            p.checkin_time.strftime('%Y-%m-%d %H:%M:%S') if p.checkin_time else ''
        ])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=attendance_{event.id}.csv'}
    )

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

# Export the app for Vercel
application = app

# Initialize database on startup
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_ENV') == 'development')