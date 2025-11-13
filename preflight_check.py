#!/usr/bin/env python3
"""
Pre-flight Check: Verify migration readiness and schema compatibility
"""

import sqlite3
import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

def check_backup_database():
    """Check the backup database structure and content"""
    print("1️⃣ Checking Backup Database...")
    
    if not os.path.exists('event_ticketing_bkp.db'):
        print("   ❌ Backup database 'event_ticketing_bkp.db' not found!")
        return False
    
    try:
        conn = sqlite3.connect('event_ticketing_bkp.db')
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        table_names = [t[0] for t in tables]
        
        required_tables = ['events', 'participants']
        missing_tables = [t for t in required_tables if t not in table_names]
        
        if missing_tables:
            print(f"   ❌ Missing required tables: {missing_tables}")
            return False
        
        # Check data
        for table in required_tables:
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            count = cursor.fetchone()[0]
            print(f"   ✅ {table}: {count} records")
            
            if count == 0:
                print(f"   ⚠️  Warning: {table} table is empty")
        
        # Check events structure
        cursor.execute('PRAGMA table_info(events)')
        event_columns = [col[1] for col in cursor.fetchall()]
        required_event_cols = ['id', 'name', 'date']
        missing_cols = [col for col in required_event_cols if col not in event_columns]
        
        if missing_cols:
            print(f"   ❌ Events table missing columns: {missing_cols}")
            return False
        
        # Check participants structure  
        cursor.execute('PRAGMA table_info(participants)')
        participant_columns = [col[1] for col in cursor.fetchall()]
        required_participant_cols = ['id', 'name', 'email', 'event_id']
        missing_cols = [col for col in required_participant_cols if col not in participant_columns]
        
        if missing_cols:
            print(f"   ❌ Participants table missing columns: {missing_cols}")
            return False
        
        conn.close()
        print("   ✅ Backup database structure is valid")
        return True
        
    except Exception as e:
        print(f"   ❌ Error checking backup database: {e}")
        return False

def check_production_database():
    """Check the production database connectivity and schema"""
    print("\n2️⃣ Checking Production Database...")
    
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("   ❌ DATABASE_URL environment variable not found!")
        print("   Please set your production database URL in .env file")
        return False
    
    try:
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        # Check if required tables exist
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name IN ('events', 'participants', 'certificates')
        """)
        tables = cursor.fetchall()
        table_names = [t['table_name'] for t in tables]
        
        required_tables = ['events', 'participants']
        missing_tables = [t for t in required_tables if t not in table_names]
        
        if missing_tables:
            print(f"   ❌ Missing tables in production: {missing_tables}")
            print("   Please run your Flask app once to create the schema")
            return False
        
        # Check current data
        for table in ['events', 'participants', 'certificates']:
            if table in table_names:
                cursor.execute(f'SELECT COUNT(*) as count FROM {table}')
                count = cursor.fetchone()['count']
                print(f"   📊 {table}: {count} records")
        
        conn.close()
        print("   ✅ Production database is accessible and ready")
        return True
        
    except Exception as e:
        print(f"   ❌ Error connecting to production database: {e}")
        return False

def check_environment():
    """Check environment and dependencies"""
    print("\n3️⃣ Checking Environment...")
    
    # Check required packages
    try:
        import psycopg2
        print("   ✅ psycopg2 (PostgreSQL adapter) available")
    except ImportError:
        print("   ❌ psycopg2 not installed. Run: pip install psycopg2-binary")
        return False
    
    try:
        import dotenv
        print("   ✅ python-dotenv available")
    except ImportError:
        print("   ❌ python-dotenv not installed. Run: pip install python-dotenv")
        return False
    
    # Check .env file
    if os.path.exists('.env'):
        print("   ✅ .env file found")
    else:
        print("   ⚠️  .env file not found - make sure DATABASE_URL is set")
    
    return True

def main():
    """Main pre-flight check"""
    print("🛫 Pre-flight Check for Data Migration")
    print("=" * 50)
    
    checks = [
        check_backup_database,
        check_production_database, 
        check_environment
    ]
    
    all_passed = True
    for check in checks:
        if not check():
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 All checks passed! Ready to run migration.")
        print("\nTo start migration, run:")
        print("   python migrate_to_production.py")
    else:
        print("❌ Some checks failed. Please fix the issues above before migrating.")
    
    return all_passed

if __name__ == "__main__":
    main()