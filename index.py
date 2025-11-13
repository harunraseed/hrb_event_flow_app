import os
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, Response
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, DateField, TimeField, SubmitField, BooleanField, SelectField, IntegerField, PasswordField
from wtforms.validators import DataRequired, Length, Optional, URL, Email, NumberRange, EqualTo
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import csv
import io
import base64
from uuid import uuid4
from utils.storage import StorageManager
from utils.quiz_performance import (
    QuizPerformanceManager, QuizStatsCollector, QuizQueryOptimizer,
    prevent_double_submission, rate_limit_quiz_joins
)
import tempfile
import pdfkit
import qrcode
from io import BytesIO

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
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = None  # No time limit for development

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

# Initialize authentication
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# Initialize password hashing
bcrypt = Bcrypt(app)

# Initialize performance manager for high-concurrency quiz support
quiz_performance = QuizPerformanceManager()
quiz_performance.init_app(app)
app.extensions['quiz_performance'] = quiz_performance

# Initialize quiz stats collector
quiz_stats = QuizStatsCollector(quiz_performance.redis_client)

# Enable CSRF protection
csrf = CSRFProtect(app)

# CSRF error handler
@app.errorhandler(400)
def csrf_error(e):
    print(f"CSRF Error: {e}")
    if 'csrf' in str(e).lower():
        return jsonify({'error': 'CSRF token missing or invalid', 'details': str(e)}), 400
    return str(e), 400

# Test route for CSRF token debugging
@app.route('/test-csrf', methods=['GET', 'POST'])
def test_csrf():
    if request.method == 'POST':
        return jsonify({'success': True, 'message': 'CSRF test successful'})
    return f'''
    <html>
    <head><meta name="csrf-token" content="{{ csrf_token() }}"></head>
    <body>
        <h1>CSRF Test</h1>
        <p>CSRF Token: <span id="token-display">{{ csrf_token() }}</span></p>
        <button onclick="testCsrf()">Test CSRF</button>
        <script>
        function testCsrf() {{
            const csrfToken = document.querySelector('meta[name="csrf-token"]');
            console.log('CSRF meta tag found:', csrfToken ? 'Yes' : 'No');
            if (csrfToken) {{
                console.log('CSRF token:', csrfToken.getAttribute('content'));
                fetch('/test-csrf', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
                    body: `csrf_token=${{encodeURIComponent(csrfToken.getAttribute('content'))}}`
                }})
                .then(response => response.json())
                .then(data => alert('Success: ' + data.message))
                .catch(error => alert('Error: ' + error));
            }} else {{
                alert('CSRF token meta tag not found!');
            }}
        }}
        </script>
    </body>
    </html>
    '''

# Make CSRF token available in all templates
@app.context_processor
def inject_csrf_token():
    from flask_wtf.csrf import generate_csrf
    return dict(csrf_token=generate_csrf)

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
        
        # Mark email as sent
        participant.email_sent = True
        participant.email_sent_date = datetime.now(timezone.utc)
        db.session.commit()
        
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

# Quiz Forms
class QuizConfigForm(FlaskForm):
    title = StringField('Quiz Title', validators=[DataRequired(), Length(min=1, max=200)], default='Event Quiz')
    description = TextAreaField('Quiz Description', validators=[Optional()])
    time_per_question = IntegerField('Time Per Question (seconds)', validators=[DataRequired(), NumberRange(min=5, max=300)], default=30)
    total_time_limit = IntegerField('Total Time Limit (seconds - optional)', validators=[Optional(), NumberRange(min=60)])
    participant_limit = IntegerField('Maximum Participants', validators=[DataRequired(), NumberRange(min=1, max=1000)], default=100)
    is_active = BooleanField('Quiz is Active', default=False)
    show_leaderboard = BooleanField('Show Leaderboard', default=True)
    submit = SubmitField('Save Quiz Configuration')

class QuizQuestionForm(FlaskForm):
    question_text = TextAreaField('Question Text', validators=[DataRequired(), Length(min=1, max=1000)])
    option_a = StringField('Option A', validators=[DataRequired(), Length(min=1, max=500)])
    option_b = StringField('Option B', validators=[DataRequired(), Length(min=1, max=500)])
    option_c = StringField('Option C', validators=[DataRequired(), Length(min=1, max=500)])
    option_d = StringField('Option D', validators=[DataRequired(), Length(min=1, max=500)])
    correct_answer = SelectField('Correct Answer', 
                                choices=[('A', 'Option A'), ('B', 'Option B'), ('C', 'Option C'), ('D', 'Option D')],
                                validators=[DataRequired()])
    points = IntegerField('Points', validators=[Optional(), NumberRange(min=1, max=10)], default=1)
    time_limit = IntegerField('Time Limit (seconds - override default)', validators=[Optional(), NumberRange(min=5, max=300)])
    submit = SubmitField('Add Question')

class QuizUploadForm(FlaskForm):
    csv_file = FileField('Upload Questions CSV', 
                        validators=[DataRequired(), FileAllowed(['csv'], 'CSV files only!')],
                        render_kw={"accept": ".csv"})
    submit = SubmitField('Upload Questions')

# Authentication Forms
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')

class CreateUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', 
                                   validators=[DataRequired(), EqualTo('password')])
    role = SelectField('Role', 
                      choices=[('member', 'Member'), ('admin', 'Admin')],
                      validators=[DataRequired()])
    submit = SubmitField('Create User')

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm New Password', 
                                   validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('Change Password')

class ApprovalActionForm(FlaskForm):
    action_id = IntegerField('Action ID', validators=[DataRequired()])
    approval_notes = TextAreaField('Approval Notes', validators=[Optional()])
    approve = SubmitField('Approve')
    reject = SubmitField('Reject')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Send Reset Link')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', 
                                   validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Reset Password')

class SimpleActionForm(FlaskForm):
    """Simple form for actions that only need CSRF protection"""
    submit = SubmitField('Submit')

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
    
    # Email tracking
    email_sent = db.Column(db.Boolean, default=False)
    email_sent_date = db.Column(db.DateTime)
    
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

# Quiz Models
class Quiz(db.Model):
    __tablename__ = 'quizzes'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False, unique=True)
    
    # Quiz configuration
    title = db.Column(db.String(200), nullable=False, default='Event Quiz')
    description = db.Column(db.Text)
    time_per_question = db.Column(db.Integer, default=30)  # seconds per question
    total_time_limit = db.Column(db.Integer)  # total quiz time in seconds (optional)
    participant_limit = db.Column(db.Integer, default=100)  # maximum participants allowed
    is_active = db.Column(db.Boolean, default=False)
    show_leaderboard = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    quiz_start_time = db.Column(db.DateTime)  # When quiz actually starts
    quiz_end_time = db.Column(db.DateTime)    # When quiz ends
    
    # Relationships
    event = db.relationship('Event', backref=db.backref('quiz', uselist=False))
    questions = db.relationship('QuizQuestion', backref='quiz', lazy=True, cascade='all, delete-orphan')
    attempts = db.relationship('QuizAttempt', backref='quiz', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Quiz {self.title} for {self.event.name}>'
    
    @property
    def total_questions(self):
        return len(self.questions)
    
    @property
    def current_participants(self):
        """Get current number of participants who have joined the quiz"""
        return len(self.attempts)
    
    @property
    def is_full(self):
        """Check if quiz has reached participant limit"""
        return self.current_participants >= self.participant_limit
    
    @property
    def available_spots(self):
        """Get number of available spots remaining"""
        return max(0, self.participant_limit - self.current_participants)
    
    @property
    def is_started(self):
        return self.quiz_start_time is not None
    
    @property
    def is_ended(self):
        return self.quiz_end_time is not None
    
    @property
    def leaderboard_data(self):
        """Get top participants with scores - improved sorting"""
        from sqlalchemy import desc
        
        # Get all attempts with participant info, ordered properly
        attempts = QuizAttempt.query.filter_by(quiz_id=self.id, is_completed=True)\
            .join(Participant)\
            .order_by(desc(QuizAttempt.score), QuizAttempt.total_time_taken.asc(), QuizAttempt.completed_at.asc())\
            .all()
        
        return attempts[:50]  # Top 50 for full leaderboard
    
    @property
    def live_leaderboard_data(self):
        """Get live leaderboard including in-progress attempts"""
        from sqlalchemy import desc
        
        # Get all attempts (completed and in-progress) with participant info
        attempts = QuizAttempt.query.filter_by(quiz_id=self.id)\
            .join(Participant)\
            .order_by(desc(QuizAttempt.score), QuizAttempt.current_question.desc(), QuizAttempt.total_time_taken.asc())\
            .all()
        
        return attempts[:50]  # Top 50 for game master view

class QuizQuestion(db.Model):
    __tablename__ = 'quiz_questions'
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    
    # Question details
    question_text = db.Column(db.Text, nullable=False)
    question_order = db.Column(db.Integer, nullable=False)
    
    # Options (stored as JSON or separate fields)
    option_a = db.Column(db.String(500))
    option_b = db.Column(db.String(500))
    option_c = db.Column(db.String(500))
    option_d = db.Column(db.String(500))
    
    # Correct answer (A, B, C, or D)
    correct_answer = db.Column(db.String(1), nullable=False)
    
    # Additional settings
    points = db.Column(db.Integer, default=1)
    time_limit = db.Column(db.Integer)  # Override quiz default time per question
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    answers = db.relationship('QuizAnswer', backref='question', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<QuizQuestion {self.question_order}: {self.question_text[:50]}...>'
    
    @property
    def options(self):
        """Return options as a dictionary"""
        return {
            'A': self.option_a,
            'B': self.option_b,
            'C': self.option_c,
            'D': self.option_d
        }
    
    @property
    def effective_time_limit(self):
        """Get time limit for this question (use question-specific or quiz default)"""
        return self.time_limit or self.quiz.time_per_question

class QuizAttempt(db.Model):
    __tablename__ = 'quiz_attempts'
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    participant_id = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False)
    
    # Attempt details
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime)
    current_question = db.Column(db.Integer, default=1)
    score = db.Column(db.Integer, default=0)
    is_completed = db.Column(db.Boolean, default=False)
    
    # Time tracking
    total_time_taken = db.Column(db.Integer, default=0)  # in seconds
    
    # Relationships
    participant = db.relationship('Participant', backref='quiz_attempts')
    answers = db.relationship('QuizAnswer', backref='attempt', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<QuizAttempt by {self.participant.name} for {self.quiz.title}>'
    
    @property
    def accuracy_percentage(self):
        """Calculate accuracy percentage"""
        if not self.answers:
            return 0
        correct_answers = sum(1 for answer in self.answers if answer.is_correct)
        return round((correct_answers / len(self.answers)) * 100, 2)
    
    @property
    def rank_position(self):
        """Get rank position in leaderboard"""
        leaderboard = self.quiz.leaderboard_data
        for i, attempt in enumerate(leaderboard):
            if attempt.id == self.id:
                return i + 1
        return None

class QuizAnswer(db.Model):
    __tablename__ = 'quiz_answers'
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('quiz_attempts.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('quiz_questions.id'), nullable=False)
    
    # Answer details
    selected_answer = db.Column(db.String(1))  # A, B, C, or D
    is_correct = db.Column(db.Boolean, default=False)
    time_taken = db.Column(db.Integer)  # seconds taken to answer
    answered_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f'<QuizAnswer {self.selected_answer} for Question {self.question.question_order}>'

# Authentication Models
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    
    # Role management
    role = db.Column(db.String(20), default='member', nullable=False)  # superadmin, admin, member
    
    # Account status
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    last_login = db.Column(db.DateTime)
    
    # Password reset tokens
    reset_token = db.Column(db.String(100))
    reset_token_expires = db.Column(db.DateTime)
    
    # Relationships
    created_by = db.relationship('User', remote_side=[id], backref='created_users')
    pending_actions = db.relationship('PendingAction', foreign_keys='PendingAction.admin_user_id', backref='admin_user')
    approved_actions = db.relationship('PendingAction', foreign_keys='PendingAction.approved_by_id', backref='approver')
    
    def __repr__(self):
        return f'<User {self.username} ({self.role})>'
    
    # Flask-Login integration
    def is_authenticated(self):
        return True
    
    def is_anonymous(self):
        return False
    
    def get_id(self):
        return str(self.id)
    
    # Role checking methods
    def is_superadmin(self):
        return self.role == 'superadmin'
    
    def is_admin(self):
        return self.role in ['admin', 'superadmin']
    
    def is_member(self):
        return self.role == 'member'
    
    def can_manage_users(self):
        return self.role == 'superadmin'
    
    def can_approve_actions(self):
        return self.role == 'superadmin'
    
    def needs_approval_for_action(self, action_type):
        """Check if admin needs approval for specific action"""
        if self.is_superadmin():
            return False
        
        # Actions that require approval for admin users
        approval_required_actions = [
            'delete_event', 'delete_participant', 'delete_quiz', 
            'delete_certificate', 'bulk_delete', 'critical_config_change'
        ]
        
        return action_type in approval_required_actions
    
    def generate_reset_token(self):
        """Generate a password reset token"""
        import secrets
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        db.session.commit()
        return self.reset_token
    
    def verify_reset_token(self, token):
        """Verify if the reset token is valid"""
        if not self.reset_token or not self.reset_token_expires:
            return False
        
        if self.reset_token != token:
            return False
            
        if datetime.now(timezone.utc) > self.reset_token_expires:
            # Token expired, clear it
            self.reset_token = None
            self.reset_token_expires = None
            db.session.commit()
            return False
            
        return True
    
    def clear_reset_token(self):
        """Clear the password reset token"""
        self.reset_token = None
        self.reset_token_expires = None
        db.session.commit()

class PendingAction(db.Model):
    __tablename__ = 'pending_actions'
    id = db.Column(db.Integer, primary_key=True)
    
    # Action details
    action_type = db.Column(db.String(50), nullable=False)  # delete_event, delete_participant, etc.
    action_data = db.Column(db.Text)  # JSON data about the action
    reason = db.Column(db.Text)  # Reason provided by admin
    
    # User management
    admin_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Approval status
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending, approved, rejected
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    approval_notes = db.Column(db.Text)
    
    # Timestamps
    requested_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime)  # Optional expiration for actions
    
    def __repr__(self):
        return f'<PendingAction {self.action_type} by {self.admin_user.username}>'
    
    @property
    def is_expired(self):
        if self.expires_at:
            return datetime.now(timezone.utc) > self.expires_at
        return False
    
    def approve(self, superadmin_user, notes=None):
        """Approve the pending action"""
        self.status = 'approved'
        self.approved_by_id = superadmin_user.id
        self.approved_at = datetime.now(timezone.utc)
        self.approval_notes = notes
        db.session.commit()
    
    def reject(self, superadmin_user, notes=None):
        """Reject the pending action"""
        self.status = 'rejected'
        self.approved_by_id = superadmin_user.id
        self.approved_at = datetime.now(timezone.utc)
        self.approval_notes = notes
        db.session.commit()

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Password management methods for User model
def set_password(self, password):
    """Hash and set password"""
    self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

def check_password(self, password):
    """Check if provided password matches hash"""
    return bcrypt.check_password_hash(self.password_hash, password)

# Add methods to User class
User.set_password = set_password
User.check_password = check_password

# Authorization decorators
from functools import wraps

def require_login(f):
    """Decorator to require user login"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

def require_admin(f):
    """Decorator to require admin or superadmin role"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin():
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def require_superadmin(f):
    """Decorator to require superadmin role"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_superadmin():
            flash('Access denied. Super admin privileges required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def require_approval_for_action(action_type):
    """Decorator to check if action requires approval"""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.needs_approval_for_action(action_type):
                # Create pending action instead of executing directly
                return handle_pending_action(action_type, request, *args, **kwargs)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def handle_pending_action(action_type, request_obj, *args, **kwargs):
    """Handle creation of pending action for admin approval"""
    import json
    
    # Extract action data from request
    action_data = {
        'args': args,
        'kwargs': kwargs,
        'form_data': dict(request_obj.form) if request_obj.form else None,
        'method': request_obj.method,
        'endpoint': request_obj.endpoint
    }
    
    # Create pending action
    pending_action = PendingAction(
        action_type=action_type,
        action_data=json.dumps(action_data),
        admin_user_id=current_user.id,
        reason=request_obj.form.get('approval_reason', '') if request_obj.form else ''
    )
    
    db.session.add(pending_action)
    db.session.commit()
    
    flash(f'Your {action_type} request has been submitted for approval. A super admin will review it shortly.', 'info')
    return redirect(url_for('pending_actions_list'))

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

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        
        if user and user.check_password(form.password.data) and user.is_active:
            login_user(user, remember=form.remember_me.data)
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            
            flash(f'Welcome back, {user.username}!', 'success')
            
            # Redirect to next page or admin dashboard
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('auth/login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))
    
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.is_active:
            # Generate reset token
            token = user.generate_reset_token()
            
            # In a real application, you would send an email here
            # For now, we'll just flash the reset URL for development
            reset_url = url_for('reset_password', token=token, _external=True)
            flash(f'Password reset link (for development): {reset_url}', 'info')
            flash('If an account with this email exists, a reset link has been sent.', 'success')
            
            # TODO: Send email with reset link
            # send_password_reset_email(user.email, reset_url)
            
        else:
            # Always show success message to prevent email enumeration
            flash('If an account with this email exists, a reset link has been sent.', 'success')
        
        return redirect(url_for('login'))
    
    return render_template('auth/forgot_password.html', form=form)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))
    
    # Find user by reset token
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.verify_reset_token(token):
        flash('Invalid or expired reset token.', 'error')
        return redirect(url_for('forgot_password'))
    
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.clear_reset_token()
        flash('Your password has been reset successfully. You can now login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('auth/reset_password.html', form=form)

@app.route('/admin/dashboard')
@require_admin
def admin_dashboard():
    """Main admin dashboard with system overview"""
    # Get system statistics
    stats = {
        'total_events': Event.query.count(),
        'total_participants': Participant.query.count(),
        'total_certificates': Certificate.query.count(),
        'pending_actions': PendingAction.query.filter_by(status='pending').count(),
        'total_users': User.query.count(),
        'recent_events': Event.query.order_by(Event.created_at.desc()).limit(5).all()
    }
    
    # Get pending actions for superadmin
    pending_actions = []
    if current_user.is_superadmin():
        pending_actions = PendingAction.query.filter_by(status='pending').order_by(PendingAction.requested_at.desc()).all()
    
    return render_template('auth/admin_dashboard.html', stats=stats, pending_actions=pending_actions)

# User Management Routes (Super Admin only)
@app.route('/admin/users')
@require_superadmin
def manage_users():
    """List and manage all users"""
    users = User.query.order_by(User.created_at.desc()).all()
    action_form = SimpleActionForm()
    return render_template('auth/manage_users.html', users=users, action_form=action_form)

@app.route('/admin/users/create', methods=['GET', 'POST'])
@require_superadmin
def create_user():
    """Create new user"""
    form = CreateUserForm()
    
    if form.validate_on_submit():
        # Check if user already exists
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already exists.', 'error')
            return render_template('auth/create_user.html', form=form)
        
        if User.query.filter_by(email=form.email.data).first():
            flash('Email already exists.', 'error')
            return render_template('auth/create_user.html', form=form)
        
        # Create new user
        user = User(
            username=form.username.data,
            email=form.email.data,
            role=form.role.data,
            created_by_id=current_user.id
        )
        user.set_password(form.password.data)
        
        db.session.add(user)
        db.session.commit()
        
        flash(f'User {user.username} created successfully!', 'success')
        return redirect(url_for('manage_users'))
    
    return render_template('auth/create_user.html', form=form)

@app.route('/admin/users/<int:user_id>/toggle_status', methods=['POST'])
@require_superadmin
def toggle_user_status(user_id):
    """Toggle user active status"""
    user = User.query.get_or_404(user_id)
    
    if user.is_superadmin():
        flash('Cannot deactivate super admin users.', 'error')
    else:
        user.is_active = not user.is_active
        db.session.commit()
        status = 'activated' if user.is_active else 'deactivated'
        flash(f'User {user.username} has been {status}.', 'success')
    
    return redirect(url_for('manage_users'))

# Approval System Routes
@app.route('/admin/pending-actions')
@require_superadmin
def pending_actions_list():
    """List all pending actions for approval"""
    pending_actions = PendingAction.query.filter_by(status='pending').order_by(PendingAction.requested_at.desc()).all()
    action_form = SimpleActionForm()
    return render_template('auth/pending_actions.html', pending_actions=pending_actions, action_form=action_form)

@app.route('/admin/pending-actions/<int:action_id>/approve', methods=['POST'])
@require_superadmin
def approve_action(action_id):
    """Approve a pending action"""
    action = PendingAction.query.get_or_404(action_id)
    notes = request.form.get('approval_notes', '')
    
    action.approve(current_user, notes)
    
    # Execute the approved action
    try:
        execute_approved_action(action)
        flash(f'Action {action.action_type} approved and executed successfully!', 'success')
    except Exception as e:
        flash(f'Action approved but execution failed: {str(e)}', 'error')
    
    return redirect(url_for('pending_actions_list'))

@app.route('/admin/pending-actions/<int:action_id>/reject', methods=['POST'])
@require_superadmin
def reject_action(action_id):
    """Reject a pending action"""
    action = PendingAction.query.get_or_404(action_id)
    notes = request.form.get('approval_notes', '')
    
    action.reject(current_user, notes)
    flash(f'Action {action.action_type} rejected.', 'info')
    
    return redirect(url_for('pending_actions_list'))

def execute_approved_action(action):
    """Execute an approved action"""
    import json
    
    action_data = json.loads(action.action_data)
    action_type = action.action_type
    
    # Map action types to execution functions
    # This is a simplified implementation - you'd expand this based on actual needs
    if action_type == 'delete_event':
        event_id = action_data.get('event_id')
        if event_id:
            event = Event.query.get(event_id)
            if event:
                db.session.delete(event)
                db.session.commit()
    elif action_type == 'delete_participant':
        participant_id = action_data.get('participant_id')
        if participant_id:
            participant = Participant.query.get(participant_id)
            if participant:
                db.session.delete(participant)
                db.session.commit()
    # Add more action types as needed

# Change Password Route
@app.route('/admin/change-password', methods=['GET', 'POST'])
@require_login
def change_password():
    """Change user password"""
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        if current_user.check_password(form.current_password.data):
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Current password is incorrect.', 'error')
    
    return render_template('auth/change_password.html', form=form)

@app.route('/')
@require_login
def index():
    try:
        events = Event.query.order_by(Event.date.desc()).all()
    except Exception as e:
        print(f"Error fetching events: {e}")
        events = []
    return render_template('index.html', events=events)

@app.route('/create_event', methods=['GET', 'POST'])
@require_admin
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
@require_admin
def event_created_success(event_id):
    """Success page after creating an event"""
    event = Event.query.get_or_404(event_id)
    return render_template('event_created_success.html', event=event)

@app.route('/upload_participants/<int:event_id>', methods=['GET', 'POST'])
@require_admin
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
@require_admin
def event_dashboard(event_id):
    event = Event.query.get_or_404(event_id)
    participants = Participant.query.filter_by(event_id=event_id).all()
    
    # Calculate email sent count
    emails_sent = sum(1 for p in participants if p.email_sent)
    
    # Calculate certificate issued count
    certificates_issued = Certificate.query.filter_by(event_id=event_id).count()
    
    stats = {
        'total': len(participants),
        'checked_in': sum(1 for p in participants if p.checked_in),
        'pending': sum(1 for p in participants if not p.checked_in),
        'emails_sent': emails_sent,
        'certificates_issued': certificates_issued
    }
    
    return render_template('event_dashboard.html', event=event, participants=participants, stats=stats)

@app.route('/event/<int:event_id>/delete', methods=['POST'])
@require_approval_for_action('delete_event')
def delete_event(event_id):
    """Delete an event and all associated data"""
    try:
        event = Event.query.get_or_404(event_id)
        event_name = event.name  # Store name before deletion
        
        # Get all participants for this event
        participants = Participant.query.filter_by(event_id=event_id).all()
        
        # Delete associated data in correct order (due to foreign key constraints)
        
        # 1. Delete quiz answers first
        for participant in participants:
            quiz_attempts = QuizAttempt.query.filter_by(participant_id=participant.id).all()
            for attempt in quiz_attempts:
                QuizAnswer.query.filter_by(attempt_id=attempt.id).delete()
                db.session.delete(attempt)
        
        # 2. Delete quiz questions and quizzes
        quizzes = Quiz.query.filter_by(event_id=event_id).all()
        for quiz in quizzes:
            QuizQuestion.query.filter_by(quiz_id=quiz.id).delete()
            db.session.delete(quiz)
        
        # 3. Delete certificates
        for participant in participants:
            Certificate.query.filter_by(participant_id=participant.id).delete()
        
        # 4. Delete participants
        for participant in participants:
            db.session.delete(participant)
        
        # 5. Finally delete the event
        db.session.delete(event)
        
        db.session.commit()
        
        flash(f'Event "{event_name}" and all associated data deleted successfully!', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting event: {str(e)}', 'error')
        return redirect(url_for('event_dashboard', event_id=event_id))

@app.route('/participants/bulk_delete', methods=['POST'])
@require_approval_for_action('bulk_delete')
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
@require_admin
def preview_ticket(participant_id):
    """Preview ticket email without sending"""
    participant = Participant.query.get_or_404(participant_id)
    return render_template('email/ticket_email.html', 
                         event=participant.event, 
                         participant=participant)

@app.route('/participants/bulk_resend', methods=['POST'])
@require_admin
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
@require_admin
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
@csrf.exempt  # Temporarily exempt from CSRF for testing
@require_admin
def toggle_checkin(participant_id):
    try:
        print(f"?? DEBUG: Check-in route called for participant {participant_id} with method {request.method}")
        print(f"?? DEBUG: Request headers: {dict(request.headers)}")
        print(f"?? DEBUG: Content-Type: {request.content_type}")
        
        participant = Participant.query.get_or_404(participant_id)
        
        # If GET request, redirect to dashboard with error message
        if request.method == 'GET':
            print(f"?? DEBUG: GET request detected, redirecting to dashboard")
            flash('Check-in must be done via button click, not direct URL access.', 'warning')
            return redirect(url_for('event_dashboard', event_id=participant.event_id))

        # Handle POST request
        print(f"?? DEBUG: Processing POST request - toggling check-in status")
        
        # Check if JSON data was sent
        json_data = None
        form_data = None
        redirect_requested = False
        
        if request.content_type == 'application/json':
            json_data = request.get_json()
            print(f"?? DEBUG: JSON data: {json_data}")
            if json_data:
                redirect_requested = json_data.get('redirect', False)
        else:
            form_data = dict(request.form)
            print(f"?? DEBUG: Form data: {form_data}")
            redirect_requested = request.form.get('redirect') == 'true'
        
        print(f"?? DEBUG: Redirect requested: {redirect_requested}")
        
        participant.checked_in = not participant.checked_in
        participant.checkin_time = datetime.now(timezone.utc) if participant.checked_in else None
        db.session.commit()
        print(f"?? DEBUG: Database updated successfully")
        
        status = 'checked in' if participant.checked_in else 'checked out'
        
        # Check if this is a form submission that should redirect
        if redirect_requested:
            print(f"?? DEBUG: Redirect requested, redirecting to dashboard")
            flash(f'{participant.name} {status}', 'success')
            return redirect(url_for('event_dashboard', event_id=participant.event_id))

        # Otherwise return JSON for AJAX calls
        response_data = {
            'success': True,
            'message': f'{participant.name} {status}',
            'checked_in': participant.checked_in
        }
        print(f"?? DEBUG: Returning JSON response: {response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        print(f"?? DEBUG: Exception occurred: {str(e)}")
        print(f"?? DEBUG: Exception type: {type(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
        flash(f'{participant.name} {status}', 'success')
        return redirect(url_for('event_dashboard', event_id=participant.event_id))
    
    # Otherwise return JSON for AJAX calls
    return jsonify({
        'success': True,
        'message': f'{participant.name} {status}',
        'checked_in': participant.checked_in
    })

@app.route('/send_emails/<int:event_id>', methods=['GET', 'POST'])
@require_admin
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
@require_admin
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
@require_approval_for_action('delete_participant')
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
@require_admin
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
@require_admin
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
@require_approval_for_action('bulk_delete')
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
@require_admin
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
@require_admin
def send_emails_alt(event_id):
    """Send emails to all participants (alternative route called by template)."""
    return redirect(url_for('send_emails', event_id=event_id))

# Certificate Routes
@app.route('/event/<int:event_id>/certificates')
@require_admin
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
@require_admin
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
@require_admin
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

# Quiz Routes
@app.route('/event/<int:event_id>/quiz')
@require_admin
def quiz_dashboard(event_id):
    """Quiz management dashboard"""
    event = Event.query.get_or_404(event_id)
    quiz = Quiz.query.filter_by(event_id=event_id).first()
    
    if not quiz:
        quiz = Quiz(event_id=event_id, title=f'{event.name} Quiz')
        db.session.add(quiz)
        db.session.commit()
    
    questions = QuizQuestion.query.filter_by(quiz_id=quiz.id).order_by(QuizQuestion.question_order).all()
    attempts = QuizAttempt.query.filter_by(quiz_id=quiz.id).all()
    
    # Get statistics
    stats = {
        'total_questions': len(questions),
        'total_attempts': len(attempts),
        'completed_attempts': len([a for a in attempts if a.is_completed]),
        'average_score': round(sum(a.score for a in attempts if a.is_completed) / max(len([a for a in attempts if a.is_completed]), 1), 2)
    }
    
    return render_template('quiz_dashboard.html', event=event, quiz=quiz, questions=questions, attempts=attempts, stats=stats)

@app.route('/event/<int:event_id>/quiz/config', methods=['GET', 'POST'])
@require_admin
def quiz_config(event_id):
    """Configure quiz settings"""
    event = Event.query.get_or_404(event_id)
    quiz = Quiz.query.filter_by(event_id=event_id).first()
    
    if not quiz:
        quiz = Quiz(event_id=event_id)
        db.session.add(quiz)
        db.session.commit()
    
    form = QuizConfigForm(obj=quiz)
    
    if form.validate_on_submit():
        try:
            form.populate_obj(quiz)
            quiz.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            
            flash('Quiz configuration saved successfully!', 'success')
            return redirect(url_for('quiz_dashboard', event_id=event_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving quiz configuration: {str(e)}', 'error')
    
    return render_template('quiz_config.html', event=event, quiz=quiz, form=form)

@app.route('/event/<int:event_id>/quiz/questions/add', methods=['GET', 'POST'])
@require_admin
def add_quiz_question(event_id):
    """Add a new quiz question manually"""
    event = Event.query.get_or_404(event_id)
    quiz = Quiz.query.filter_by(event_id=event_id).first()
    
    if not quiz:
        flash('Please configure the quiz first.', 'error')
        return redirect(url_for('quiz_config', event_id=event_id))
    
    form = QuizQuestionForm()
    
    if form.validate_on_submit():
        try:
            # Get next question order
            last_question = QuizQuestion.query.filter_by(quiz_id=quiz.id).order_by(QuizQuestion.question_order.desc()).first()
            next_order = (last_question.question_order + 1) if last_question else 1
            
            question = QuizQuestion(
                quiz_id=quiz.id,
                question_text=form.question_text.data,
                question_order=next_order,
                option_a=form.option_a.data,
                option_b=form.option_b.data,
                option_c=form.option_c.data,
                option_d=form.option_d.data,
                correct_answer=form.correct_answer.data,
                points=form.points.data or 1,
                time_limit=form.time_limit.data
            )
            
            db.session.add(question)
            db.session.commit()
            
            flash('Question added successfully!', 'success')
            return redirect(url_for('quiz_dashboard', event_id=event_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding question: {str(e)}', 'error')
    
    return render_template('add_quiz_question.html', event=event, quiz=quiz, form=form)

@app.route('/event/<int:event_id>/quiz/questions/upload', methods=['GET', 'POST'])
@require_admin
def upload_quiz_questions(event_id):
    """Upload quiz questions via CSV"""
    event = Event.query.get_or_404(event_id)
    quiz = Quiz.query.filter_by(event_id=event_id).first()
    
    if not quiz:
        flash('Please configure the quiz first.', 'error')
        return redirect(url_for('quiz_config', event_id=event_id))
    
    form = QuizUploadForm()
    
    if form.validate_on_submit():
        try:
            csv_file = form.csv_file.data
            stream = io.StringIO(csv_file.stream.read().decode("UTF8"), newline=None)
            csv_input = csv.reader(stream)
            
            # Skip header row
            next(csv_input)
            
            questions_added = 0
            current_order = QuizQuestion.query.filter_by(quiz_id=quiz.id).count() + 1
            
            for row in csv_input:
                if len(row) < 6:  # question, option_a, option_b, option_c, option_d, correct_answer
                    continue
                
                question_text = row[0].strip()
                option_a = row[1].strip()
                option_b = row[2].strip() 
                option_c = row[3].strip()
                option_d = row[4].strip()
                correct_answer = row[5].strip().upper()
                
                # Optional fields
                points = int(row[6]) if len(row) > 6 and row[6].strip().isdigit() else 1
                time_limit = int(row[7]) if len(row) > 7 and row[7].strip().isdigit() else None
                
                if not all([question_text, option_a, option_b, option_c, option_d, correct_answer]):
                    continue
                
                if correct_answer not in ['A', 'B', 'C', 'D']:
                    continue
                
                question = QuizQuestion(
                    quiz_id=quiz.id,
                    question_text=question_text,
                    question_order=current_order,
                    option_a=option_a,
                    option_b=option_b,
                    option_c=option_c,
                    option_d=option_d,
                    correct_answer=correct_answer,
                    points=points,
                    time_limit=time_limit
                )
                
                db.session.add(question)
                questions_added += 1
                current_order += 1
            
            db.session.commit()
            flash(f'Successfully uploaded {questions_added} questions!', 'success')
            return redirect(url_for('quiz_dashboard', event_id=event_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error uploading questions: {str(e)}', 'error')
    
    return render_template('upload_quiz_questions.html', event=event, quiz=quiz, form=form)

@app.route('/event/<int:event_id>/quiz/questions/<int:question_id>/delete', methods=['POST'])
@require_approval_for_action('delete_quiz_question')
def delete_quiz_question(event_id, question_id):
    """Delete a quiz question"""
    try:
        event = Event.query.get_or_404(event_id)
        question = QuizQuestion.query.get_or_404(question_id)
        
        if question.quiz.event_id != event_id:
            return jsonify({'success': False, 'error': 'Question not found'}), 404
        
        db.session.delete(question)
        db.session.commit()
        
        flash('Question deleted successfully!', 'success')
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/event/<int:event_id>/quiz/delete', methods=['POST'])
@require_approval_for_action('delete_quiz')
def delete_quiz(event_id):
    """Delete the entire quiz and all related data"""
    try:
        event = Event.query.get_or_404(event_id)
        quiz = Quiz.query.filter_by(event_id=event_id).first()
        
        if not quiz:
            return jsonify({'success': False, 'error': 'Quiz not found'}), 404
        
        quiz_title = quiz.title
        
        # Delete in proper order to avoid foreign key constraints
        # 1. Delete quiz answers first
        attempts = QuizAttempt.query.filter_by(quiz_id=quiz.id).all()
        for attempt in attempts:
            QuizAnswer.query.filter_by(attempt_id=attempt.id).delete()
            db.session.delete(attempt)
        
        # 2. Delete quiz questions
        QuizQuestion.query.filter_by(quiz_id=quiz.id).delete()
        
        # 3. Delete the quiz itself
        db.session.delete(quiz)
        
        db.session.commit()
        
        flash(f'Quiz "{quiz_title}" and all related data deleted successfully!', 'success')
        return jsonify({'success': True, 'message': f'Quiz "{quiz_title}" deleted successfully!'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/event/<int:event_id>/quiz/reset', methods=['POST'])
@require_admin
def reset_quiz(event_id):
    """Reset quiz data (delete all attempts and answers, keep questions)"""
    try:
        event = Event.query.get_or_404(event_id)
        quiz = Quiz.query.filter_by(event_id=event_id).first()
        
        if not quiz:
            return jsonify({'success': False, 'error': 'Quiz not found'}), 404
        
        # Count attempts before deletion for feedback
        attempts = QuizAttempt.query.filter_by(quiz_id=quiz.id).all()
        attempt_count = len(attempts)
        
        # Delete quiz answers and attempts, but keep questions and quiz configuration
        for attempt in attempts:
            QuizAnswer.query.filter_by(attempt_id=attempt.id).delete()
            db.session.delete(attempt)
        
        # Reset quiz state
        quiz.is_active = False
        quiz.quiz_start_time = None
        quiz.quiz_end_time = None
        quiz.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        flash(f'Quiz reset successfully! Removed {attempt_count} participant attempts.', 'success')
        return jsonify({
            'success': True, 
            'message': f'Quiz reset successfully! Removed {attempt_count} participant attempts.',
            'attempts_removed': attempt_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/event/<int:event_id>/quiz/start', methods=['POST'])
@require_admin
def start_quiz(event_id):
    """Start the quiz (admin function)"""
    try:
        event = Event.query.get_or_404(event_id)
        quiz = Quiz.query.filter_by(event_id=event_id).first()
        
        if not quiz:
            return jsonify({'success': False, 'error': 'Quiz not found'}), 404
        
        if not quiz.questions:
            return jsonify({'success': False, 'error': 'No questions added to quiz'}), 400
        
        quiz.quiz_start_time = datetime.now(timezone.utc)
        quiz.is_active = True
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Quiz started successfully!'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/event/<int:event_id>/quiz/end', methods=['POST'])
@require_admin
def end_quiz(event_id):
    """End the quiz (admin function)"""
    try:
        event = Event.query.get_or_404(event_id)
        quiz = Quiz.query.filter_by(event_id=event_id).first()
        
        if not quiz:
            return jsonify({'success': False, 'error': 'Quiz not found'}), 404
        
        quiz.quiz_end_time = datetime.now(timezone.utc)
        quiz.is_active = False
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Quiz ended successfully!'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/event/<int:event_id>/quiz/play')
def play_quiz(event_id):
    """Main quiz interface for participants"""
    event = Event.query.get_or_404(event_id)
    quiz = Quiz.query.filter_by(event_id=event_id).first()
    
    if not quiz:
        flash('Quiz not found.', 'error')
        return redirect(url_for('event_dashboard', event_id=event_id))
    
    if not quiz.is_active:
        flash('Quiz is not currently active.', 'warning')
        return redirect(url_for('event_dashboard', event_id=event_id))
    
    if quiz.is_ended:
        return render_template('quiz_ended.html', event=event, quiz=quiz)
    
    return render_template('play_quiz.html', event=event, quiz=quiz)

@app.route('/event/<int:event_id>/quiz/join', methods=['POST'])
@rate_limit_quiz_joins(max_joins_per_minute=50)  # Allow up to 50 joins per minute per IP
def join_quiz(event_id):
    """Join quiz as a participant - Optimized for high concurrency"""
    try:
        data = request.get_json()
        participant_email = data.get('email')
        participant_name = data.get('name')
        
        if not participant_email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        event = Event.query.get_or_404(event_id)
        
        # Use cached quiz data if available
        cached_quiz = quiz_performance.get_cached_quiz_data(event_id)
        if cached_quiz and cached_quiz.get('is_active'):
            quiz_id = cached_quiz['quiz_id']
            quiz = Quiz.query.get(quiz_id)
        else:
            quiz = Quiz.query.filter_by(event_id=event_id).first()
            if quiz:
                # Cache quiz data for faster subsequent requests
                quiz_cache_data = {
                    'quiz_id': quiz.id,
                    'is_active': quiz.is_active,
                    'title': quiz.title,
                    'total_questions': quiz.total_questions
                }
                quiz_performance.cache_quiz_data(event_id, quiz_cache_data)
        
        if not quiz or not quiz.is_active or quiz.is_ended:
            if quiz and quiz.is_ended:
                return jsonify({'success': False, 'error': 'Quiz has ended. Check the leaderboard for results.'}), 400
            else:
                return jsonify({'success': False, 'error': 'Quiz is not active'}), 400
        
        # Check participant limit before allowing new participants
        if quiz.is_full:
            return jsonify({
                'success': False, 
                'error': f'Quiz is full! Maximum {quiz.participant_limit} participants allowed.'
            }), 400
        
        # Record participation for stats
        quiz_stats.record_participation(quiz.id, 'join')
        
        # Optimized participant lookup/creation
        participant = Participant.query.filter_by(
            email=participant_email, 
            event_id=event_id
        ).with_for_update().first()  # Lock for update to prevent race conditions
        
        if not participant:
            if not participant_name:
                return jsonify({'success': False, 'error': 'Name is required for new participants'}), 400
            
            participant = Participant(
                name=participant_name,
                email=participant_email,
                event_id=event_id,
                checked_in=True  # Auto check-in quiz participants
            )
            db.session.add(participant)
            db.session.flush()
        
        # Check for existing attempt with optimized query
        existing_attempt = QuizAttempt.query.filter_by(
            quiz_id=quiz.id,
            participant_id=participant.id
        ).first()
        
        if existing_attempt:
            if existing_attempt.is_completed:
                return jsonify({'success': False, 'error': 'You have already completed this quiz'}), 400
            else:
                # Resume existing attempt
                attempt = existing_attempt
        else:
            # Double-check participant limit before creating new attempt (race condition protection)
            current_attempt_count = QuizAttempt.query.filter_by(quiz_id=quiz.id).count()
            if current_attempt_count >= quiz.participant_limit:
                return jsonify({
                    'success': False, 
                    'error': f'Quiz is full! Maximum {quiz.participant_limit} participants allowed.'
                }), 400
            
            # Create new attempt
            attempt = QuizAttempt(
                quiz_id=quiz.id,
                participant_id=participant.id
            )
            db.session.add(attempt)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'attempt_id': attempt.id,
            'participant_id': participant.id,
            'current_question': attempt.current_question
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/quiz/attempt/<int:attempt_id>/question')
def get_quiz_question(attempt_id):
    """Get current question for quiz attempt"""
    try:
        attempt = QuizAttempt.query.get_or_404(attempt_id)
        quiz = attempt.quiz
        
        if not quiz.is_active or quiz.is_ended:
            return jsonify({'success': False, 'error': 'Quiz is not active'}), 400
        
        # Get current question
        question = QuizQuestion.query.filter_by(
            quiz_id=quiz.id,
            question_order=attempt.current_question
        ).first()
        
        if not question:
            # No more questions, complete the attempt
            attempt.is_completed = True
            attempt.completed_at = datetime.now(timezone.utc)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'completed': True,
                'score': attempt.score,
                'total_questions': quiz.total_questions
            })
        
        return jsonify({
            'success': True,
            'question': {
                'id': question.id,
                'question_text': question.question_text,
                'options': question.options,
                'question_number': question.question_order,
                'total_questions': quiz.total_questions,
                'time_limit': question.effective_time_limit
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/quiz/attempt/<int:attempt_id>/answer', methods=['POST'])
def submit_quiz_answer(attempt_id):
    """Submit answer for quiz question - Optimized with anti-double-submission"""
    try:
        data = request.get_json()
        selected_answer = data.get('answer')
        time_taken = data.get('time_taken', 0)
        
        # Get performance manager for locking
        perf_manager = app.extensions.get('quiz_performance')
        
        attempt = QuizAttempt.query.get_or_404(attempt_id)
        quiz = attempt.quiz
        
        # Check if quiz is still active
        if not quiz.is_active or quiz.is_ended:
            return jsonify({'success': False, 'error': 'Quiz is no longer active'}), 400
        
        # Get current question
        question = QuizQuestion.query.filter_by(
            quiz_id=attempt.quiz_id,
            question_order=attempt.current_question
        ).first()
        
        if not question:
            return jsonify({'success': False, 'error': 'Question not found'}), 404
        
        # Use lock to prevent double submissions for high concurrency
        if perf_manager:
            answer_lock = perf_manager.get_answer_lock(attempt.id, question.id)
            if not answer_lock.acquire(blocking=False):
                return jsonify({
                    'success': False, 
                    'error': 'Answer submission in progress, please wait'
                }), 429
        else:
            answer_lock = None
        
        try:
            # Check if answer already exists (with database lock)
            existing_answer = QuizAnswer.query.filter_by(
                attempt_id=attempt.id,
                question_id=question.id
            ).with_for_update().first()
            
            if existing_answer:
                return jsonify({'success': False, 'error': 'Answer already submitted'}), 400
            
            # Create answer record
            is_correct = selected_answer == question.correct_answer
            answer = QuizAnswer(
                attempt_id=attempt.id,
                question_id=question.id,
                selected_answer=selected_answer,
                is_correct=is_correct,
                time_taken=time_taken
            )
            
            db.session.add(answer)
            
            # Update score and move to next question
            if is_correct:
                attempt.score += question.points
            
            attempt.current_question += 1
            attempt.total_time_taken += time_taken
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'correct': is_correct,
                'correct_answer': question.correct_answer,
                'current_score': attempt.score
            })
            
        finally:
            # Always release the lock
            if answer_lock:
                answer_lock.release()
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/event/<int:event_id>/quiz/leaderboard')
def quiz_leaderboard(event_id):
    """Show quiz leaderboard"""
    event = Event.query.get_or_404(event_id)
    quiz = Quiz.query.filter_by(event_id=event_id).first()
    
    if not quiz:
        flash('Quiz not found.', 'error')
        return redirect(url_for('event_dashboard', event_id=event_id))
    
    # Check if this is a participant view (from quiz completion) or admin view
    is_participant = request.args.get('participant') == 'true'
    
    leaderboard = quiz.leaderboard_data
    
    return render_template('quiz_leaderboard.html', 
                         event=event, 
                         quiz=quiz, 
                         leaderboard=leaderboard,
                         is_participant=is_participant)

@app.route('/event/<int:event_id>/quiz/gamemaster')
@require_admin
def quiz_gamemaster(event_id):
    """Game master dashboard with live updates"""
    event = Event.query.get_or_404(event_id)
    quiz = Quiz.query.filter_by(event_id=event_id).first()
    
    if not quiz:
        flash('Quiz not found.', 'error')
        return redirect(url_for('event_dashboard', event_id=event_id))
    
    return render_template('quiz_gamemaster.html', event=event, quiz=quiz)

@app.route('/api/quiz/<int:quiz_id>/live-leaderboard')
def quiz_live_leaderboard_api(quiz_id):
    """API endpoint for live leaderboard updates"""
    try:
        quiz = Quiz.query.get_or_404(quiz_id)
        attempts = quiz.live_leaderboard_data
        
        leaderboard_data = []
        for i, attempt in enumerate(attempts, 1):
            participant = attempt.participant
            
            # Calculate progress percentage
            progress = (attempt.current_question - 1) / max(quiz.total_questions, 1) * 100
            
            leaderboard_data.append({
                'rank': i,
                'participant_name': participant.name,
                'participant_email': participant.email,
                'score': attempt.score,
                'current_question': attempt.current_question,
                'total_questions': quiz.total_questions,
                'progress_percentage': round(progress, 1),
                'total_time_taken': attempt.total_time_taken,
                'is_completed': attempt.is_completed,
                'completion_time': attempt.completed_at.strftime('%H:%M:%S') if attempt.completed_at else None,
                'status': 'Completed' if attempt.is_completed else f'Question {attempt.current_question}/{quiz.total_questions}'
            })
        
        return jsonify({
            'success': True,
            'quiz_id': quiz_id,
            'quiz_title': quiz.title,
            'quiz_status': {
                'is_active': quiz.is_active,
                'is_started': quiz.is_started,
                'is_ended': quiz.is_ended,
                'total_questions': quiz.total_questions,
                'current_participants': quiz.current_participants,
                'participant_limit': quiz.participant_limit
            },
            'leaderboard': leaderboard_data,
            'last_updated': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/quiz/<int:quiz_id>/live-stats')
def quiz_live_stats(quiz_id):
    """Get live quiz statistics for monitoring"""
    try:
        quiz = Quiz.query.get_or_404(quiz_id)
        
        # Get live stats from Redis (if available)
        live_stats = quiz_stats.get_live_stats(quiz_id)
        
        # Get database stats for backup
        total_attempts = QuizAttempt.query.filter_by(quiz_id=quiz_id).count()
        completed_attempts = QuizAttempt.query.filter_by(quiz_id=quiz_id, is_completed=True).count()
        
        # Average score calculation
        from sqlalchemy import func
        avg_score_result = db.session.query(func.avg(QuizAttempt.score)).filter_by(
            quiz_id=quiz_id, 
            is_completed=True
        ).scalar()
        avg_score = round(float(avg_score_result), 2) if avg_score_result else 0
        
        stats = {
            'quiz_id': quiz_id,
            'quiz_title': quiz.title,
            'is_active': quiz.is_active,
            'total_questions': quiz.total_questions,
            'participant_limit': quiz.participant_limit,
            'current_participants': quiz.current_participants,
            'available_spots': quiz.available_spots,
            'is_full': quiz.is_full,
            'live_stats': live_stats,
            'database_stats': {
                'total_attempts': total_attempts,
                'completed_attempts': completed_attempts,
                'completion_rate': round((completed_attempts / total_attempts * 100), 2) if total_attempts > 0 else 0,
                'average_score': avg_score
            },
            'performance_metrics': {
                'concurrent_submissions': len(quiz_performance.answer_locks) if quiz_performance else 0,
                'cache_available': quiz_performance.redis_client is not None if quiz_performance else False
            }
        }
        
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/event/<int:event_id>/quiz/qr')
@require_admin
def generate_quiz_qr(event_id):
    """Generate QR code for quiz joining"""
    try:
        event = Event.query.get_or_404(event_id)
        quiz = Quiz.query.filter_by(event_id=event_id).first()
        
        # Always create QR code for the quiz game level (play route)
        # Even if quiz doesn't exist yet, participants should land on the quiz play page
        quiz_join_url = url_for('play_quiz', event_id=event_id, _external=True)
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,  # controls the size of the QR Code
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(quiz_join_url)
        qr.make(fit=True)
        
        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to bytes
        img_io = BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        
        return Response(
            img_io.getvalue(),
            mimetype='image/png',
            headers={
                'Content-Disposition': f'inline; filename=quiz_qr_{event.title.replace(" ", "_")}.png',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
        
    except Exception as e:
        # Create a fallback QR with quiz play URL (not dashboard)
        try:
            fallback_url = url_for('play_quiz', event_id=event_id, _external=True)
            qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
            qr.add_data(fallback_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img_io = BytesIO()
            img.save(img_io, 'PNG')
            img_io.seek(0)
            return Response(img_io.getvalue(), mimetype='image/png')
        except:
            return redirect(url_for('play_quiz', event_id=event_id))

# Export for Vercel
application = app

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_ENV') == 'development')
