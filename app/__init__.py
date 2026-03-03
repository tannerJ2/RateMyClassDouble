'''

this is what turns the app folder into a Python package and 
is where Flask gets initialized and everything gets 
connected together

'''


from flask import Flask
from app.extensions import db, login_manager, bcrypt
from config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)

    # Register blueprints
    from app.auth.routes import auth
    from app.courses.routes import courses

    app.register_blueprint(auth)
    app.register_blueprint(courses)

    return app