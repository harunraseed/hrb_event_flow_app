"""
Script to create a new superadmin user
"""
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default='member', nullable=False)
    is_active = db.Column(db.Boolean, default=True)

with app.app_context():
    print("\n" + "="*60)
    print("CREATING NEW SUPERADMIN USER")
    print("="*60)
    print(f"\nDatabase: {os.getenv('DATABASE_URL')[:50]}...")
    
    # Check if superadmin already exists
    existing = User.query.filter_by(username='superadmin').first()
    
    if existing:
        print(f"\n⚠️ User 'superadmin' already exists!")
        print(f"  ID: {existing.id}")
        print(f"  Email: {existing.email}")
        print(f"  Role: {existing.role}")
        
        # Update password anyway
        print("\nUpdating password...")
        test_password = "Admin@123"
        new_hash = bcrypt.generate_password_hash(test_password).decode('utf-8')
        existing.password_hash = new_hash
        existing.role = 'superadmin'  # Ensure role is correct
        existing.is_active = True  # Ensure active
        db.session.commit()
        print("✓ Password updated!")
    else:
        print("\n✓ Creating new superadmin user...")
        
        superadmin = User(
            username='superadmin',
            email='superadmin@example.com',
            role='superadmin',
            is_active=True
        )
        superadmin.password_hash = bcrypt.generate_password_hash('Admin@123').decode('utf-8')
        db.session.add(superadmin)
        db.session.commit()
        print("✓ Superadmin user created!")
    
    print("\n" + "-"*60)
    print("LOGIN CREDENTIALS")
    print("-"*60)
    print("Username: superadmin")
    print("Password: Admin@123")
    print("="*60 + "\n")
