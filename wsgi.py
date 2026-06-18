"""Gunicorn entry point.  Run: gunicorn wsgi:app --workers 1 --threads 4"""
from app import app

if __name__ == "__main__":
    app.run()
