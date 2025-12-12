"""
Script to generate a bcrypt password hash for resetting admin password.
Run this script to get a hash, then update it in Supabase.
"""
from flask_bcrypt import Bcrypt
from flask import Flask

app = Flask(__name__)
bcrypt = Bcrypt(app)

# Change this to your desired password
NEW_PASSWORD = "Admin@123"

# Generate the hash
password_hash = bcrypt.generate_password_hash(NEW_PASSWORD).decode('utf-8')

print("\n" + "="*60)
print("PASSWORD RESET HELPER")
print("="*60)
print(f"\nNew Password: {NEW_PASSWORD}")
print(f"\nBcrypt Hash: {password_hash}")
print("\n" + "="*60)
print("\nTo update in Supabase:")
print("1. Go to Supabase Table Editor")
print("2. Open 'users' table")
print("3. Find the 'admin' user")
print("4. Update the 'password_hash' column with the hash above")
print("="*60 + "\n")
