# Simple test to verify imports work correctly on Vercel
try:
    from flask import Flask
    print("✓ Flask imported successfully")
    
    from flask_sqlalchemy import SQLAlchemy
    print("✓ Flask-SQLAlchemy imported successfully")
    
    from flask_mail import Mail, Message
    print("✓ Flask-Mail imported successfully")
    
    from flask_wtf import FlaskForm
    print("✓ Flask-WTF imported successfully")
    
    import requests
    print("✓ Requests imported successfully")
    
    print("✅ All dependencies imported successfully!")
    
except ImportError as e:
    print(f"❌ Import error: {e}")