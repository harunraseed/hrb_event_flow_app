#!/usr/bin/env python3
"""
Database Migration: Add Password Reset Token Support to Users Table
Date: 2025-11-13
Description: Adds reset_token and reset_token_expires columns to the users table
"""

import os
import sys
from datetime import datetime, timezone

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from index import app, db

def migrate_password_reset_tokens():
    """Add password reset token fields to users table"""
    
    print("🔄 Starting password reset token migration...")
    
    with app.app_context():
        try:
            # Check if migration is needed
            inspector = db.inspect(db.engine)
            columns = inspector.get_columns('users')
            column_names = [col['name'] for col in columns]
            
            if 'reset_token' in column_names and 'reset_token_expires' in column_names:
                print("✅ Password reset token columns already exist. Migration not needed.")
                return True
            
            # Perform migration
            print("📝 Adding password reset token columns to users table...")
            
            # Add the new columns
            if 'reset_token' not in column_names:
                with db.engine.connect() as connection:
                    connection.execute(db.text('ALTER TABLE users ADD COLUMN reset_token VARCHAR(100)'))
                    connection.commit()
                print("  ✅ Added reset_token column")
            
            if 'reset_token_expires' not in column_names:
                with db.engine.connect() as connection:
                    connection.execute(db.text('ALTER TABLE users ADD COLUMN reset_token_expires DATETIME'))
                    connection.commit()
                print("  ✅ Added reset_token_expires column")
            
            print("✅ Password reset token migration completed successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Migration failed: {str(e)}")
            return False

def verify_migration():
    """Verify that the migration was successful"""
    
    print("\n🔍 Verifying migration...")
    
    with app.app_context():
        try:
            inspector = db.inspect(db.engine)
            columns = inspector.get_columns('users')
            column_names = [col['name'] for col in columns]
            
            required_columns = ['reset_token', 'reset_token_expires']
            missing_columns = [col for col in required_columns if col not in column_names]
            
            if missing_columns:
                print(f"❌ Migration verification failed. Missing columns: {missing_columns}")
                return False
            
            print("✅ All password reset token columns present")
            print("✅ Migration verification successful!")
            return True
            
        except Exception as e:
            print(f"❌ Verification failed: {str(e)}")
            return False

if __name__ == "__main__":
    print("🚀 Password Reset Token Migration Script")
    print("=" * 50)
    
    # Run migration
    if migrate_password_reset_tokens():
        # Verify migration
        if verify_migration():
            print("\n🎉 Password reset token support has been successfully added to your database!")
            print("\nNew features available:")
            print("  • Users can request password reset via email")
            print("  • Secure token-based password reset process")
            print("  • Automatic token expiration for security")
        else:
            print("\n⚠️  Migration completed but verification failed. Please check your database.")
            sys.exit(1)
    else:
        print("\n❌ Migration failed. Please check the error messages above.")
        sys.exit(1)