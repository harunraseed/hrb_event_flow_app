"""
Database Migration Script for Participant Limit
Adds participant_limit column to quizzes table
"""

import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def run_migration():
    """Add participant_limit column to quizzes table"""
    
    # Get database URL
    if os.getenv('DATABASE_URL'):
        database_url = os.getenv('DATABASE_URL')
        print("Using PostgreSQL database")
    else:
        database_url = 'sqlite:///event_ticketing.db'
        print("Using SQLite database")
    
    try:
        # Create engine
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            # Check if column already exists
            if 'postgresql' in database_url:
                # PostgreSQL
                check_sql = """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'quizzes' AND column_name = 'participant_limit'
                """
            else:
                # SQLite
                check_sql = "PRAGMA table_info(quizzes)"
            
            result = conn.execute(text(check_sql))
            
            if 'postgresql' in database_url:
                column_exists = len(list(result)) > 0
            else:
                # For SQLite, check if participant_limit is in the columns
                columns = [row[1] for row in result]  # Column name is at index 1
                column_exists = 'participant_limit' in columns
            
            if column_exists:
                print("✅ Column 'participant_limit' already exists in quizzes table")
                return
            
            # Add the column
            if 'postgresql' in database_url:
                alter_sql = "ALTER TABLE quizzes ADD COLUMN participant_limit INTEGER DEFAULT 100"
            else:
                alter_sql = "ALTER TABLE quizzes ADD COLUMN participant_limit INTEGER DEFAULT 100"
            
            conn.execute(text(alter_sql))
            conn.commit()
            
            print("✅ Successfully added 'participant_limit' column to quizzes table")
            print("   Default value: 100")
            
    except Exception as e:
        print(f"❌ Error running migration: {str(e)}")
        return False
    
    return True

if __name__ == "__main__":
    print("🔄 Running database migration...")
    success = run_migration()
    if success:
        print("🎉 Migration completed successfully!")
    else:
        print("💥 Migration failed!")
        sys.exit(1)