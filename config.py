'''

stores all your app settings and configuration, like database 
connection info, secret keys, etc.

'''

import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production' # In production, set this to a secure random value and keep it secret
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'mysql+pymysql://root:257536@localhost/ratemyclass' # Update with your actual database credentials || will be different for each of us 
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB file upload limit for now
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = False  # Set to True in production for now