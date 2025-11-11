#!/usr/bin/env python3
"""
Database Reset Script
This script drops and recreates all database tables with the new schema.
Use this when you've made changes to your models.
"""

import os
import sys

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from index import app, db

def reset_database():
    """Drop and recreate all database tables"""
    with app.app_context():
        try:
            print("Dropping all database tables with CASCADE...")
            # Use raw SQL to drop with CASCADE to handle dependencies
            from sqlalchemy import text
            result = db.session.execute(text("DROP SCHEMA public CASCADE;"))
            result = db.session.execute(text("CREATE SCHEMA public;"))
            result = db.session.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
            result = db.session.execute(text("GRANT ALL ON SCHEMA public TO public;"))
            db.session.commit()
            print("✓ All tables dropped with CASCADE")
            
            print("Creating new database tables...")
            db.create_all()
            print("✓ All tables created with new schema")
            
            print("Database reset completed successfully!")
            
        except Exception as e:
            print(f"Error resetting database: {e}")
            print("Trying alternative method...")
            try:
                # Alternative: Try to drop each table individually
                db.session.execute(text("DROP TABLE IF EXISTS certificates CASCADE;"))
                db.session.execute(text("DROP TABLE IF EXISTS participants CASCADE;"))
                db.session.execute(text("DROP TABLE IF EXISTS events CASCADE;"))
                db.session.commit()
                print("✓ Tables dropped individually")
                
                db.create_all()
                print("✓ All tables recreated")
                
            except Exception as e2:
                print(f"Alternative method also failed: {e2}")
                raise

if __name__ == "__main__":
    reset_database()