# backend/wsgi.py
from app import app as application

# Optional: Gunicorn looks for "application"
app = application
