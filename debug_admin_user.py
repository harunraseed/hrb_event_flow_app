"""
Debug script to check admin user in database
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
    print("CHECKING ADMIN USER IN DATABASE")
    print("="*60)
    print(f"\nDatabase: {os.getenv('DATABASE_URL')[:50]}...")
    
    # Find admin user
    admin = User.query.filter_by(username='admin').first()
    
    if admin:
        print(f"\n✓ Admin user found!")
        print(f"  ID: {admin.id}")
        print(f"  Username: {admin.username}")
        print(f"  Email: {admin.email}")
        print(f"  Role: {admin.role}")
        print(f"  Active: {admin.is_active}")
        print(f"  Password Hash: {admin.password_hash[:50]}...")
        
        # Test password
        test_password = "Admin@123"
        print(f"\nTesting password: {test_password}")
        is_valid = bcrypt.check_password_hash(admin.password_hash, test_password)
        print(f"Password valid: {is_valid}")
        
        if not is_valid:
            print("\n⚠️ Password doesn't match! Generating new hash...")
            new_hash = bcrypt.generate_password_hash(test_password).decode('utf-8')
            print(f"New hash: {new_hash}")
            
            # Update in database
            admin.password_hash = new_hash
            db.session.commit()
            print("✓ Password hash updated in database!")
            
            # Verify again
            is_valid_now = bcrypt.check_password_hash(admin.password_hash, test_password)
            print(f"Password valid now: {is_valid_now}")
        else:
            print("\n✓ Password is already correct!")
            print("\n⚠️ FORCING PASSWORD UPDATE to ensure it's in Supabase...")
            new_hash = bcrypt.generate_password_hash(test_password).decode('utf-8')
            admin.password_hash = new_hash
            db.session.commit()
            print("✓ Password hash force-updated in Supabase!")
    else:
        print("\n✗ Admin user not found!")
        print("Creating admin user...")
        
        admin = User(
            username='admin',
            email='admin@example.com',
            role='superadmin',
            is_active=True
        )
        admin.password_hash = bcrypt.generate_password_hash('Admin@123').decode('utf-8')
        db.session.add(admin)
        db.session.commit()
        print("✓ Admin user created!")
        print(f"  Username: admin")
        print(f"  Password: Admin@123")
    
    print("="*60 + "\n")
