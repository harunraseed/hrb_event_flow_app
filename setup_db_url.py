#!/usr/bin/env python3
"""
Database URL Configuration Helper
Helps configure the production database URL for migration
"""

import os
from dotenv import load_dotenv

def setup_database_url():
    """Interactive setup for database URL"""
    print("🔧 Database URL Configuration")
    print("=" * 40)
    
    print("You have several DATABASE_URL options commented in your .env file:")
    print("1. postgresql://postgres:[YOUR-PASSWORD]@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres")
    print("2. postgresql://postgres:harunraseed@db.gbhbretciwuuuftueotk.supabase.co:6543/postgres") 
    print("3. postgresql://postgres.gbhbretciwuuuftueotk:harunraseed@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres")
    
    print("\n⚠️  For migration, I need the correct production database URL.")
    print("Please choose one of the above or provide a new one:")
    
    choice = input("\nEnter choice (1/2/3) or 'c' for custom: ").strip().lower()
    
    if choice == '1':
        password = input("Enter your password for option 1: ")
        db_url = f"postgresql://postgres:{password}@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres"
    elif choice == '2':
        db_url = "postgresql://postgres:harunraseed@db.gbhbretciwuuuftueotk.supabase.co:6543/postgres"
    elif choice == '3':
        db_url = "postgresql://postgres.gbhbretciwuuuftueotk:harunraseed@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres"
    elif choice == 'c':
        db_url = input("Enter your complete DATABASE_URL: ").strip()
    else:
        print("Invalid choice")
        return None
    
    return db_url

def test_connection(db_url):
    """Test database connection"""
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        conn.close()
        print(f"✅ Connection successful! PostgreSQL version: {version[:50]}...")
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

def main():
    """Main function"""
    db_url = setup_database_url()
    if not db_url:
        return
    
    print(f"\n🔍 Testing connection...")
    if test_connection(db_url):
        print(f"\n✅ Database URL is working!")
        print(f"DATABASE_URL={db_url}")
        print(f"\nTo use this for migration:")
        print(f"1. Add this to your .env file:")
        print(f"   DATABASE_URL={db_url}")
        print(f"2. Run: python preflight_check.py")
        print(f"3. Run: python migrate_to_production.py")
    else:
        print(f"\n❌ Please check your database URL and try again")

if __name__ == "__main__":
    main()