"""
Script to initialize the database and create the first admin user
"""
import os
import sys
from datetime import datetime, timezone
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
database_url = os.getenv('DATABASE_URL')

if not database_url:
    print("\n❌ ERROR: DATABASE_URL not found in environment!")
    print("\nPlease create a .env file with DATABASE_URL")
    exit(1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# Define User model
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default='member', nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    reset_token = db.Column(db.String(100))
    reset_token_expires = db.Column(db.DateTime)

with app.app_context():
    print("\n" + "="*60)
    print("DATABASE INITIALIZATION")
    print("="*60)
    print(f"\nDatabase: {database_url[:50]}...")
    
    # Create all tables
    print("\n📁 Creating database tables...")
    db.create_all()
    print("✓ Tables created successfully!")
    
    # Check if admin user exists
    admin = User.query.filter_by(username='admin').first()
    
    if admin:
        print("\n✓ Admin user already exists!")
        print(f"  Username: {admin.username}")
        print(f"  Email: {admin.email}")
        print(f"  Role: {admin.role}")
    else:
        print("\n👤 Creating admin user...")
        admin_password = "Admin@123"
        password_hash = bcrypt.generate_password_hash(admin_password).decode('utf-8')
        
        admin = User(
            username='admin',
            email='admin@example.com',
            password_hash=password_hash,
            role='superadmin',
            is_active=True
        )
        
        db.session.add(admin)
        db.session.commit()
        
        print("✓ Admin user created successfully!")
        print(f"  Username: admin")
        print(f"  Email: admin@example.com")
        print(f"  Password: {admin_password}")
        print(f"  Role: superadmin")
        print(f"  Active: True")
    
    print("\n" + "="*60)
    print("✅ DATABASE INITIALIZATION COMPLETE")
    print("="*60 + "\n")
