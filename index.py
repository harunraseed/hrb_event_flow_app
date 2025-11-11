import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, Response
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, DateField, TimeField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, URL
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import csv
import io
import base64
from uuid import uuid4

load_dotenv()

# CRITICAL: Specify static and template folders
app = Flask(__name__,
            static_folder='static',
            static_url_path='/static',
            template_folder='templates')

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

# WTForms
class CreateEventForm(FlaskForm):
    name = StringField('Event Name', validators=[DataRequired(), Length(min=1, max=200)])
    alias_name = StringField('Alias Name', validators=[Optional(), Length(max=50)])
    date = DateField('Event Date', validators=[DataRequired()])
    time = TimeField('Event Time', validators=[Optional()])
    logo = FileField('Event Logo', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')])
    location = TextAreaField('Location', validators=[Optional()])
    google_maps_url = StringField('Google Maps URL', validators=[Optional(), URL()])
    description = TextAreaField('Description', validators=[Optional()])
    organizer_name = StringField('Organizer Name', validators=[Optional(), Length(max=200)])
    instructions = TextAreaField('Instructions', validators=[Optional()])
    submit = SubmitField('Create Event')

# Database Models
class Event(db.Model):
    __tablename__ = 'events'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    alias_name = db.Column(db.String(50))  # For ticket numbering
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time)  # Event start time
    logo = db.Column(db.String(255))  # Logo file path
    location = db.Column(db.Text)  # Event location
    google_maps_url = db.Column(db.Text)  # Google Maps link
    description = db.Column(db.Text)
    organizer_name = db.Column(db.String(200))  # Organizer name
    instructions = db.Column(db.Text)  # Detailed instructions
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

# Favicon routes - prevent 404 errors
@app.route('/favicon.ico')
@app.route('/favicon.png')
def favicon():
    return '', 204

# Helper function for templates
@app.template_filter('logo_url')
def logo_url_filter(logo_base64):
    """Convert base64 logo to data URL for templates"""
    if logo_base64 and logo_base64.startswith('data:'):
        return logo_base64
    return None

# Routes
@app.route('/')
def index():
    try:
        events = Event.query.order_by(Event.date.desc()).all()
    except Exception as e:
        print(f"Error fetching events: {e}")
        events = []
    return render_template('index.html', events=events)

@app.route('/create_event', methods=['GET', 'POST'])
def create_event():
    form = CreateEventForm()
    
    if form.validate_on_submit():
        try:
            # Handle logo upload - convert to base64
            logo_base64 = None
            if form.logo.data:
                try:
                    logo_file = form.logo.data
                    # Read the file content
                    logo_content = logo_file.read()
                    # Convert to base64
                    logo_base64_encoded = base64.b64encode(logo_content).decode('utf-8')
                    # Create data URL with proper MIME type
                    file_extension = logo_file.filename.lower().split('.')[-1]
                    mime_types = {
                        'jpg': 'image/jpeg',
                        'jpeg': 'image/jpeg', 
                        'png': 'image/png',
                        'gif': 'image/gif'
                    }
                    mime_type = mime_types.get(file_extension, 'image/png')
                    logo_base64 = f"data:{mime_type};base64,{logo_base64_encoded}"
                    
                    # Reset file pointer (just in case)
                    logo_file.seek(0)
                    
                except Exception as e:
                    flash(f'Error processing logo: {str(e)}', 'error')
                    logo_base64 = None
            
            # Create event with all fields
            event = Event(
                name=form.name.data,
                alias_name=form.alias_name.data,
                date=form.date.data,
                time=form.time.data,
                logo=logo_base64,
                location=form.location.data,
                google_maps_url=form.google_maps_url.data,
                description=form.description.data,
                organizer_name=form.organizer_name.data,
                instructions=form.instructions.data
            )
            
            db.session.add(event)
            db.session.commit()
            flash(f'Event "{form.name.data}" created successfully!', 'success')
            return redirect(url_for('upload_participants', event_id=event.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating event: {str(e)}', 'error')
    
    return render_template('create_event.html', form=form)

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
            db.session.rollback()
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

# Error handlers
@app.errorhandler(401)
def unauthorized(error):
    return render_template('401.html'), 401

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

# Prevent files from being downloaded as attachments
@app.after_request
def after_request(response):
    if response.content_type and 'text/html' in response.content_type:
        response.headers['Content-Disposition'] = 'inline'
    return response

# Initialize database on startup
with app.app_context():
    try:
        # For development: drop and recreate tables to handle schema changes
        if os.getenv('FLASK_ENV') == 'development':
            db.drop_all()
            print("✓ Dropped existing tables")
        db.create_all()
        print("✓ Database tables created/verified")
    except Exception as e:
        print(f"Warning: Could not create database tables: {e}")

# Export for Vercel
application = app

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_ENV') == 'development')