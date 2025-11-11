import sys
import os

# Add parent directory to path so imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Global variable to store import error message
import_error_message = None

try:
    # Try to import the main Flask application
    from index import application as main_app
    app = main_app
    print("✅ Successfully imported main Flask app")
except ImportError as e:
    import_error_message = str(e)
    print(f"❌ Import error: {import_error_message}")
    # Create a simple fallback Flask app
    from flask import Flask, jsonify
    app = Flask(__name__)
    
    @app.route('/')
    def hello():
        return jsonify({
            "status": "error",
            "message": f"Failed to import main app: {import_error_message}",
            "python_version": sys.version,
            "path": sys.path[:3]  # Show first 3 paths for debugging
        })
    
    @app.route('/health')
    def health():
        return jsonify({"status": "ok", "message": "Fallback app running"})
    
    @app.route('/debug')
    def debug():
        import os
        parent_files = []
        try:
            parent_files = os.listdir(parent_dir)
        except:
            parent_files = ["Could not list parent directory"]
        
        return jsonify({
            "current_dir": current_dir,
            "parent_dir": parent_dir,
            "parent_files": parent_files,
            "sys_path": sys.path[:5],
            "import_error": import_error_message
        })

# Export for Vercel
application = app