"""
WSGI entry point for the Flask application.
This file is used by Gunicorn to serve the application.
"""

from app import app

if __name__ == "__main__":
    app.run()
