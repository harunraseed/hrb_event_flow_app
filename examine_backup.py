#!/usr/bin/env python3

import sqlite3
import os
import sys

def examine_backup_db():
    """Examine the backup database structure and content"""
    db_path = 'event_ticketing_bkp.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Backup database '{db_path}' not found!")
        return False
    
    try:
        # Connect to the backup database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print(f"📊 Examining backup database: {db_path}")
        print("=" * 50)
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print(f"🗂️  Found {len(tables)} tables:")
        for table in tables:
            table_name = table[0]
            try:
                cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
                count = cursor.fetchone()[0]
                print(f"   📋 {table_name}: {count} records")
            except Exception as e:
                print(f"   ❌ {table_name}: Error - {e}")
        
        print("\n" + "=" * 50)
        
        # Examine Events table specifically
        if any(table[0] == 'events' for table in tables):
            print("🎪 EVENTS TABLE:")
            
            # Get table structure
            cursor.execute('PRAGMA table_info(events)')
            columns = cursor.fetchall()
            print("   Columns:")
            for col in columns:
                print(f"     - {col[1]} ({col[2]})")
            
            # Get sample data
            cursor.execute('SELECT * FROM events LIMIT 5')
            events = cursor.fetchall()
            print(f"\n   Sample Events (showing first 5):")
            for i, event in enumerate(events, 1):
                print(f"     {i}. ID: {event[0]}, Data: {event[1:3]}")
        
        # Examine Participants table
        if any(table[0] == 'participants' for table in tables):
            print("\n👥 PARTICIPANTS TABLE:")
            cursor.execute('SELECT COUNT(*) FROM participants')
            count = cursor.fetchone()[0]
            print(f"   Total participants: {count}")
            
            if count > 0:
                cursor.execute('SELECT event_id, COUNT(*) FROM participants GROUP BY event_id')
                by_event = cursor.fetchall()
                print("   Participants by event:")
                for event_id, part_count in by_event:
                    print(f"     Event {event_id}: {part_count} participants")
        
        # Examine other important tables
        important_tables = ['users', 'quizzes', 'quiz_questions', 'quiz_attempts', 'certificates']
        for table_name in important_tables:
            if any(table[0] == table_name for table in tables):
                cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
                count = cursor.fetchone()[0]
                if count > 0:
                    print(f"\n📊 {table_name.upper()}: {count} records")
        
        conn.close()
        print("\n✅ Database examination completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error examining database: {e}")
        return False

if __name__ == "__main__":
    examine_backup_db()