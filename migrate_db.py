#!/usr/bin/env python
"""
Database migration script to add new columns to events table.
This preserves existing data while adding new fields.
"""

import sqlite3
import os

DB_PATH = 'event_ticketing.db'

def migrate_database():
    """Add new columns to events table if they don't exist"""

    if not os.path.exists(DB_PATH):
        print(f"⚠️  Database file '{DB_PATH}' not found!")
        print("   The database will be created automatically when you run the application.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get current columns in events table
    cursor.execute("PRAGMA table_info(events)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    print(f"📊 Current columns in 'events' table:")
    for col in sorted(existing_columns):
        print(f"   - {col}")
    print()

    # New columns to add
    new_columns = {
        'event_end_time': 'TIME',
        'community': 'VARCHAR(100)',
        'speakers': 'TEXT',
        'event_official_link': 'TEXT',
        'organizer_name': 'VARCHAR(200)'
    }

    columns_added = []
    for column_name, column_type in new_columns.items():
        if column_name not in existing_columns:
            try:
                alter_sql = f"ALTER TABLE events ADD COLUMN {column_name} {column_type}"
                cursor.execute(alter_sql)
                columns_added.append(column_name)
                print(f"✅ Added column: {column_name} ({column_type})")
            except sqlite3.Error as e:
                print(f"❌ Error adding {column_name}: {e}")
        else:
            print(f"⏭️  Column already exists: {column_name}")

    conn.commit()
    conn.close()

    print()
    if columns_added:
        print(f"✨ Migration complete! Added {len(columns_added)} new column(s).")
    else:
        print("ℹ️  No new columns needed. Database is already up to date.")

if __name__ == '__main__':
    migrate_database()
