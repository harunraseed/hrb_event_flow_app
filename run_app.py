#!/usr/bin/env python3
"""
Quick test script to run the Flask application
"""
import subprocess
import sys
import os

def main():
    # Change to the app directory
    app_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(app_dir)
    
    # Check if virtual environment exists
    venv_python = os.path.join('.venv', 'Scripts', 'python.exe')
    if os.path.exists(venv_python):
        print("🚀 Starting Flask application...")
        try:
            subprocess.run([venv_python, 'index.py'], check=True)
        except KeyboardInterrupt:
            print("\n✋ Application stopped by user")
        except Exception as e:
            print(f"❌ Error running application: {e}")
    else:
        print("❌ Virtual environment not found. Please run 'python -m venv .venv' and install requirements.")

if __name__ == "__main__":
    main()