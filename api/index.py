import sys
import os

# Add parent directory to path so imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    # Try to import the main Flask application
    from index import application as main_app
    app = main_app
    print("✅ Successfully imported main Flask app")
except ImportError as e:
    print(f"❌ Import error: {e}")
    # Create a simple fallback Flask app
    from flask import Flask, jsonify
    app = Flask(__name__)
    
    @app.route('/')
    def hello():
        return jsonify({
            "status": "error",
            "message": f"Failed to import main app: {str(e)}",
            "python_version": sys.version
        })
    
    @app.route('/health')
    def health():
        return jsonify({"status": "ok", "message": "Fallback app running"})

# Export for Vercel
application = app