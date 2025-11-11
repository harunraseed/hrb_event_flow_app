import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, Response
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, DateField, TimeField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Length, Optional, URL, Email
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import csv
import io
import base64
from uuid import uuid4
from utils.storage import storage_manager

load_dotenv()

# CRITICAL: Specify static and template folders
app = Flask(__name__,
            static_folder='static',
            static_url_path='/static',
            template_folder='templates')

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Database configuration - Force SQLite for local development
# Check if we're running locally or in production
if os.getenv('FLASK_ENV') == 'production' and os.getenv('DATABASE_URL'):
    # Only use PostgreSQL in production
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    print("Using PostgreSQL database for production")
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
        print(f"✅ Email sent successfully to {participant.email}")
        
    except Exception as e:
        print(f"❌ Failed to send email to {participant.email}: {str(e)}")
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    participants = db.relationship('Participant', backref='event', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Event {self.name}>'
    
    def generate_ticket_number(self):
        """Generate ticket number in format: ALIAS-EVENTDATE-001"""
        # Use alias_name if available, otherwise use first 3 letters of event name
        if self.alias_name:
            prefix = self.alias_name.upper()
        else:
            prefix = self.name.replace(' ', '')[:3].upper()
        
        # Format date as DDMMYYYY 
        date_str = self.date.strftime('%d%m%Y')
        
        # Get the next sequential number for this event
        existing_count = Participant.query.filter_by(event_id=self.id).count()
        next_number = existing_count + 1
        
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
def logo_url_filter(logo_url):
    """Return logo URL if it exists"""
    if logo_url:
        return logo_url
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
            # Handle logo upload using storage manager
            logo_url = None
            if form.logo.data:
                try:
                    logo_url = storage_manager.save_image(form.logo.data, folder="logos")
                    if not logo_url:
                        flash('Error uploading logo. Event created without logo.', 'warning')
                except Exception as e:
                    flash(f'Error processing logo: {str(e)}', 'warning')
                    logo_url = None
            
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
                participant.checkin_time = datetime.utcnow()
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
    print(f"🔍 DEBUG: Check-in route called for participant {participant_id} with method {request.method}")
    participant = Participant.query.get_or_404(participant_id)
    
    # If GET request, redirect to dashboard with error message
    if request.method == 'GET':
        print(f"🔍 DEBUG: GET request detected, redirecting to dashboard")
        flash('Check-in must be done via button click, not direct URL access.', 'warning')
        return redirect(url_for('event_dashboard', event_id=participant.event_id))
    
    # Handle POST request
    participant.checked_in = not participant.checked_in
    participant.checkin_time = datetime.utcnow() if participant.checked_in else None
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
                print(f"✅ Email sent to {participant.email}")
            except Exception as e:
                error_count += 1
                print(f"❌ Error sending email to {participant.email}: {e}")
        
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
        
        flash(f'✅ Test email sent successfully to {participant.email}!', 'success')
    except Exception as e:
        print(f"Single email test failed: {str(e)}")
        flash(f'❌ Test email failed: {str(e)}', 'error')
    
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
        # Delete participant
        db.session.delete(participant)
        db.session.commit()
        
        flash(f'Successfully deleted participant: {participant_name}', 'success')
        print(f"✓ Deleted participant {participant_name} (ID: {participant_id})")
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting participant: {str(e)}', 'error')
        print(f"❌ Error deleting participant {participant_id}: {str(e)}")
    
    return redirect(url_for('event_dashboard', event_id=event_id))

@app.route('/participant/<int:participant_id>/resend_ticket', methods=['POST'])
def resend_ticket(participant_id):
    """Resend ticket to a single participant (called by template)."""
    participant = Participant.query.get_or_404(participant_id)
    event = participant.event
    
    try:
        send_ticket_email(participant, event)
        flash(f'Ticket resent successfully to {participant.email}!', 'success')
        print(f"✓ Ticket resent to participant {participant.email}")
    except Exception as e:
        print(f"❌ Failed to resend ticket: {str(e)}")
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
            print(f"❌ Failed to resend ticket to participant {participant_id}: {str(e)}")
    
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
        print(f"❌ Error in bulk delete: {str(e)}")
    
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
        print(f"✓ Added participant {name} ({email}) to event {event.name}")
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding participant: {str(e)}', 'error')
        print(f"❌ Error adding participant: {str(e)}")
    
    return redirect(url_for('event_dashboard', event_id=event_id))

@app.route('/event/<int:event_id>/send_emails', methods=['POST'])
def send_emails_alt(event_id):
    """Send emails to all participants (alternative route called by template)."""
    return redirect(url_for('send_emails', event_id=event_id))

# Initialize database on startup
with app.app_context():
    try:
        # Only create tables if they don't exist (preserve existing data)
        db.create_all()
        print("✓ Database tables created/verified (existing data preserved)")
    except Exception as e:
        print(f"Warning: Could not create database tables: {e}")

# Export for Vercel
application = app

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_ENV') == 'development')