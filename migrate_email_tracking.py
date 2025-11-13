#!/usr/bin/env python3
"""
Database Migration: Add Email Tracking Fields to Participants

Run this script to add email_sent and email_sent_date columns to the participants table
"""

import os
import sys
import sqlite3
from datetime import datetime

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def migrate_sqlite():
    """Add email tracking columns to SQLite database"""
    db_path = os.path.join(project_root, 'instance', 'event_ticketing.db')
    
    if not os.path.exists(db_path):
        print(f"❌ SQLite database not found at: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(participants)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'email_sent' not in columns:
            print("Adding email_sent column...")
            cursor.execute('ALTER TABLE participants ADD COLUMN email_sent BOOLEAN DEFAULT 0')
            
        if 'email_sent_date' not in columns:
            print("Adding email_sent_date column...")
            cursor.execute('ALTER TABLE participants ADD COLUMN email_sent_date DATETIME')
        
        conn.commit()
        conn.close()
        
        print("✅ Email tracking columns added successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error migrating database: {e}")
        return False

def main():
    """Main migration function"""
    print("🚀 Starting email tracking migration for SQLite...")
    print("=" * 50)
    
    if migrate_sqlite():
        print("🎉 Email tracking migration completed successfully!")
        return True
    else:
        print("❌ Migration failed!")
        return False

if __name__ == "__main__":
    main()