#!/usr/bin/env python3
"""
Schema-aware migration: Handles differences between backup and production schemas
"""

import sqlite3
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from datetime import datetime
import secrets

load_dotenv()

def get_production_schema():
    """Get the production database schema"""
    db_url = os.getenv('DATABASE_URL')
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    # Get events table schema
    cursor.execute("""
        SELECT column_name, data_type, is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'events' AND table_schema = 'public'
        ORDER BY ordinal_position
    """)
    event_columns = cursor.fetchall()
    
    # Get participants table schema
    cursor.execute("""
        SELECT column_name, data_type, is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'participants' AND table_schema = 'public'
        ORDER BY ordinal_position
    """)
    participant_columns = cursor.fetchall()
    
    conn.close()
    
    return {
        'events': [col['column_name'] for col in event_columns],
        'participants': [col['column_name'] for col in participant_columns]
    }

def migrate_events_safe():
    """Migrate events with schema-safe mapping"""
    print("🎪 Migrating Events (schema-safe)...")
    
    # Get production schema
    prod_schema = get_production_schema()
    prod_event_cols = prod_schema['events']
    
    print(f"   Production event columns: {prod_event_cols}")
    
    # Connect to databases
    sqlite_conn = sqlite3.connect('event_ticketing_bkp.db')
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    db_url = os.getenv('DATABASE_URL')
    pg_conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    pg_cursor = pg_conn.cursor()
    
    # Get backup events
    sqlite_cursor.execute("SELECT * FROM events")
    backup_events = sqlite_cursor.fetchall()
    
    event_mapping = {}
    
    for event in backup_events:
        old_id = event['id']
        
        # Map backup columns to production columns safely
        event_data = {}
        
        # Required columns
        if 'name' in prod_event_cols:
            event_data['name'] = event['name']
        if 'date' in prod_event_cols:
            event_data['date'] = event['date']
        if 'time' in prod_event_cols:
            event_data['time'] = event['time'] if 'time' in event.keys() else None
        if 'created_at' in prod_event_cols:
            event_data['created_at'] = event['created_at'] if 'created_at' in event.keys() else datetime.now()
        
        # Optional columns - map based on what exists in production
        column_mapping = {
            'description': event['description'] if 'description' in event.keys() else '',
            'location': event['location'] if 'location' in event.keys() else '',
            'instructions': event['instructions'] if 'instructions' in event.keys() else '',
            'google_maps_url': event['google_maps_url'] if 'google_maps_url' in event.keys() else '',
            'alias_name': event['alias_name'] if 'alias_name' in event.keys() else '',
            'certificate_type': event['certificate_type'] if 'certificate_type' in event.keys() else 'completion',
            'organizer_name': event['organizer_name'] if 'organizer_name' in event.keys() else '',
            'organizer_logo_url': event['organizer_logo_url'] if 'organizer_logo_url' in event.keys() else '',
            'sponsor_name': event['sponsor_name'] if 'sponsor_name' in event.keys() else '',
            'sponsor_logo_url': event['sponsor_logo_url'] if 'sponsor_logo_url' in event.keys() else '',
            'event_location_cert': event['event_location_cert'] if 'event_location_cert' in event.keys() else '',
            'event_theme': event['event_theme'] if 'event_theme' in event.keys() else 'professional',
            'signature1_name': event['signature1_name'] if 'signature1_name' in event.keys() else '',
            'signature1_title': event['signature1_title'] if 'signature1_title' in event.keys() else '',
            'signature1_image_url': event['signature1_image_url'] if 'signature1_image_url' in event.keys() else '',
            'signature2_name': event['signature2_name'] if 'signature2_name' in event.keys() else '',
            'signature2_title': event['signature2_title'] if 'signature2_title' in event.keys() else '',
            'signature2_image_url': event['signature2_image_url'] if 'signature2_image_url' in event.keys() else '',
            'certificate_template': event['certificate_template'] if 'certificate_template' in event.keys() else 'professional',
            'certificate_config_updated': event['certificate_config_updated'] if 'certificate_config_updated' in event.keys() else None,
            'logo_filename': event['logo_filename'] if 'logo_filename' in event.keys() else '',
            'capacity': 1000  # Default capacity
        }
        
        # Add columns that exist in production
        for col_name, value in column_mapping.items():
            if col_name in prod_event_cols:
                event_data[col_name] = value
        
        # Special case: if production has 'venue' but backup has 'location'
        if 'venue' in prod_event_cols and 'location' in event:
            event_data['venue'] = event['location']
        
        # Build dynamic INSERT query
        columns = list(event_data.keys())
        placeholders = [f'%({col})s' for col in columns]
        
        insert_query = f"""
            INSERT INTO events ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING id
        """
        
        try:
            pg_cursor.execute(insert_query, event_data)
            new_id = pg_cursor.fetchone()['id']
            event_mapping[old_id] = new_id
            print(f"   ✅ Migrated: {event['name']} (ID: {old_id} → {new_id})")
        except Exception as e:
            print(f"   ❌ Failed to migrate event {old_id}: {e}")
            continue
    
    pg_conn.commit()
    sqlite_conn.close()
    pg_conn.close()
    
    return event_mapping

def migrate_participants_safe(event_mapping):
    """Migrate participants with schema-safe mapping"""
    print("\n👥 Migrating Participants (schema-safe)...")
    
    # Get production schema
    prod_schema = get_production_schema()
    prod_participant_cols = prod_schema['participants']
    
    print(f"   Production participant columns: {prod_participant_cols}")
    
    # Connect to databases
    sqlite_conn = sqlite3.connect('event_ticketing_bkp.db')
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    db_url = os.getenv('DATABASE_URL')
    pg_conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    pg_cursor = pg_conn.cursor()
    
    # Get backup participants
    sqlite_cursor.execute("SELECT * FROM participants")
    backup_participants = sqlite_cursor.fetchall()
    
    participant_mapping = {}
    migrated_count = 0
    
    for participant in backup_participants:
        old_id = participant['id']
        old_event_id = participant['event_id']
        
        # Skip if event wasn't migrated
        if old_event_id not in event_mapping:
            print(f"   ⚠️  Skipping participant {old_id}: Event {old_event_id} not migrated")
            continue
        
        new_event_id = event_mapping[old_event_id]
        
        # Map participant data safely
        participant_data = {}
        
        # Required columns
        if 'name' in prod_participant_cols:
            participant_data['name'] = participant['name']
        if 'email' in prod_participant_cols:
            participant_data['email'] = participant['email']
        if 'event_id' in prod_participant_cols:
            participant_data['event_id'] = new_event_id
        
        # Optional columns
        optional_mapping = {
            'checked_in': bool(participant['checked_in']) if 'checked_in' in participant.keys() else False,
            'checkin_time': participant['checkin_time'] if 'checkin_time' in participant.keys() else None,
            'ticket_sent': bool(participant['ticket_sent']) if 'ticket_sent' in participant.keys() else False,
            'created_at': participant['created_at'] if 'created_at' in participant.keys() else datetime.now(),
            'unique_id': participant['unique_id'] if 'unique_id' in participant.keys() else secrets.token_urlsafe(16)
        }
        
        # Add columns that exist in production
        for col_name, value in optional_mapping.items():
            if col_name in prod_participant_cols:
                participant_data[col_name] = value
        
        # Build dynamic INSERT query
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
            participant_mapping[old_id] = new_id
            migrated_count += 1
            
            if migrated_count % 50 == 0:
                print(f"   📊 Migrated {migrated_count} participants...")
                
        except Exception as e:
            print(f"   ❌ Failed to migrate participant {old_id}: {e}")
            pg_conn.rollback()  # Rollback the transaction
            # Restart connection to continue
            pg_conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
            pg_cursor = pg_conn.cursor()
            continue
    
    pg_conn.commit()
    sqlite_conn.close()
    pg_conn.close()
    
    print(f"   ✅ Successfully migrated {migrated_count} participants")
    return participant_mapping

def main():
    """Main migration function"""
    print("🚀 Starting Schema-Safe Migration")
    print("=" * 50)
    
    # Show what we're about to do
    response = input("This will migrate events and participants from backup to production. Continue? (y/N): ")
    if response.lower() != 'y':
        print("Migration cancelled.")
        return
    
    # Migrate events
    event_mapping = migrate_events_safe()
    if not event_mapping:
        print("❌ No events migrated. Stopping.")
        return
    
    # Migrate participants
    participant_mapping = migrate_participants_safe(event_mapping)
    
    print("\n" + "=" * 50)
    print(f"🎉 Migration completed!")
    print(f"   Events migrated: {len(event_mapping)}")
    print(f"   Participants migrated: {len(participant_mapping)}")
    print("You can now check your production database for the migrated data.")

if __name__ == "__main__":
    main()