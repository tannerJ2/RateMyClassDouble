'''

this is what turns the app folder into a Python package and 
is where Flask gets initialized and everything gets 
connected together

'''

from flask import Flask, redirect, url_for, flash
from flask_login import current_user, logout_user
from app.extensions import db, login_manager, bcrypt, mail
from config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)

    # Register blueprints
    from app.auth.routes import auth
    from app.courses.routes import courses
    from app.admin.routes import admin

    app.register_blueprint(auth)
    app.register_blueprint(courses)
    app.register_blueprint(admin)

    @app.before_request
    def enforce_user_status():
        if current_user.is_authenticated:
            if current_user.is_banned():
                logout_user()
                flash('Your account has been permanently banned.', 'danger')
                return redirect(url_for('auth.login'))

            pre_check_status = current_user.status
            if current_user.is_suspended():
                logout_user()
                flash('Your account is currently suspended.', 'danger')
                return redirect(url_for('auth.login'))

            if pre_check_status == 'suspended' and current_user.status == 'active':
                db.session.commit()

    return app