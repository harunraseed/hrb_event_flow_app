import sys
import os

# Add parent directory to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from index import application
    app = application
except ImportError as e:
    print(f"Import error: {e}")
    # Fallback: create a simple app
    from flask import Flask
    app = Flask(__name__)
    
    @app.route('/')
    def hello():
        return f"Import Error: {str(e)}"

# Vercel expects this exact export
application = app

# Also provide direct access
def handler(event, context):
    return app(event, context)