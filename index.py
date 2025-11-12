import os
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, Response
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, DateField, TimeField, SubmitField, BooleanField, SelectField
from wtforms.validators import DataRequired, Length, Optional, URL, Email
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import csv
import io
import base64
from uuid import uuid4
from utils.storage import StorageManager
import tempfile
import pdfkit

load_dotenv()

# Initialize storage manager after loading environment
storage_manager = StorageManager()

# CRITICAL: Specify static and template folders
app = Flask(__name__,
            static_folder='static',
            static_url_path='/static',
            template_folder='templates')

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Database configuration
if os.getenv('DATABASE_URL'):
    # Use PostgreSQL in production (including Vercel)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    print("Using PostgreSQL database")
else:
    # Use SQLite for local development
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///event_ticketing.db'
    print("Using SQLite database for local development")

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
# Temporarily disable CSRF for development
# csrf = CSRFProtect(app)

# Helper functions for email
def test_email_connection():
    """Test email connection without sending."""
    import smtplib
    
    mail_server = app.config.get('MAIL_SERVER')
    mail_port = app.config.get('MAIL_PORT')
    mail_username = app.config.get('MAIL_USERNAME')
    mail_password = app.config.get('MAIL_PASSWORD')
    
    print(f"Testing connection to {mail_server}:{mail_port}")
    
    server = smtplib.SMTP(mail_server, mail_port, timeout=10)
    server.starttls()
    server.login(mail_username, mail_password)
    server.quit()
    
    print("Email connection test successful")

def send_ticket_email(participant, event):
    """Send individual ticket email to a participant."""
    try:
        print(f"Preparing email for {participant.email}")
        
        subject = f"Registration Confirmation - Your Ticket for {event.name}"
        
        # Create message
        msg = Message(
            subject=subject,
            recipients=[participant.email],
            html=render_template('email/ticket_email.html', 
                               event=event, 
                               participant=participant)
        )
        
        # Send email
        mail.send(msg)
        print(f"? Email sent successfully to {participant.email}")
        
    except Exception as e:
        print(f"? Failed to send email to {participant.email}: {str(e)}")
        raise e

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

class EditParticipantForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=1, max=200)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=200)])
    checked_in = BooleanField('Checked In')
    submit = SubmitField('Update Participant')

class CertificateConfigForm(FlaskForm):
    # Basic certificate settings
    certificate_type = SelectField('Certificate Type', 
                                 choices=[('participation', 'Participation'), 
                                         ('completion', 'Completion'), 
                                         ('achievement', 'Achievement')],
                                 default='participation')
    
    # Organization details
    organizer_name = StringField('Organizer Name', validators=[Optional(), Length(max=200)],
                                default='Azure Developer Community Tamilnadu')
    sponsor_name = StringField('Sponsor Name', validators=[Optional(), Length(max=200)],
                              default='Microsoft')
    event_location = StringField('Event Location', validators=[Optional(), Length(max=200)])
    event_theme = StringField('Event Theme', validators=[Optional(), Length(max=500)],
                             default='advanced technologies and innovation')
    
    # Logo uploads and URLs
    organizer_logo_file = FileField('Organizer Logo Upload', 
                                   validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')])
    organizer_logo_url = StringField('Organizer Logo URL', validators=[Optional(), URL(), Length(max=500)])
    
    sponsor_logo_file = FileField('Sponsor Logo Upload', 
                                 validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')])
    sponsor_logo_url = StringField('Sponsor Logo URL', validators=[Optional(), URL(), Length(max=500)])
    
    # Signature 1 details
    signature1_name = StringField('First Signatory Name', validators=[Optional(), Length(max=200)])
    signature1_title = StringField('First Signatory Title', validators=[Optional(), Length(max=200)],
                                  default='Organizer')
    signature1_file = FileField('First Signature Upload', 
                               validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')])
    signature1_image_url = StringField('First Signature URL', validators=[Optional(), URL(), Length(max=500)])
    
    # Signature 2 details
    signature2_name = StringField('Second Signatory Name', validators=[Optional(), Length(max=200)])
    signature2_title = StringField('Second Signatory Title', validators=[Optional(), Length(max=200)],
                                  default='Event Lead')
    signature2_file = FileField('Second Signature Upload', 
                               validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')])
    signature2_image_url = StringField('Second Signature URL', validators=[Optional(), URL(), Length(max=500)])
    
    # Settings
    send_to_all_checked_in = BooleanField('Send to all checked-in participants', default=True)
    
    submit = SubmitField('Save Configuration')

# Database Models
class Event(db.Model):
    __tablename__ = 'events'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    alias_name = db.Column(db.String(50))  # For ticket numbering
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time)  # Event start time
    logo = db.Column(db.Text)  # Logo as base64 string
    location = db.Column(db.Text)  # Event location
    google_maps_url = db.Column(db.Text)  # Google Maps link
    description = db.Column(db.Text)
    organizer_name = db.Column(db.String(200))  # Organizer name
    instructions = db.Column(db.Text)  # Detailed instructions
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    participants = db.relationship('Participant', backref='event', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Event {self.name}>'
    
    def generate_ticket_number(self):
        """Generate unique ticket number in format: ALIAS-EVENTDATE-001"""
        # Use alias_name if available, otherwise use first 3 letters of event name
        if self.alias_name:
            prefix = self.alias_name.upper()
        else:
            prefix = self.name.replace(' ', '')[:3].upper()
        
        # Format date as DDMMYYYY 
        date_str = self.date.strftime('%d%m%Y')
        
        # Find the next available number by checking existing ticket numbers
        base_pattern = f"{prefix}-{date_str}-"
        
        # Get all existing ticket numbers for this event with the same pattern
        existing_participants = Participant.query.filter_by(event_id=self.id).all()
        existing_numbers = []
        
        for participant in existing_participants:
            if participant.ticket_number and participant.ticket_number.startswith(base_pattern):
                try:
                    # Extract the number part (last 3 digits)
                    number_part = participant.ticket_number.split('-')[-1]
                    existing_numbers.append(int(number_part))
                except (ValueError, IndexError):
                    continue
        
        # Find the next available number
        next_number = 1
        while next_number in existing_numbers:
            next_number += 1
        
        return f"{prefix}-{date_str}-{next_number:03d}"

class Participant(db.Model):
    __tablename__ = 'participants'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    ticket_number = db.Column(db.String(50), unique=True, nullable=False)
    checked_in = db.Column(db.Boolean, default=False)
    checkin_time = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Participant {self.name}>'

# Certificate model
class Certificate(db.Model):
    __tablename__ = 'certificates'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    participant_id = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False)
    
    # Certificate details
    certificate_number = db.Column(db.String(100), unique=True, nullable=False)
    certificate_type = db.Column(db.String(50), default='participation')  # participation, completion, achievement
    
    # Organizer and event details
    organizer_name = db.Column(db.String(200))
    sponsor_name = db.Column(db.String(200))
    event_location = db.Column(db.String(200))
    event_theme = db.Column(db.String(500))
    
    # Logo URLs
    organizer_logo_url = db.Column(db.String(500))
    sponsor_logo_url = db.Column(db.String(500))
    
    # Signature details
    signature1_name = db.Column(db.String(200))
    signature1_title = db.Column(db.String(200))
    signature1_image_url = db.Column(db.String(500))
    
    signature2_name = db.Column(db.String(200))
    signature2_title = db.Column(db.String(200))
    signature2_image_url = db.Column(db.String(500))
    
    # Timestamps
    issued_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    email_sent = db.Column(db.Boolean, default=False)
    email_sent_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    event = db.relationship('Event', backref='certificates')
    participant = db.relationship('Participant', backref=db.backref('certificates', cascade='all, delete-orphan'))
    
    def __repr__(self):
        return f'<Certificate {self.certificate_number}>'

# Certificate Configuration model (one per event)
class CertificateConfig(db.Model):
    __tablename__ = 'certificate_configs'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False, unique=True)
    
    # Configuration details
    certificate_type = db.Column(db.String(50), default='participation')
    organizer_name = db.Column(db.String(200))
    sponsor_name = db.Column(db.String(200))
    event_location = db.Column(db.String(200))
    event_theme = db.Column(db.String(500))
    
    # Logo URLs
    organizer_logo_url = db.Column(db.String(500))
    sponsor_logo_url = db.Column(db.String(500))
    
    # Signature details
    signature1_name = db.Column(db.String(200))
    signature1_title = db.Column(db.String(200))
    signature1_image_url = db.Column(db.String(500))
    
    signature2_name = db.Column(db.String(200))
    signature2_title = db.Column(db.String(200))
    signature2_image_url = db.Column(db.String(500))
    
    # Settings
    send_to_all_checked_in = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationship
    event = db.relationship('Event', backref=db.backref('certificate_config', uselist=False))
    
    def __repr__(self):
        return f'<CertificateConfig for {self.event.name}>'

# Add property to Event model for certificate status
@property
def has_certificate_config(self):
    return self.certificate_config is not None

Event.has_certificate_config = has_certificate_config

# Favicon routes - prevent 404 errors
@app.route('/favicon.ico')
@app.route('/favicon.png')
def favicon():
    return '', 204

# Helper function for templates
@app.template_filter('logo_url')
def logo_url_filter(logo_url):
    """Return logo URL if it exists"""
    if logo_url:
        return logo_url
    return None

# Debug endpoint for checking storage configuration
@app.route('/debug/storage')
def debug_storage():
    """Debug endpoint to check storage configuration"""
    debug_info = {
        'github_repo': storage_manager.github_repo,
        'github_branch': storage_manager.github_branch,
        'github_token_set': bool(storage_manager.github_token),
        'github_token_length': len(storage_manager.github_token) if storage_manager.github_token else 0,
        'storage_type': storage_manager.storage_type
    }
    return f"<pre>{str(debug_info)}</pre>"

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
            # Handle logo upload using storage manager
            logo_url = None
            if form.logo.data:
                print(f"?? Processing logo upload for file: {form.logo.data.filename}")
                print(f"?? GitHub Token Available: {bool(storage_manager.github_token)}")
                print(f"?? Target Repository: {storage_manager.github_repo}")
                try:
                    logo_url = storage_manager.save_image(form.logo.data, folder="logos")
                    if logo_url:
                        print(f"? Logo uploaded successfully: {logo_url}")
                        flash(f'Logo uploaded successfully to: {logo_url}', 'success')
                    else:
                        print("? Logo upload failed - no URL returned")
                        flash('Error uploading logo. Event created without logo.', 'warning')
                except Exception as e:
                    print(f"? Exception during logo upload: {str(e)}")
                    flash(f'Error processing logo: {str(e)}', 'warning')
                    logo_url = None
            else:
                print("?? No logo file provided")
            
            # Create event with all fields
            event = Event(
                name=form.name.data,
                alias_name=form.alias_name.data,
                date=form.date.data,
                time=form.time.data,
                logo=logo_url,
                location=form.location.data,
                google_maps_url=form.google_maps_url.data,
                description=form.description.data,
                organizer_name=form.organizer_name.data,
                instructions=form.instructions.data
            )
            
            db.session.add(event)
            db.session.commit()
            flash(f'Event "{form.name.data}" created successfully!', 'success')
            return redirect(url_for('event_created_success', event_id=event.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating event: {str(e)}', 'error')
    
    return render_template('create_event.html', form=form)

@app.route('/event_created/<int:event_id>')
def event_created_success(event_id):
    """Success page after creating an event"""
    event = Event.query.get_or_404(event_id)
    return render_template('event_created_success.html', event=event)

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
                
                ticket_number = event.generate_ticket_number()
                participant = Participant(
                    event_id=event_id,
                    name=name,
                    email=email,
                    ticket_number=ticket_number
                )
                db.session.add(participant)
            
            db.session.commit()
            flash('Participants uploaded successfully!', 'success')
            return redirect(url_for('event_dashboard', event_id=event_id))
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

@app.route('/participants/bulk_delete', methods=['POST'])
def bulk_delete_participants_alt():
    """Delete multiple participants (alternative route)"""
    participant_ids = request.form.getlist('participant_ids')
    if not participant_ids:
        flash('No participants selected for deletion!', 'warning')
        return redirect(request.referrer or url_for('index'))
    
    try:
        # Get event_id before deletion
        first_participant = Participant.query.get(participant_ids[0])
        event_id = first_participant.event_id if first_participant else None
        
        deleted_count = 0
        for pid in participant_ids:
            participant = Participant.query.get(pid)
            if participant:
                # Delete associated certificates first
                certificates = Certificate.query.filter_by(participant_id=pid).all()
                for cert in certificates:
                    db.session.delete(cert)
                
                db.session.delete(participant)
                deleted_count += 1
        
        db.session.commit()
        flash(f'{deleted_count} participants deleted successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting participants: {str(e)}', 'error')
    
    return redirect(url_for('event_dashboard', event_id=event_id) if event_id else url_for('index'))

@app.route('/participant/<int:participant_id>/preview_ticket')
def preview_ticket(participant_id):
    """Preview ticket email without sending"""
    participant = Participant.query.get_or_404(participant_id)
    return render_template('email/ticket_email.html', 
                         event=participant.event, 
                         participant=participant)

@app.route('/participants/bulk_resend', methods=['POST'])
def bulk_resend_tickets_alt():
    """Resend tickets to multiple participants (alternative route)"""
    participant_ids = request.form.getlist('participant_ids')
    if not participant_ids:
        flash('No participants selected for ticket resend!', 'warning')
        return redirect(request.referrer or url_for('index'))
    
    # Check if mail is configured
    if not app.config.get('MAIL_USERNAME'):
        flash('Email not configured. Please set up email settings in environment variables.', 'error')
        return redirect(request.referrer or url_for('index'))
    
    # Test connection first
    try:
        test_email_connection()
        print("Email connection test passed for bulk resend")
    except Exception as e:
        flash(f'Email connection failed: {str(e)}', 'error')
        return redirect(request.referrer or url_for('index'))
    
    sent_count = 0
    error_count = 0
    event_id = None

    for pid in participant_ids:
        try:
            participant = Participant.query.get(pid)
            if participant:
                if not event_id:
                    event_id = participant.event_id
                
                send_ticket_email(participant, participant.event)
                sent_count += 1
                
        except Exception as e:
            error_count += 1
            print(f"Error sending ticket to participant {pid}: {e}")
    
    if sent_count > 0:
        flash(f'Tickets resent to {sent_count} participants!', 'success')
    if error_count > 0:
        flash(f'Failed to send {error_count} tickets. Please try again.', 'warning')
    
    return redirect(url_for('event_dashboard', event_id=event_id) if event_id else url_for('index'))

@app.route('/participant/<int:participant_id>/edit', methods=['GET', 'POST'])
def edit_participant(participant_id):
    """Edit participant details"""
    participant = Participant.query.get_or_404(participant_id)
    form = EditParticipantForm(obj=participant)
    
    if form.validate_on_submit():
        try:
            # Check if email is being changed and if it already exists for this event
            if form.email.data != participant.email:
                existing = Participant.query.filter_by(
                    event_id=participant.event_id, 
                    email=form.email.data
                ).first()
                if existing:
                    flash(f'Email {form.email.data} already exists for this event!', 'error')
                    return render_template('edit_participant.html', form=form, participant=participant)
            
            # Update participant details
            participant.name = form.name.data
            participant.email = form.email.data
            participant.checked_in = form.checked_in.data
            
            if form.checked_in.data and not participant.checkin_time:
                participant.checkin_time = datetime.now(timezone.utc)
            elif not form.checked_in.data:
                participant.checkin_time = None
            
            db.session.commit()
            flash(f'Participant {participant.name} updated successfully!', 'success')
            return redirect(url_for('event_dashboard', event_id=participant.event_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating participant: {str(e)}', 'error')
    
    return render_template('edit_participant.html', form=form, participant=participant)

@app.route('/participant/<int:participant_id>/checkin', methods=['GET', 'POST'])
def toggle_checkin(participant_id):
    print(f"?? DEBUG: Check-in route called for participant {participant_id} with method {request.method}")
    participant = Participant.query.get_or_404(participant_id)
    
    # If GET request, redirect to dashboard with error message
    if request.method == 'GET':
        print(f"?? DEBUG: GET request detected, redirecting to dashboard")
        flash('Check-in must be done via button click, not direct URL access.', 'warning')
        return redirect(url_for('event_dashboard', event_id=participant.event_id))
    
    # Handle POST request
    participant.checked_in = not participant.checked_in
    participant.checkin_time = datetime.now(timezone.utc) if participant.checked_in else None
    db.session.commit()
    
    status = 'checked in' if participant.checked_in else 'checked out'
    
    # Check if this is a form submission that should redirect
    if request.form.get('redirect') == 'true':
        flash(f'{participant.name} {status}', 'success')
        return redirect(url_for('event_dashboard', event_id=participant.event_id))
    
    # Otherwise return JSON for AJAX calls
    return jsonify({
        'success': True,
        'message': f'{participant.name} {status}',
        'checked_in': participant.checked_in
    })

@app.route('/send_emails/<int:event_id>', methods=['GET', 'POST'])
def send_emails(event_id):
    event = Event.query.get_or_404(event_id)
    participants = Participant.query.filter_by(event_id=event_id).all()
    
    try:
        if not participants:
            flash('No participants found to send emails to!', 'warning')
            return redirect(url_for('event_dashboard', event_id=event_id))
            
        # Check if mail is configured
        if not app.config.get('MAIL_USERNAME'):
            flash('Email not configured. Please set up email settings in environment variables.', 'error')
            return redirect(url_for('event_dashboard', event_id=event_id))
            
        # Test email connection first
        try:
            test_email_connection()
            print("Email connection test passed")
        except Exception as e:
            print(f"Email connection test failed: {str(e)}")
            flash(f'Email connection failed: {str(e)}', 'error')
            return redirect(url_for('event_dashboard', event_id=event_id))
            
        sent_count = 0
        error_count = 0
        
        for participant in participants:
            try:
                send_ticket_email(participant, event)
                sent_count += 1
                print(f"? Email sent to {participant.email}")
            except Exception as e:
                error_count += 1
                print(f"? Error sending email to {participant.email}: {e}")
        
        if sent_count > 0:
            flash(f'Emails sent successfully to {sent_count} participants!', 'success')
        if error_count > 0:
            flash(f'Failed to send {error_count} emails. Check email configuration.', 'warning')
            
    except Exception as e:
        flash(f'Error sending emails: {str(e)}', 'error')
        print(f"Email error: {e}")
    
    return redirect(url_for('event_dashboard', event_id=event_id))

@app.route('/debug/email-config')
def debug_email_config():
    """Debug route to check email configuration."""
    config_info = {
        'MAIL_SERVER': app.config.get('MAIL_SERVER'),
        'MAIL_PORT': app.config.get('MAIL_PORT'),
        'MAIL_USERNAME': app.config.get('MAIL_USERNAME'),
        'MAIL_USE_TLS': app.config.get('MAIL_USE_TLS'),
        'MAIL_USE_SSL': app.config.get('MAIL_USE_SSL'),
        'MAIL_DEFAULT_SENDER': app.config.get('MAIL_DEFAULT_SENDER'),
        'MAIL_PASSWORD_SET': bool(app.config.get('MAIL_PASSWORD')),
        'MAIL_PASSWORD_LENGTH': len(app.config.get('MAIL_PASSWORD', '')),
    }
    return jsonify(config_info)

@app.route('/test_single_email/<int:participant_id>')
def test_single_email(participant_id):
    """Test sending email to a single participant."""
    participant = Participant.query.get_or_404(participant_id)
    event = participant.event
    
    try:
        print(f"Testing single email to {participant.email}")
        
        # Test connection first
        test_email_connection()
        print("Single test: Email connection successful")
        
        # Send test email
        send_ticket_email(participant, event)
        
        flash(f'? Test email sent successfully to {participant.email}!', 'success')
    except Exception as e:
        print(f"Single email test failed: {str(e)}")
        flash(f'? Test email failed: {str(e)}', 'error')
    
    return redirect(url_for('event_dashboard', event_id=event.id))

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

# ===== MISSING ROUTES FOR TEMPLATE COMPATIBILITY =====

@app.route('/participant/<int:participant_id>/delete', methods=['POST'])
def delete_participant(participant_id):
    """Delete a single participant (called by template)."""
    participant = Participant.query.get_or_404(participant_id)
    event_id = participant.event_id
    participant_name = participant.name
    
    try:
        # Delete associated certificates first
        certificates = Certificate.query.filter_by(participant_id=participant_id).all()
        for cert in certificates:
            db.session.delete(cert)
        
        # Delete participant
        db.session.delete(participant)
        db.session.commit()
        
        flash(f'Successfully deleted participant: {participant_name}', 'success')
        print(f"? Deleted participant {participant_name} (ID: {participant_id}) and {len(certificates)} certificates")
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting participant: {str(e)}', 'error')
        print(f"? Error deleting participant {participant_id}: {str(e)}")
    
    return redirect(url_for('event_dashboard', event_id=event_id))

@app.route('/participant/<int:participant_id>/resend_ticket', methods=['POST'])
def resend_ticket(participant_id):
    """Resend ticket to a single participant (called by template)."""
    participant = Participant.query.get_or_404(participant_id)
    event = participant.event
    
    try:
        send_ticket_email(participant, event)
        flash(f'Ticket resent successfully to {participant.email}!', 'success')
        print(f"? Ticket resent to participant {participant.email}")
    except Exception as e:
        print(f"? Failed to resend ticket: {str(e)}")
        flash(f'Failed to resend ticket to {participant.email}: {str(e)}', 'error')
    
    return redirect(url_for('event_dashboard', event_id=event.id))

@app.route('/bulk_resend_tickets', methods=['POST'])
def bulk_resend_tickets():
    """Bulk resend tickets to selected participants."""
    selected_participants = request.form.getlist('selected_participants')
    
    if not selected_participants:
        flash('No participants selected for resending tickets.', 'warning')
        return redirect(request.referrer or url_for('index'))
    
    success_count = 0
    error_count = 0
    
    for participant_id in selected_participants:
        try:
            participant = Participant.query.get(participant_id)
            if participant:
                send_ticket_email(participant, participant.event)
                success_count += 1
        except Exception as e:
            error_count += 1
            print(f"? Failed to resend ticket to participant {participant_id}: {str(e)}")
    
    if success_count > 0:
        flash(f'Successfully resent {success_count} tickets!', 'success')
    if error_count > 0:
        flash(f'Failed to resend {error_count} tickets. Check the logs for details.', 'error')
    
    return redirect(request.referrer or url_for('index'))

@app.route('/bulk_delete_participants', methods=['POST'])
def bulk_delete_participants():
    """Bulk delete selected participants."""
    selected_participants = request.form.getlist('selected_participants')
    
    if not selected_participants:
        flash('No participants selected for deletion.', 'warning')
        return redirect(request.referrer or url_for('index'))
    
    deleted_count = 0
    deleted_names = []
    
    try:
        for participant_id in selected_participants:
            participant = Participant.query.get(participant_id)
            if participant:
                deleted_names.append(participant.name)
                
                # Delete associated certificates first
                certificates = Certificate.query.filter_by(participant_id=participant_id).all()
                for cert in certificates:
                    db.session.delete(cert)
                
                # Delete participant
                db.session.delete(participant)
                deleted_count += 1
        
        db.session.commit()
        
        if deleted_count > 0:
            flash(f'Successfully deleted {deleted_count} participants: {", ".join(deleted_names[:5])}{"..." if len(deleted_names) > 5 else ""}', 'success')
        else:
            flash('No participants were deleted.', 'warning')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting participants: {str(e)}', 'error')
        print(f"? Error in bulk delete: {str(e)}")
    
    return redirect(request.referrer or url_for('index'))

@app.route('/event/<int:event_id>/add_participant', methods=['POST'])
def add_participant(event_id):
    """Add a participant manually (called by template form)."""
    event = Event.query.get_or_404(event_id)
    
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    
    if not name or not email:
        flash('Name and email are required.', 'error')
        return redirect(url_for('event_dashboard', event_id=event_id))
    
    try:
        # Check for duplicate email
        existing = Participant.query.filter_by(event_id=event_id, email=email).first()
        if existing:
            flash(f'A participant with email {email} already exists in this event.', 'error')
            return redirect(url_for('event_dashboard', event_id=event_id))
        
        # Generate ticket number
        ticket_number = event.generate_ticket_number()
        
        # Create new participant
        participant = Participant(
            name=name,
            email=email,
            event_id=event_id,
            ticket_number=ticket_number,
            checked_in=False,
            checkin_time=None
        )
        
        db.session.add(participant)
        db.session.commit()
        
        flash(f'Successfully added participant: {name} with ticket {ticket_number}', 'success')
        print(f"? Added participant {name} ({email}) to event {event.name}")
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding participant: {str(e)}', 'error')
        print(f"? Error adding participant: {str(e)}")
    
    return redirect(url_for('event_dashboard', event_id=event_id))

@app.route('/event/<int:event_id>/send_emails', methods=['POST'])
def send_emails_alt(event_id):
    """Send emails to all participants (alternative route called by template)."""
    return redirect(url_for('send_emails', event_id=event_id))

# Certificate Routes
@app.route('/event/<int:event_id>/certificates')
def certificate_preview_page(event_id):
    """Certificate preview and configuration page"""
    event = Event.query.get_or_404(event_id)
    
    # Get or create certificate configuration
    cert_config = CertificateConfig.query.filter_by(event_id=event_id).first()
    
    # Initialize form with existing data
    form = CertificateConfigForm()
    if cert_config:
        form.certificate_type.data = cert_config.certificate_type
        form.organizer_name.data = cert_config.organizer_name
        form.sponsor_name.data = cert_config.sponsor_name
        form.event_location.data = cert_config.event_location
        form.event_theme.data = cert_config.event_theme
        form.organizer_logo_url.data = cert_config.organizer_logo_url
        form.sponsor_logo_url.data = cert_config.sponsor_logo_url
        form.signature1_name.data = cert_config.signature1_name
        form.signature1_title.data = cert_config.signature1_title
        form.signature1_image_url.data = cert_config.signature1_image_url
        form.signature2_name.data = cert_config.signature2_name
        form.signature2_title.data = cert_config.signature2_title
        form.signature2_image_url.data = cert_config.signature2_image_url
        form.send_to_all_checked_in.data = cert_config.send_to_all_checked_in
    
    # Get participant statistics
    participants = Participant.query.filter_by(event_id=event_id).all()
    total_participants = len(participants)
    checked_in_participants = [p for p in participants if p.checked_in]
    checked_in_count = len(checked_in_participants)
    
    # Certificates already issued
    already_issued = Certificate.query.filter_by(event_id=event_id).count()
    
    # Eligible for certificate (checked in but not yet issued)
    issued_participant_ids = {c.participant_id for c in Certificate.query.filter_by(event_id=event_id).all()}
    eligible_participants = [p for p in checked_in_participants if p.id not in issued_participant_ids]
    eligible_for_certificate = len(eligible_participants)
    
    return render_template('certificate_preview.html',
                         event=event,
                         form=form,
                         total_participants=total_participants,
                         checked_in_count=checked_in_count,
                         eligible_for_certificate=eligible_for_certificate,
                         already_issued=already_issued,
                         eligible_participants=eligible_participants)

@app.route('/event/<int:event_id>/certificates/save', methods=['POST'])
def save_certificate_config(event_id):
    """Save certificate configuration"""
    event = Event.query.get_or_404(event_id)
    form = CertificateConfigForm()
    
    if form.validate_on_submit():
        try:
            # Get or create certificate configuration
            cert_config = CertificateConfig.query.filter_by(event_id=event_id).first()
            if not cert_config:
                cert_config = CertificateConfig(event_id=event_id)
                db.session.add(cert_config)
            
            # Update basic fields
            cert_config.certificate_type = form.certificate_type.data
            cert_config.organizer_name = form.organizer_name.data
            cert_config.sponsor_name = form.sponsor_name.data
            cert_config.event_location = form.event_location.data
            cert_config.event_theme = form.event_theme.data
            cert_config.send_to_all_checked_in = form.send_to_all_checked_in.data
            
            # Handle logo uploads
            if form.organizer_logo_file.data:
                logo_url = storage_manager.save_image(form.organizer_logo_file.data, folder="certificates/logos")
                if logo_url:
                    cert_config.organizer_logo_url = logo_url
            elif form.organizer_logo_url.data:
                cert_config.organizer_logo_url = form.organizer_logo_url.data
            
            if form.sponsor_logo_file.data:
                logo_url = storage_manager.save_image(form.sponsor_logo_file.data, folder="certificates/logos")
                if logo_url:
                    cert_config.sponsor_logo_url = logo_url
            elif form.sponsor_logo_url.data:
                cert_config.sponsor_logo_url = form.sponsor_logo_url.data
            
            # Handle signature uploads
            if form.signature1_file.data:
                sig_url = storage_manager.save_image(form.signature1_file.data, folder="certificates/signatures")
                if sig_url:
                    cert_config.signature1_image_url = sig_url
            elif form.signature1_image_url.data:
                cert_config.signature1_image_url = form.signature1_image_url.data
                
            cert_config.signature1_name = form.signature1_name.data
            cert_config.signature1_title = form.signature1_title.data
            
            if form.signature2_file.data:
                sig_url = storage_manager.save_image(form.signature2_file.data, folder="certificates/signatures")
                if sig_url:
                    cert_config.signature2_image_url = sig_url
            elif form.signature2_image_url.data:
                cert_config.signature2_image_url = form.signature2_image_url.data
                
            cert_config.signature2_name = form.signature2_name.data
            cert_config.signature2_title = form.signature2_title.data
            
            # Update timestamp
            cert_config.updated_at = datetime.now(timezone.utc)
            
            db.session.commit()
            
            flash('Certificate configuration saved successfully!', 'success')
            return jsonify({'status': 'success', 'message': 'Configuration saved successfully!'})
            
        except Exception as e:
            db.session.rollback()
            print(f"Error saving certificate config: {str(e)}")
            return jsonify({'status': 'error', 'message': f'Error: {str(e)}'}), 500

@app.route('/event/<int:event_id>/certificate_assets')
def certificate_assets_manager(event_id):
    """Certificate Assets Management Page"""
    event = Event.query.get_or_404(event_id)
    cert_config = CertificateConfig.query.filter_by(event_id=event_id).first()
    
    if not cert_config:
        cert_config = CertificateConfig(event_id=event_id)
        db.session.add(cert_config)
        db.session.commit()
    
    # Get all uploaded assets for this event
    assets = {
        'organizer_logo': {
            'url': cert_config.organizer_logo_url,
            'name': 'Organizer Logo',
            'type': 'logo'
        },
        'sponsor_logo': {
            'url': cert_config.sponsor_logo_url,
            'name': 'Sponsor Logo', 
            'type': 'logo'
        },
        'signature1': {
            'url': cert_config.signature1_image_url,
            'name': f"Signature 1 - {cert_config.signature1_name or 'First Signatory'}",
            'type': 'signature',
            'signatory_name': cert_config.signature1_name,
            'signatory_title': cert_config.signature1_title
        },
        'signature2': {
            'url': cert_config.signature2_image_url,
            'name': f"Signature 2 - {cert_config.signature2_name or 'Second Signatory'}",
            'type': 'signature', 
            'signatory_name': cert_config.signature2_name,
            'signatory_title': cert_config.signature2_title
        }
    }
    
    return render_template('certificate_assets.html', 
                         event=event, 
                         cert_config=cert_config,
                         assets=assets)

@app.route('/event/<int:event_id>/certificate_assets/upload', methods=['POST'])
def upload_certificate_asset(event_id):
    """Upload new certificate asset"""
    try:
        event = Event.query.get_or_404(event_id)
        cert_config = CertificateConfig.query.filter_by(event_id=event_id).first()
        
        if not cert_config:
            cert_config = CertificateConfig(event_id=event_id)
            db.session.add(cert_config)
            db.session.commit()
        
        asset_type = request.form.get('asset_type')  # organizer_logo, sponsor_logo, signature1, signature2
        uploaded_file = request.files.get('file')
        
        if not uploaded_file or not uploaded_file.filename:
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # Determine folder based on asset type
        if asset_type in ['organizer_logo', 'sponsor_logo']:
            folder = 'certificates/logos'
        elif asset_type in ['signature1', 'signature2']:
            folder = 'certificates/signatures'
        else:
            return jsonify({'success': False, 'error': 'Invalid asset type'})
        
        # Upload to GitHub
        print(f"🔄 Uploading {asset_type} for event {event.name}")
        asset_url = storage_manager.save_image(uploaded_file, folder=folder)
        
        if asset_url:
            # Update certificate config
            if asset_type == 'organizer_logo':
                cert_config.organizer_logo_url = asset_url
            elif asset_type == 'sponsor_logo':
                cert_config.sponsor_logo_url = asset_url
            elif asset_type == 'signature1':
                cert_config.signature1_image_url = asset_url
            elif asset_type == 'signature2':
                cert_config.signature2_image_url = asset_url
            
            cert_config.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            
            print(f"✅ {asset_type} uploaded successfully: {asset_url}")
            return jsonify({
                'success': True, 
                'url': asset_url,
                'asset_type': asset_type,
                'message': f'{asset_type.replace("_", " ").title()} uploaded successfully!'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to upload to GitHub'})
            
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error uploading certificate asset: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/event/<int:event_id>/certificate_assets/delete', methods=['POST'])
def delete_certificate_asset(event_id):
    """Delete certificate asset"""
    try:
        event = Event.query.get_or_404(event_id)
        cert_config = CertificateConfig.query.filter_by(event_id=event_id).first()
        
        if not cert_config:
            return jsonify({'success': False, 'error': 'No certificate configuration found'})
        
        asset_type = request.form.get('asset_type')
        
        # Clear the asset URL from database
        if asset_type == 'organizer_logo':
            old_url = cert_config.organizer_logo_url
            cert_config.organizer_logo_url = None
        elif asset_type == 'sponsor_logo':
            old_url = cert_config.sponsor_logo_url
            cert_config.sponsor_logo_url = None
        elif asset_type == 'signature1':
            old_url = cert_config.signature1_image_url
            cert_config.signature1_image_url = None
        elif asset_type == 'signature2':
            old_url = cert_config.signature2_image_url
            cert_config.signature2_image_url = None
        else:
            return jsonify({'success': False, 'error': 'Invalid asset type'})
        
        cert_config.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        
        # Note: We could implement actual GitHub file deletion here if needed
        # storage_manager.delete_image(old_url)
        
        print(f"🗑️ {asset_type} removed from event {event.name}")
        return jsonify({
            'success': True,
            'asset_type': asset_type,
            'message': f'{asset_type.replace("_", " ").title()} removed successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting certificate asset: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    else:
        errors = []
        for field, field_errors in form.errors.items():
            for error in field_errors:
                errors.append(f"{field}: {error}")
        return jsonify({'status': 'error', 'message': f'Validation errors: {", ".join(errors)}'}), 400

@app.route('/event/<int:event_id>/certificates/preview')
def preview_certificate(event_id):
    """Preview certificate template"""
    event = Event.query.get_or_404(event_id)
    cert_config = CertificateConfig.query.filter_by(event_id=event_id).first()
    
    if not cert_config:
        flash('Please configure the certificate first.', 'warning')
        return redirect(url_for('certificate_preview_page', event_id=event_id))
    
    # Get a sample participant (first checked-in participant or create dummy)
    sample_participant = Participant.query.filter_by(event_id=event_id, checked_in=True).first()
    if not sample_participant:
        sample_participant = Participant(
            name="John Doe",
            email="john.doe@example.com",
            event_id=event_id,
            ticket_number="SAMPLE-001",
            checked_in=True
        )
    
    # Create a sample certificate object
    sample_certificate = Certificate(
        certificate_number=f"CERT-{event.id}-SAMPLE-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        certificate_type=cert_config.certificate_type,
        organizer_name=cert_config.organizer_name,
        sponsor_name=cert_config.sponsor_name,
        event_location=cert_config.event_location,
        event_theme=cert_config.event_theme,
        organizer_logo_url=cert_config.organizer_logo_url,
        sponsor_logo_url=cert_config.sponsor_logo_url,
        signature1_name=cert_config.signature1_name,
        signature1_title=cert_config.signature1_title,
        signature1_image_url=cert_config.signature1_image_url,
        signature2_name=cert_config.signature2_name,
        signature2_title=cert_config.signature2_title,
        signature2_image_url=cert_config.signature2_image_url,
        issued_date=datetime.now(timezone.utc)
    )
    
    return render_template('certificate_professional.html',
                         event=event,
                         participant=sample_participant,
                         certificate=sample_certificate)

@app.route('/participant/<int:participant_id>/certificate/preview')
def preview_single_certificate(participant_id):
    """Preview certificate for a specific participant"""
    participant = Participant.query.get_or_404(participant_id)
    event = participant.event
    cert_config = CertificateConfig.query.filter_by(event_id=event.id).first()
    
    if not cert_config:
        flash('Certificate configuration not found.', 'error')
        return redirect(url_for('certificate_preview_page', event_id=event.id))
    
    # Create certificate object for this participant
    sample_certificate = Certificate(
        certificate_number=f"CERT-{event.id}-{participant.id}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        certificate_type=cert_config.certificate_type,
        organizer_name=cert_config.organizer_name,
        sponsor_name=cert_config.sponsor_name,
        event_location=cert_config.event_location,
        event_theme=cert_config.event_theme,
        organizer_logo_url=cert_config.organizer_logo_url,
        sponsor_logo_url=cert_config.sponsor_logo_url,
        signature1_name=cert_config.signature1_name,
        signature1_title=cert_config.signature1_title,
        signature1_image_url=cert_config.signature1_image_url,
        signature2_name=cert_config.signature2_name,
        signature2_title=cert_config.signature2_title,
        signature2_image_url=cert_config.signature2_image_url,
        issued_date=datetime.now(timezone.utc)
    )
    
    return render_template('certificate_professional.html',
                         event=event,
                         participant=participant,
                         certificate=sample_certificate)

@app.route('/event/<int:event_id>/certificates/generate', methods=['POST'])
def generate_certificates(event_id):
    """Generate and send certificates to eligible participants"""
    event = Event.query.get_or_404(event_id)
    cert_config = CertificateConfig.query.filter_by(event_id=event_id).first()
    
    if not cert_config:
        flash('Please configure the certificate first.', 'error')
        return redirect(url_for('certificate_preview_page', event_id=event_id))
    
    try:
        # Get eligible participants (checked in but no certificate issued)
        participants = Participant.query.filter_by(event_id=event_id, checked_in=True).all()
        issued_participant_ids = {c.participant_id for c in Certificate.query.filter_by(event_id=event_id).all()}
        eligible_participants = [p for p in participants if p.id not in issued_participant_ids]
        
        if not eligible_participants:
            flash('No eligible participants found for certificates.', 'warning')
            return redirect(url_for('certificate_preview_page', event_id=event_id))
        
        success_count = 0
        error_count = 0
        
        for participant in eligible_participants:
            try:
                # Generate certificate
                certificate_number = f"CERT-{event.id}-{participant.id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                
                # Create certificate record
                certificate = Certificate(
                    event_id=event_id,
                    participant_id=participant.id,
                    certificate_number=certificate_number,
                    certificate_type=cert_config.certificate_type,
                    organizer_name=cert_config.organizer_name,
                    sponsor_name=cert_config.sponsor_name,
                    event_location=cert_config.event_location,
                    event_theme=cert_config.event_theme,
                    organizer_logo_url=cert_config.organizer_logo_url,
                    sponsor_logo_url=cert_config.sponsor_logo_url,
                    signature1_name=cert_config.signature1_name,
                    signature1_title=cert_config.signature1_title,
                    signature1_image_url=cert_config.signature1_image_url,
                    signature2_name=cert_config.signature2_name,
                    signature2_title=cert_config.signature2_title,
                    signature2_image_url=cert_config.signature2_image_url,
                    issued_date=datetime.now(timezone.utc)
                )
                
                db.session.add(certificate)
                db.session.commit()
                
                # Send certificate email (with PDF attachment - to be implemented)
                send_certificate_email(participant, event, certificate)
                
                success_count += 1
                print(f"? Certificate generated and sent to {participant.name}")
                
            except Exception as e:
                print(f"? Error generating certificate for {participant.name}: {str(e)}")
                error_count += 1
        
        if success_count > 0:
            flash(f'? Successfully generated and sent {success_count} certificates!', 'success')
        if error_count > 0:
            flash(f'? {error_count} certificates failed to generate.', 'error')
            
    except Exception as e:
        db.session.rollback()
        print(f"Error in certificate generation: {str(e)}")
        flash(f'Error generating certificates: {str(e)}', 'error')
    
    return redirect(url_for('certificate_preview_page', event_id=event_id))

def send_certificate_email(participant, event, certificate):
    """Send certificate email with PDF attachment"""
    try:
        # Create certificate email
        subject = f"Your Certificate - {event.name}"
        
        # Render email template
        email_html = render_template('email/certificate_email.html',
                                   event=event,
                                   participant=participant,
                                   certificate=certificate)
        
        # Create email message
        msg = Message(
            subject=subject,
            sender=app.config['MAIL_USERNAME'],
            recipients=[participant.email],
            html=email_html
        )
        
        # Generate PDF certificate
        try:
            pdf_data = generate_certificate_pdf(participant, event, certificate)
            if pdf_data:
                filename = f"Certificate_{participant.name.replace(' ', '_')}_{event.name.replace(' ', '_')}.pdf"
                msg.attach(filename, "application/pdf", pdf_data)
                print(f"? PDF certificate attached: {filename}")
            else:
                print("?? PDF generation failed, sending email without attachment")
        except Exception as pdf_error:
            print(f"?? PDF generation error: {str(pdf_error)}, sending email without attachment")
        
        print(f"?? Sending certificate email to {participant.email}")
        
        mail.send(msg)
        
        # Update certificate record
        certificate.email_sent = True
        certificate.email_sent_date = datetime.now(timezone.utc)
        db.session.commit()
        
        print(f"? Certificate email sent successfully to {participant.email}")
        
    except Exception as e:
        print(f"? Error sending certificate email to {participant.email}: {str(e)}")
        raise e

def generate_certificate_pdf(participant, event, certificate):
    """Generate PDF certificate using multiple fallback methods"""
    try:
        # Method 1: Try ReportLab (most reliable for serverless)
        try:
            pdf_data = generate_certificate_with_reportlab(participant, event, certificate)
            if pdf_data:
                print(f"✅ PDF generated using ReportLab for {participant.name}")
                return pdf_data
        except ImportError:
            print("⚠️ ReportLab not available")
        except Exception as reportlab_error:
            print(f"⚠️ ReportLab failed: {str(reportlab_error)}")
        
        # Method 2: Try rendering HTML and convert with WeasyPrint
        try:
            certificate_html = render_template('certificate_professional.html',
                                             event=event,
                                             participant=participant,
                                             certificate=certificate)
            
            import weasyprint
            pdf = weasyprint.HTML(string=certificate_html).write_pdf()
            print(f"✅ PDF generated using WeasyPrint for {participant.name}")
            return pdf
        except ImportError:
            print("⚠️ WeasyPrint not available")
        except Exception as weasy_error:
            print(f"⚠️ WeasyPrint failed: {str(weasy_error)}")
            
        # Method 3: Try pdfkit (requires wkhtmltopdf binary)
        try:
            certificate_html = render_template('certificate_professional.html',
                                             event=event,
                                             participant=participant,
                                             certificate=certificate)
            
            options = {
                'page-size': 'A4',
                'orientation': 'Landscape',
                'margin-top': '0.75in',
                'margin-right': '0.75in',
                'margin-bottom': '0.75in',
                'margin-left': '0.75in',
                'encoding': "UTF-8",
                'no-outline': None,
                'enable-local-file-access': None,
                'print-media-type': None,
                'disable-smart-shrinking': None,
            }
            
            pdf_data = pdfkit.from_string(certificate_html, False, options=options)
            print(f"✅ PDF generated using pdfkit for {participant.name}")
            return pdf_data
        except Exception as pdfkit_error:
            print(f"⚠️ pdfkit failed: {str(pdfkit_error)}")
        
        # All methods failed
        print(f"❌ All PDF generation methods failed for {participant.name}")
        return None
            
    except Exception as e:
        print(f"❌ Error generating PDF certificate: {str(e)}")
        return None

def generate_certificate_with_reportlab(participant, event, certificate):
    """Generate certificate PDF using proven ReportLab canvas approach"""
    try:
        from flask import render_template
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import HexColor
        from reportlab.lib.utils import ImageReader
        import io
        import requests
        from PIL import Image
        import os
        
        print(f"🎨 Creating certificate PDF for {participant.name} using proven method")
        
        # Helper function for centered text (ReportLab doesn't have drawCentredText)
        def draw_centered_text(canvas_obj, x, y, text):
            text_width = canvas_obj.stringWidth(text, canvas_obj._fontname, canvas_obj._fontsize)
            canvas_obj.drawString(x - text_width/2, y, text)
        
        # Create PDF with ReportLab in LANDSCAPE orientation
        pdf_buffer = io.BytesIO()
        pagesize = landscape(A4)  # Change to landscape
        pdf_canvas = canvas.Canvas(pdf_buffer, pagesize=pagesize)
        width, height = pagesize  # Get landscape dimensions
        
        # Add certificate content using ReportLab
        # Background and border
        pdf_canvas.setStrokeColor(HexColor('#0078d4'))
        pdf_canvas.setLineWidth(3)
        pdf_canvas.rect(20, 20, width-40, height-40)
        
        # Try to add logos if available (positioned near top border)
        logo_y = height - 125  # MOVED MUCH CLOSER to top border
        logo_width = 160  # Much larger - increased from 120
        logo_height = 120  # Much larger - increased from 90
        try:
            if certificate.organizer_logo_url:
                # Try to fetch and add organizer logo (LEFT side)
                if certificate.organizer_logo_url.startswith('http'):
                    response = requests.get(certificate.organizer_logo_url, timeout=5)
                    if response.status_code == 200:
                        logo_img = ImageReader(io.BytesIO(response.content))
                        pdf_canvas.drawImage(logo_img, 40, logo_y, width=logo_width, height=logo_height, mask='auto', preserveAspectRatio=True)
                else:
                    # Local file - convert relative path to absolute
                    if certificate.organizer_logo_url.startswith('/uploads/'):
                        logo_path = os.path.join(os.getcwd(), certificate.organizer_logo_url[1:])
                    else:
                        logo_path = certificate.organizer_logo_url
                    
                    if os.path.exists(logo_path):
                        logo_img = ImageReader(logo_path)
                        pdf_canvas.drawImage(logo_img, 40, logo_y, width=logo_width, height=logo_height, mask='auto', preserveAspectRatio=True)
            
            if certificate.sponsor_logo_url:
                # Try to fetch and add sponsor logo (RIGHT side)
                if certificate.sponsor_logo_url.startswith('http'):
                    response = requests.get(certificate.sponsor_logo_url, timeout=5)
                    if response.status_code == 200:
                        logo_img = ImageReader(io.BytesIO(response.content))
                        pdf_canvas.drawImage(logo_img, width - logo_width - 40, logo_y, width=logo_width, height=logo_height, mask='auto', preserveAspectRatio=True)
                else:
                    # Local file - convert relative path to absolute
                    if certificate.sponsor_logo_url.startswith('/uploads/'):
                        logo_path = os.path.join(os.getcwd(), certificate.sponsor_logo_url[1:])
                    else:
                        logo_path = certificate.sponsor_logo_url
                    
                    if os.path.exists(logo_path):
                        logo_img = ImageReader(logo_path)
                        pdf_canvas.drawImage(logo_img, width - logo_width - 40, logo_y, width=logo_width, height=logo_height, mask='auto', preserveAspectRatio=True)
        except Exception as logo_error:
            print(f"Could not add logos to PDF: {logo_error}")
        
        # Title
        pdf_canvas.setFont("Helvetica-Bold", 36)
        pdf_canvas.setFillColor(HexColor('#0078d4'))
        draw_centered_text(pdf_canvas, width/2, height-180, "CERTIFICATE")
        
        # Subtitle
        pdf_canvas.setFont("Helvetica", 18)
        pdf_canvas.setFillColor(HexColor('#323130'))
        draw_centered_text(pdf_canvas, width/2, height-210, f"OF {certificate.certificate_type.upper()}")
        
        # "This is to certify that" text
        pdf_canvas.setFont("Helvetica", 14)
        pdf_canvas.setFillColor(HexColor('#605e5c'))
        draw_centered_text(pdf_canvas, width/2, height-260, "This is to certify that")
        
        # Participant name
        pdf_canvas.setFont("Helvetica-Bold", 28)
        pdf_canvas.setFillColor(HexColor('#323130'))
        draw_centered_text(pdf_canvas, width/2, height-300, participant.name)
        
        # Underline for participant name
        pdf_canvas.setStrokeColor(HexColor('#0078d4'))
        pdf_canvas.setLineWidth(2)
        name_width = pdf_canvas.stringWidth(participant.name, "Helvetica-Bold", 28)
        pdf_canvas.line(width/2 - name_width/2, height-310, width/2 + name_width/2, height-310)
        
        # Event details
        pdf_canvas.setFont("Helvetica", 14)
        pdf_canvas.setFillColor(HexColor('#323130'))
        
        # Description text
        action = "participated in"
        if certificate.certificate_type == 'completion':
            action = "completed"
        elif certificate.certificate_type == 'achievement':
            action = "achieved excellence in"
        
        description = f"has successfully {action} the event"
        draw_centered_text(pdf_canvas, width/2, height-350, description)
        
        # Event name
        pdf_canvas.setFont("Helvetica-Bold", 16)
        pdf_canvas.setFillColor(HexColor('#0078d4'))
        draw_centered_text(pdf_canvas, width/2, height-380, f'"{event.name}"')
        
        # Organizer and date info
        pdf_canvas.setFont("Helvetica", 12)
        pdf_canvas.setFillColor(HexColor('#323130'))
        
        organizer = certificate.organizer_name or 'Azure Developer Community Tamilnadu'
        draw_centered_text(pdf_canvas, width/2, height-410, f"organized by {organizer}")
        
        if event.date:
            draw_centered_text(pdf_canvas, width/2, height-430, f"on {event.date.strftime('%B %d, %Y')}")
        
        if certificate.event_location:
            draw_centered_text(pdf_canvas, width/2, height-450, f"at {certificate.event_location}")
        
        # Signature section (moved to bottom)
        signature_y = 120  # Moved down from 200
        
        # Signature lines
        pdf_canvas.setStrokeColor(HexColor('#323130'))
        pdf_canvas.setLineWidth(1)
        pdf_canvas.line(150, signature_y, 300, signature_y)  # Left signature line
        pdf_canvas.line(width-300, signature_y, width-150, signature_y)  # Right signature line
        
        # Try to add signature images
        try:
            if certificate.signature1_image_url:
                if certificate.signature1_image_url.startswith('http'):
                    response = requests.get(certificate.signature1_image_url, timeout=5)
                    if response.status_code == 200:
                        sig_img = ImageReader(io.BytesIO(response.content))
                        pdf_canvas.drawImage(sig_img, 175, signature_y + 10, width=120, height=50, mask='auto')
                else:
                    # Local file - convert relative path to absolute
                    if certificate.signature1_image_url.startswith('/uploads/'):
                        sig_path = os.path.join(os.getcwd(), certificate.signature1_image_url[1:])
                    else:
                        sig_path = certificate.signature1_image_url
                    
                    if os.path.exists(sig_path):
                        sig_img = ImageReader(sig_path)
                        pdf_canvas.drawImage(sig_img, 175, signature_y + 10, width=120, height=50, mask='auto')
            
            if certificate.signature2_image_url:
                if certificate.signature2_image_url.startswith('http'):
                    response = requests.get(certificate.signature2_image_url, timeout=5)
                    if response.status_code == 200:
                        sig_img = ImageReader(io.BytesIO(response.content))
                        pdf_canvas.drawImage(sig_img, width-295, signature_y + 10, width=120, height=50, mask='auto')
                else:
                    # Local file - convert relative path to absolute
                    if certificate.signature2_image_url.startswith('/uploads/'):
                        sig_path = os.path.join(os.getcwd(), certificate.signature2_image_url[1:])
                    else:
                        sig_path = certificate.signature2_image_url
                    
                    if os.path.exists(sig_path):
                        sig_img = ImageReader(sig_path)
                        pdf_canvas.drawImage(sig_img, width-295, signature_y + 10, width=120, height=50, mask='auto')
        except Exception as sig_error:
            print(f"Could not add signatures to PDF: {sig_error}")
        
        # Signature names
        signature1_name = certificate.signature1_name or 'Authorized Signatory'
        signature2_name = certificate.signature2_name or 'Event Organizer'
        
        pdf_canvas.setFont("Helvetica-Bold", 11)
        pdf_canvas.setFillColor(HexColor('#323130'))
        draw_centered_text(pdf_canvas, 225, signature_y - 20, signature1_name)
        draw_centered_text(pdf_canvas, width-225, signature_y - 20, signature2_name)
        
        # Signature titles
        signature1_title = certificate.signature1_title or 'Microsoft MVP'
        signature2_title = certificate.signature2_title or 'Microsoft MVP'
        
        pdf_canvas.setFont("Helvetica", 9)
        pdf_canvas.setFillColor(HexColor('#605e5c'))
        draw_centered_text(pdf_canvas, 225, signature_y - 35, signature1_title)
        draw_centered_text(pdf_canvas, width-225, signature_y - 35, signature2_title)
        
        # Footer with certificate details (moved down)
        pdf_canvas.setFont("Helvetica-Bold", 10)
        pdf_canvas.setFillColor(HexColor('#0078d4'))
        pdf_canvas.drawString(50, 50, f"Certificate No: {certificate.certificate_number}")
        pdf_canvas.drawString(width-250, 50, f"Issued: {certificate.issued_date.strftime('%B %d, %Y')}")
        
        # Corner accents
        pdf_canvas.setStrokeColor(HexColor('#0078d4'))
        pdf_canvas.setLineWidth(4)
        # Top left
        pdf_canvas.line(35, height-35, 85, height-35)
        pdf_canvas.line(35, height-35, 35, height-85)
        # Top right
        pdf_canvas.line(width-85, height-35, width-35, height-35)
        pdf_canvas.line(width-35, height-35, width-35, height-85)
        # Bottom left
        pdf_canvas.line(35, 85, 85, 85)
        pdf_canvas.line(35, 85, 35, 35)
        # Bottom right
        pdf_canvas.line(width-85, 85, width-35, 85)
        pdf_canvas.line(width-35, 85, width-35, 35)
        
        # Save the PDF
        pdf_canvas.save()
        
        pdf_buffer.seek(0)
        pdf_data = pdf_buffer.getvalue()
        pdf_size = len(pdf_data)
        
        print(f"✅ Certificate PDF generated successfully, size: {pdf_size} bytes")
        
        return pdf_data
        
    except Exception as e:
        print(f"❌ Certificate PDF generation failed: {e}")
        return None
        
    except Exception as e:
        print(f"❌ ReportLab PDF generation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

# Initialize database on startup
with app.app_context():
    try:
        # Only create tables if they don't exist (preserve existing data)
        db.create_all()
        print("🗃️ Database tables created/verified (existing data preserved)")
    except Exception as e:
        print(f"Warning: Could not create database tables: {e}")

# Export for Vercel
application = app

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_ENV') == 'development')
