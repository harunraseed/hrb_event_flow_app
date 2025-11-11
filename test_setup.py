#!/usr/bin/env python3
"""
Test script to verify event ticketing functionality
"""
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test if all required modules can be imported"""
    try:
        import flask
        print("✅ Flask imported successfully")
        
        import flask_sqlalchemy
        print("✅ Flask-SQLAlchemy imported successfully")
        
        import flask_mail
        print("✅ Flask-Mail imported successfully")
        
        import flask_wtf
        print("✅ Flask-WTF imported successfully")
        
        import wtforms
        print("✅ WTForms imported successfully")
        
        import email_validator
        print("✅ email_validator imported successfully")
        
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_email_config():
    """Test email configuration"""
    from dotenv import load_dotenv
    load_dotenv()
    
    config = {
        'MAIL_SERVER': os.getenv('MAIL_SERVER'),
        'MAIL_PORT': os.getenv('MAIL_PORT'),
        'MAIL_USERNAME': os.getenv('MAIL_USERNAME'),
        'MAIL_PASSWORD': os.getenv('MAIL_PASSWORD'),
        'MAIL_DEFAULT_SENDER': os.getenv('MAIL_DEFAULT_SENDER'),
    }
    
    print("\n📧 Email Configuration:")
    for key, value in config.items():
        if key == 'MAIL_PASSWORD':
            print(f"  {key}: {'*' * len(value) if value else 'Not set'}")
        else:
            print(f"  {key}: {value}")
    
    missing = [k for k, v in config.items() if not v]
    if missing:
        print(f"❌ Missing email config: {missing}")
        return False
    else:
        print("✅ Email configuration complete")
        return True

def main():
    """Run all tests"""
    print("🧪 Testing Event Ticketing Application\n")
    
    # Test imports
    if not test_imports():
        return False
    
    # Test email config
    if not test_email_config():
        return False
    
    print("\n✅ All tests passed! Your application should be working correctly.")
    print("\n🚀 To start the application:")
    print("   python index.py")
    print("\n📱 Then visit: http://localhost:5000")
    
    return True

if __name__ == "__main__":
    main()