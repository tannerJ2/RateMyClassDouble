'''

stores all your app settings and configuration, like database 
connection info, secret keys, etc.

'''

import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB

    # Local fallback for dev — ignored when USE_GCS is True
    MATERIAL_UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'uploads', 'materials')

    # Google Cloud Storage
    USE_GCS                  = os.environ.get('USE_GCS', 'false').lower() == 'true'
    GCS_BUCKET_NAME          = os.environ.get('GCS_BUCKET_NAME', '')
    GOOGLE_APPLICATION_CREDENTIALS = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '')

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE   = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'

    MAIL_SERVER         = 'smtp.gmail.com'
    MAIL_PORT           = 587
    MAIL_USE_TLS        = True
    MAIL_USERNAME       = 'ratemyclasspswreset@gmail.com'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = 'RateMyClassPswReset@gmail.com'