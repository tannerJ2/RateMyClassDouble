'''

This file initializes and configures Flask extensions used across the application.

'''


from flask_sqlalchemy import SQLAlchemy # for database interactions
from flask_login import LoginManager
from flask_bcrypt import Bcrypt

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()

login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'