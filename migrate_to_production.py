#!/usr/bin/env python3
"""
Data Migration Script: Local SQLite to Production PostgreSQL
Migrates events, participants, and certificates from backup database to production
"""

import sqlite3
import os
import sys
import json
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib
import secrets
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class DataMigrator:
    def __init__(self):
        self.backup_db = 'event_ticketing_bkp.db'
        self.production_db_url = os.getenv('DATABASE_URL')
        
        if not self.production_db_url:
            print("❌ DATABASE_URL not found in environment variables!")
            print("Please ensure you have the production database URL set.")
            sys.exit(1)
        
        # Connect to both databases
        self.sqlite_conn = None
        self.pg_conn = None
        
    def connect_databases(self):
        """Connect to both SQLite backup and PostgreSQL production databases"""
        try:
            # SQLite connection
            if not os.path.exists(self.backup_db):
                print(f"❌ Backup database '{self.backup_db}' not found!")
                return False
            
            self.sqlite_conn = sqlite3.connect(self.backup_db)
            self.sqlite_conn.row_factory = sqlite3.Row  # Enable row access by column name
            print("✅ Connected to SQLite backup database")
            
            # PostgreSQL connection
            self.pg_conn = psycopg2.connect(
                self.production_db_url,
                cursor_factory=RealDictCursor
            )
            print("✅ Connected to PostgreSQL production database")
            
            return True
            
        except Exception as e:
            print(f"❌ Database connection error: {e}")
            return False
    
    def check_production_data(self):
        """Check what data already exists in production"""
        try:
            cursor = self.pg_conn.cursor()
            
            # Check events
            cursor.execute("SELECT COUNT(*) as count FROM events")
            event_count = cursor.fetchone()['count']
            
            # Check participants
            cursor.execute("SELECT COUNT(*) as count FROM participants")
            participant_count = cursor.fetchone()['count']
            
            # Check certificates
            cursor.execute("SELECT COUNT(*) as count FROM certificates")
            cert_count = cursor.fetchone()['count']
            
            print(f"\n📊 Production Database Status:")
            print(f"   Events: {event_count}")
            print(f"   Participants: {participant_count}")
            print(f"   Certificates: {cert_count}")
            
            if event_count > 0 or participant_count > 0:
                response = input(f"\n⚠️  Production database has existing data. Continue anyway? (y/N): ")
                if response.lower() != 'y':
                    return False
            
            return True
            
        except Exception as e:
            print(f"❌ Error checking production data: {e}")
            return False
    
    def migrate_events(self):
        """Migrate events from backup to production"""
        try:
            sqlite_cursor = self.sqlite_conn.cursor()
            pg_cursor = self.pg_conn.cursor()
            
            print("\n🎪 Migrating Events...")
            
            # Get all events from backup
            sqlite_cursor.execute("SELECT * FROM events")
            events = sqlite_cursor.fetchall()
            
            event_id_mapping = {}  # Map old IDs to new IDs
            
            for event in events:
                # Convert SQLite row to dict
                event_data = dict(event)
                old_id = event_data['id']
                
                # Prepare data for PostgreSQL (exclude id for auto-increment)
                insert_data = {
                    'name': event_data['name'],
                    'date': event_data['date'],
                    'time': event_data.get('time'),
                    'venue': event_data.get('location', ''),  # Map location to venue
                    'capacity': 1000,  # Default capacity
                    'description': event_data.get('description', ''),
                    'instructions': event_data.get('instructions', ''),
                    'google_maps_url': event_data.get('google_maps_url', ''),
                    'alias_name': event_data.get('alias_name', ''),
                    'certificate_type': event_data.get('certificate_type', 'completion'),
                    'organizer_name': event_data.get('organizer_name', ''),
                    'organizer_logo_url': event_data.get('organizer_logo_url', ''),
                    'sponsor_name': event_data.get('sponsor_name', ''),
                    'sponsor_logo_url': event_data.get('sponsor_logo_url', ''),
                    'event_location_cert': event_data.get('event_location_cert', ''),
                    'event_theme': event_data.get('event_theme', 'professional'),
                    'signature1_name': event_data.get('signature1_name', ''),
                    'signature1_title': event_data.get('signature1_title', ''),
                    'signature1_image_url': event_data.get('signature1_image_url', ''),
                    'signature2_name': event_data.get('signature2_name', ''),
                    'signature2_title': event_data.get('signature2_title', ''),
                    'signature2_image_url': event_data.get('signature2_image_url', ''),
                    'certificate_template': event_data.get('certificate_template', 'professional'),
                    'certificate_config_updated': event_data.get('certificate_config_updated'),
                    'logo_filename': event_data.get('logo_filename', ''),
                    'created_at': event_data.get('created_at', datetime.now())
                }
                
                # Insert into PostgreSQL and get new ID
                insert_query = """
                    INSERT INTO events (name, date, time, venue, capacity, description, instructions,
                                      google_maps_url, alias_name, certificate_type, organizer_name,
                                      organizer_logo_url, sponsor_name, sponsor_logo_url, event_location_cert,
                                      event_theme, signature1_name, signature1_title, signature1_image_url,
                                      signature2_name, signature2_title, signature2_image_url,
                                      certificate_template, certificate_config_updated, logo_filename, created_at)
                    VALUES (%(name)s, %(date)s, %(time)s, %(venue)s, %(capacity)s, %(description)s, %(instructions)s,
                           %(google_maps_url)s, %(alias_name)s, %(certificate_type)s, %(organizer_name)s,
                           %(organizer_logo_url)s, %(sponsor_name)s, %(sponsor_logo_url)s, %(event_location_cert)s,
                           %(event_theme)s, %(signature1_name)s, %(signature1_title)s, %(signature1_image_url)s,
                           %(signature2_name)s, %(signature2_title)s, %(signature2_image_url)s,
                           %(certificate_template)s, %(certificate_config_updated)s, %(logo_filename)s, %(created_at)s)
                    RETURNING id
                """
                
                pg_cursor.execute(insert_query, insert_data)
                new_id = pg_cursor.fetchone()['id']
                event_id_mapping[old_id] = new_id
                
                print(f"   ✅ Migrated event: {event_data['name']} (ID: {old_id} → {new_id})")
            
            self.pg_conn.commit()
            print(f"✅ Successfully migrated {len(events)} events")
            return event_id_mapping
            
        except Exception as e:
            print(f"❌ Error migrating events: {e}")
            self.pg_conn.rollback()
            return None
    
    def migrate_participants(self, event_id_mapping):
        """Migrate participants from backup to production"""
        try:
            sqlite_cursor = self.sqlite_conn.cursor()
            pg_cursor = self.pg_conn.cursor()
            
            print("\n👥 Migrating Participants...")
            
            # Get all participants from backup
            sqlite_cursor.execute("SELECT * FROM participants")
            participants = sqlite_cursor.fetchall()
            
            participant_id_mapping = {}
            migrated_count = 0
            
            for participant in participants:
                participant_data = dict(participant)
                old_id = participant_data['id']
                old_event_id = participant_data['event_id']
                
                # Skip if event wasn't migrated
                if old_event_id not in event_id_mapping:
                    print(f"   ⚠️  Skipping participant {old_id}: Event {old_event_id} not found")
                    continue
                
                new_event_id = event_id_mapping[old_event_id]
                
                # Prepare participant data
                insert_data = {
                    'name': participant_data['name'],
                    'email': participant_data['email'],
                    'event_id': new_event_id,
                    'checked_in': participant_data.get('checked_in', False),
                    'checkin_time': participant_data.get('checkin_time'),
                    'ticket_sent': participant_data.get('ticket_sent', False),
                    'created_at': participant_data.get('created_at', datetime.now()),
                    'unique_id': participant_data.get('unique_id') or secrets.token_urlsafe(16)
                }
                
                # Insert participant
                insert_query = """
                    INSERT INTO participants (name, email, event_id, checked_in, checkin_time, 
                                            ticket_sent, created_at, unique_id)
                    VALUES (%(name)s, %(email)s, %(event_id)s, %(checked_in)s, %(checkin_time)s,
                           %(ticket_sent)s, %(created_at)s, %(unique_id)s)
                    RETURNING id
                """
                
                pg_cursor.execute(insert_query, insert_data)
                new_id = pg_cursor.fetchone()['id']
                participant_id_mapping[old_id] = new_id
                migrated_count += 1
                
                if migrated_count % 50 == 0:
                    print(f"   📊 Migrated {migrated_count} participants...")
            
            self.pg_conn.commit()
            print(f"✅ Successfully migrated {migrated_count} participants")
            return participant_id_mapping
            
        except Exception as e:
            print(f"❌ Error migrating participants: {e}")
            self.pg_conn.rollback()
            return None
    
    def migrate_certificates(self, participant_id_mapping):
        """Migrate certificates from backup to production"""
        try:
            sqlite_cursor = self.sqlite_conn.cursor()
            pg_cursor = self.pg_conn.cursor()
            
            print("\n🏆 Migrating Certificates...")
            
            # Get all certificates from backup
            sqlite_cursor.execute("SELECT * FROM certificates")
            certificates = sqlite_cursor.fetchall()
            
            migrated_count = 0
            
            for certificate in certificates:
                cert_data = dict(certificate)
                old_participant_id = cert_data['participant_id']
                
                # Skip if participant wasn't migrated
                if old_participant_id not in participant_id_mapping:
                    continue
                
                new_participant_id = participant_id_mapping[old_participant_id]
                
                # Prepare certificate data
                insert_data = {
                    'participant_id': new_participant_id,
                    'certificate_data': cert_data.get('certificate_data', ''),
                    'generated_at': cert_data.get('generated_at', datetime.now()),
                    'pdf_filename': cert_data.get('pdf_filename', ''),
                    'unique_id': cert_data.get('unique_id') or secrets.token_urlsafe(16)
                }
                
                # Insert certificate
                insert_query = """
                    INSERT INTO certificates (participant_id, certificate_data, generated_at, 
                                            pdf_filename, unique_id)
                    VALUES (%(participant_id)s, %(certificate_data)s, %(generated_at)s,
                           %(pdf_filename)s, %(unique_id)s)
                """
                
                pg_cursor.execute(insert_query, insert_data)
                migrated_count += 1
            
            self.pg_conn.commit()
            print(f"✅ Successfully migrated {migrated_count} certificates")
            return True
            
        except Exception as e:
            print(f"❌ Error migrating certificates: {e}")
            self.pg_conn.rollback()
            return False
    
    def verify_migration(self):
        """Verify the migration was successful"""
        try:
            sqlite_cursor = self.sqlite_conn.cursor()
            pg_cursor = self.pg_conn.cursor()
            
            print("\n🔍 Verifying Migration...")
            
            # Compare record counts
            tables = ['events', 'participants', 'certificates']
            
            for table in tables:
                sqlite_cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
                sqlite_count = sqlite_cursor.fetchone()[0]
                
                pg_cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
                pg_count = pg_cursor.fetchone()['count']
                
                status = "✅" if sqlite_count == pg_count else "❌"
                print(f"   {status} {table}: {sqlite_count} (backup) → {pg_count} (production)")
            
            return True
            
        except Exception as e:
            print(f"❌ Error verifying migration: {e}")
            return False
    
    def close_connections(self):
        """Close database connections"""
        if self.sqlite_conn:
            self.sqlite_conn.close()
        if self.pg_conn:
            self.pg_conn.close()
        print("\n🔌 Database connections closed")
    
    def run_migration(self):
        """Run the complete migration process"""
        print("🚀 Starting Data Migration from SQLite to PostgreSQL")
        print("=" * 60)
        
        # Connect to databases
        if not self.connect_databases():
            return False
        
        # Check production data
        if not self.check_production_data():
            return False
        
        # Run migrations
        event_mapping = self.migrate_events()
        if not event_mapping:
            return False
        
        participant_mapping = self.migrate_participants(event_mapping)
        if not participant_mapping:
            return False
        
        if not self.migrate_certificates(participant_mapping):
            return False
        
        # Verify migration
        self.verify_migration()
        
        print("\n" + "=" * 60)
        print("🎉 Migration completed successfully!")
        print("You can now access your events and participants in production.")
        
        return True

def main():
    """Main function"""
    migrator = DataMigrator()
    
    try:
        success = migrator.run_migration()
        if not success:
            print("\n❌ Migration failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
    finally:
        migrator.close_connections()

if __name__ == "__main__":
    main()