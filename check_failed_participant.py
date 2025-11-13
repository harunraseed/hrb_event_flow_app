#!/usr/bin/env python3
"""
Check the failed participant and understand why it failed
"""

import sqlite3

def check_failed_participant():
    """Check participant 165 that failed during migration"""
    conn = sqlite3.connect('event_ticketing_bkp.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Find the participant that failed (ID 165)
    cursor.execute('SELECT * FROM participants WHERE id = 165')
    failed_participant = cursor.fetchone()
    
    print("🔍 Failed Participant Analysis")
    print("=" * 40)
    
    if failed_participant:
        print(f"Participant ID: {failed_participant['id']}")
        print(f"Event ID: {failed_participant['event_id']}")
        print(f"Name: {failed_participant['name']}")
        print(f"Email: {failed_participant['email']}")
        print(f"Ticket Number: {failed_participant['ticket_number']}")
        print(f"Checked In: {failed_participant['checked_in']}")
        print(f"Check-in Time: {failed_participant['checkin_time']}")
        print(f"Created At: {failed_participant['created_at']}")
        
        event_id = failed_participant['event_id']
        
        # Check what event this participant belongs to
        cursor.execute('SELECT * FROM events WHERE id = ?', (event_id,))
        event = cursor.fetchone()
        
        print(f"\n🎪 Event Analysis (ID {event_id}):")
        if event:
            print(f"Name: {event['name']}")
            print(f"Description: {event['description'] if 'description' in event.keys() else 'N/A'}")
            print(f"Created At: {event['created_at'] if 'created_at' in event.keys() else 'N/A'}")
        else:
            print(f"❌ Event ID {event_id} not found in backup database!")
        
        # Check all events to see the full picture
        print(f"\n📊 All Events in Backup Database:")
        cursor.execute('SELECT id, name FROM events ORDER BY id')
        all_events = cursor.fetchall()
        for event in all_events:
            participant_count_cursor = conn.cursor()
            participant_count_cursor.execute('SELECT COUNT(*) FROM participants WHERE event_id = ?', (event['id'],))
            count = participant_count_cursor.fetchone()[0]
            print(f"  ID {event['id']}: {event['name']} ({count} participants)")
    else:
        print("❌ Participant ID 165 not found in backup database!")
    
    conn.close()

if __name__ == "__main__":
    check_failed_participant()