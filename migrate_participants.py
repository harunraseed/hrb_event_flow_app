#!/usr/bin/env python3
"""
Participants-only migration: Migrate participants for events that were already migrated
"""

import sqlite3
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from datetime import datetime
import secrets
import string

load_dotenv()

def generate_ticket_number():
    """Generate a unique ticket number"""
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))

def migrate_participants_only():
    """Migrate participants for events that are already in production"""
    print("👥 Migrating Participants for Existing Events...")
    
    # Connect to databases
    sqlite_conn = sqlite3.connect('event_ticketing_bkp.db')
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    db_url = os.getenv('DATABASE_URL')
    pg_conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    pg_cursor = pg_conn.cursor()
    
    # First, get the mapping of event names to production IDs
    print("   🔍 Finding event mappings...")
    pg_cursor.execute("SELECT id, name FROM events ORDER BY id DESC LIMIT 10")
    prod_events = pg_cursor.fetchall()
    
    print("   Production Events:")
    for event in prod_events:
        print(f"     ID {event['id']}: {event['name']}")
    
    # Get backup events
    sqlite_cursor.execute("SELECT id, name FROM events")
    backup_events = sqlite_cursor.fetchall()
    
    # Create event mapping by name
    event_mapping = {}
    for backup_event in backup_events:
        backup_name = backup_event['name']
        backup_id = backup_event['id']
        
        # Find matching production event by name
        for prod_event in prod_events:
            if prod_event['name'] == backup_name:
                event_mapping[backup_id] = prod_event['id']
                print(f"   ✅ Mapped: {backup_name} (backup ID {backup_id} → prod ID {prod_event['id']})")
                break
    
    if not event_mapping:
        print("   ❌ No event mappings found!")
        return False
    
    # Get backup participants
    sqlite_cursor.execute("SELECT * FROM participants")
    backup_participants = sqlite_cursor.fetchall()
    
    migrated_count = 0
    failed_count = 0
    
    print(f"\n   📋 Processing {len(backup_participants)} participants...")
    
    for participant in backup_participants:
        old_id = participant['id']
        old_event_id = participant['event_id']
        
        # Skip if event wasn't migrated
        if old_event_id not in event_mapping:
            print(f"   ⚠️  Skipping participant {old_id}: Event {old_event_id} not found in mapping")
            failed_count += 1
            continue
        
        new_event_id = event_mapping[old_event_id]
        
        # Prepare participant data with type conversion and only essential columns
        participant_data = {
            'name': participant['name'],
            'email': participant['email'], 
            'event_id': new_event_id,
            'ticket_number': participant['ticket_number'] if 'ticket_number' in participant.keys() and participant['ticket_number'] else generate_ticket_number(),  # Use existing ticket number
            'checked_in': bool(participant['checked_in']) if 'checked_in' in participant.keys() and participant['checked_in'] is not None else False,
            'created_at': participant['created_at'] if 'created_at' in participant.keys() else datetime.now(),
        }
        
        # Add optional columns only if they exist in the backup and are safe
        if 'checkin_time' in participant.keys() and participant['checkin_time']:
            participant_data['checkin_time'] = participant['checkin_time']
        
        # Add email tracking columns if they exist
        if 'email_sent' in participant.keys() and participant['email_sent'] is not None:
            participant_data['email_sent'] = bool(participant['email_sent'])
        
        if 'email_sent_at' in participant.keys() and participant['email_sent_at']:
            participant_data['email_sent_date'] = participant['email_sent_at']
        
        # Check if this participant already exists (by name and email for this event)
        pg_cursor.execute("""
            SELECT id FROM participants 
            WHERE event_id = %s AND name = %s AND email = %s
        """, (new_event_id, participant_data['name'], participant_data['email']))
        
        existing = pg_cursor.fetchone()
        if existing:
            print(f"   ⚠️  Skipping participant {old_id}: Already exists as ID {existing['id']}")
            continue
        
        # Insert participant with only the columns that exist
        columns = list(participant_data.keys())
        placeholders = [f'%({col})s' for col in columns]
        
        insert_query = f"""
            INSERT INTO participants ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING id
        """
        
        try:
            pg_cursor.execute(insert_query, participant_data)
            new_id = pg_cursor.fetchone()['id']
            migrated_count += 1
            
            if migrated_count % 25 == 0:
                print(f"   📊 Migrated {migrated_count} participants...")
                pg_conn.commit()  # Commit in batches
                
        except Exception as e:
            print(f"   ❌ Failed to migrate participant {old_id}: {e}")
            failed_count += 1
            pg_conn.rollback()
            continue
    
    # Final commit
    pg_conn.commit()
    
    sqlite_conn.close()
    pg_conn.close()
    
    print(f"\n✅ Participant Migration Complete!")
    print(f"   Migrated: {migrated_count}")
    print(f"   Failed: {failed_count}")
    print(f"   Total: {len(backup_participants)}")
    
    return migrated_count > 0

def main():
    """Main function"""
    print("🚀 Participants-Only Migration")
    print("=" * 40)
    
    success = migrate_participants_only()
    
    if success:
        print("\n🎉 Migration completed! Check your production database.")
    else:
        print("\n❌ Migration failed!")

if __name__ == "__main__":
    main()