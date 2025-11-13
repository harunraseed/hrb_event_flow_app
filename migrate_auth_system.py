#!/usr/bin/env python3
"""
Database Migration: Add User Authentication System
Creates User and PendingAction tables and creates initial superadmin user

Run this script after adding authentication models to add the new tables
and create the first superadmin user.
"""

import os
import sys
from datetime import datetime, timezone

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from index import app, db, User, PendingAction, bcrypt

def create_tables():
    """Create the new authentication tables"""
    print("Creating authentication tables...")
    
    with app.app_context():
        # Create only the new tables (User and PendingAction)
        try:
            # Create tables
            db.create_all()
            print("✅ Authentication tables created successfully!")
            return True
        except Exception as e:
            print(f"❌ Error creating tables: {e}")
            return False

def create_superadmin():
    """Create the initial superadmin user"""
    print("\n🔧 Setting up initial superadmin user...")
    
    with app.app_context():
        try:
            # Check if any superadmin exists
            existing_superadmin = User.query.filter_by(role='superadmin').first()
            if existing_superadmin:
                print(f"⚠️  Superadmin user already exists: {existing_superadmin.username}")
                return True
            
            # Prompt for superadmin details
            print("\nPlease provide details for the initial superadmin:")
            username = input("Username: ").strip()
            email = input("Email: ").strip()
            password = input("Password (minimum 6 characters): ").strip()
            
            # Validate input
            if len(username) < 3:
                print("❌ Username must be at least 3 characters long")
                return False
            
            if len(password) < 6:
                print("❌ Password must be at least 6 characters long")
                return False
            
            if '@' not in email:
                print("❌ Please provide a valid email address")
                return False
            
            # Check if username or email already exists
            if User.query.filter_by(username=username).first():
                print("❌ Username already exists")
                return False
            
            if User.query.filter_by(email=email).first():
                print("❌ Email already exists")
                return False
            
            # Create superadmin user
            superadmin = User(
                username=username,
                email=email,
                role='superadmin',
                is_active=True
            )
            superadmin.set_password(password)
            
            db.session.add(superadmin)
            db.session.commit()
            
            print(f"✅ Superadmin user '{username}' created successfully!")
            print(f"You can now log in at: http://localhost:5000/login")
            return True
            
        except Exception as e:
            print(f"❌ Error creating superadmin: {e}")
            db.session.rollback()
            return False

def main():
    """Main migration function"""
    print("🚀 Starting authentication system migration...")
    print("=" * 50)
    
    # Step 1: Create tables
    if not create_tables():
        print("\n❌ Migration failed: Could not create tables")
        return False
    
    # Step 2: Create superadmin user
    if not create_superadmin():
        print("\n❌ Migration failed: Could not create superadmin user")
        return False
    
    print("\n" + "=" * 50)
    print("🎉 Authentication system migration completed successfully!")
    print("\nNext steps:")
    print("1. Restart your application")
    print("2. Navigate to /login to access the admin panel")
    print("3. Use your superadmin credentials to log in")
    print("4. Create additional admin and member users as needed")
    
    return True

if __name__ == "__main__":
    main()