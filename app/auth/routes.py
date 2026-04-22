'''

contains all the actual login, register, logout route functions

'''


from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db, bcrypt
from app.models import User, PasswordResetToken
from datetime import datetime, timedelta, timezone
from flask_mail import Message
from app.extensions import mail
import secrets

auth = Blueprint('auth', __name__)


# ─────────────────────────────────────────────
# Register
# ─────────────────────────────────────────────
@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('courses.index'))

    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name  = request.form.get('last_name')
        email      = request.form.get('email')
        password   = request.form.get('password')

        # Validate SCSU email
        if not email.endswith('@southernct.edu'):
            flash('You must use a Southern CT State University email.', 'danger')
            return redirect(url_for('auth.register'))

        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('An account with that email already exists.', 'danger')
            return redirect(url_for('auth.register'))

        # Hash password and create user
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(
            first_name    = first_name,
            last_name     = last_name,
            email         = email,
            password_hash = hashed_password,
            role          = 'user',
            is_active     = True,
            status        = 'active',
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


# ─────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────
@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('courses.index'))

    if request.method == 'POST':
        email    = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        # Check user exists and password is correct
        if not user or not bcrypt.check_password_hash(user.password_hash, password):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('auth.login'))

        # Check account is active
        if not user.is_active:
            flash('Your account has been deactivated.', 'danger')
            return redirect(url_for('auth.login'))
        
        # Block banned users from logging in
        if user.is_banned():
            flash(
                'Your account has been permanently banned. '
                'Reason: ' + (user.ban_reason or 'No reason provided.'),
                'danger'
            )
            return redirect(url_for('auth.login'))

        # Block suspended users from logging in
        if user.is_suspended():
            until = (
                user.suspended_until.strftime('%b %d, %Y at %I:%M %p')
                if user.suspended_until else 'an unspecified date'
            )
            flash(
                f'Your account is suspended until {until}. '
                f'Reason: {user.suspension_reason or "No reason provided."}',
                'danger'
            )
            return redirect(url_for('auth.login'))

        # Log the user in and update last login time
        login_user(user)
        user.last_login_at = datetime.utcnow()
        db.session.commit()

        flash(f'Welcome back, {user.first_name}!', 'success')
        return redirect(url_for('courses.index'))

    return render_template('auth/login.html')


# ─────────────────────────────────────────────
# Logout
# ─────────────────────────────────────────────
@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


# ─────────────────────────────────────────────
# Forgot Password
# ─────────────────────────────────────────────
@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user  = User.query.filter_by(email=email).first()

        # Always show success message even if email not found (security)
        if user:
            token     = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

            reset_token = PasswordResetToken(
                user_id    = user.user_id,
                token      = token,
                expires_at = expires_at
            )
            db.session.add(reset_token)
            db.session.commit()

            # TODO: Send email via SendGrid with reset link
            reset_link = url_for('auth.reset_password', token=token, _external=True)

            msg = Message(
                subject='RateMyClass — Password Reset',
                recipients=[user.email],
                html=f'''
                    <p>Hi {user.first_name},</p>
                    <p>Click the link below to reset your password. This link expires in 30 minutes.</p>
                    <p><a href="{reset_link}">{reset_link}</a></p>
                    <p>If you did not request this, ignore this email.</p>
                    '''
            )
            mail.send(msg)

        flash('If that email exists you will receive a reset link shortly.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


# ─────────────────────────────────────────────
# Reset Password
# ─────────────────────────────────────────────
@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    reset_token = PasswordResetToken.query.filter_by(token=token).first()

    if not reset_token or not reset_token.is_valid():
        flash('This reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('password')

        # Hash new password and update user
        reset_token.user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        reset_token.used_at = datetime.now(timezone.utc)
        db.session.commit()

        flash('Your password has been reset. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)


# ─────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────
@auth.route('/profile')
@login_required
def profile():
    from app.models import Review, ReviewLike, Material
    from sqlalchemy import func

    total_likes = (
        db.session.query(func.count(ReviewLike.like_id))
        .join(Review, ReviewLike.review_id == Review.review_id)
        .filter(
            Review.user_id == current_user.user_id,
            ReviewLike.like_type.in_(['really_helpful', 'helpful'])
        )
        .scalar() or 0
    )
    review_count   = Review.query.filter_by(user_id=current_user.user_id).count()
    material_count = Material.query.filter_by(
        user_id=current_user.user_id, is_removed=False
    ).count()

    return render_template('auth/profile.html',
        total_likes    = total_likes,
        review_count   = review_count,
        material_count = material_count,
    )


# ─────────────────────────────────────────────
# Edit Profile
# ─────────────────────────────────────────────
@auth.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio    = request.form.get('bio',    '').strip() or None
        current_user.school = request.form.get('school', '').strip() or None
        current_user.major  = request.form.get('major',  '').strip() or None
        current_user.minor  = request.form.get('minor',  '').strip() or None
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/edit_profile.html')


# ─────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────
@auth.route('/settings')
@login_required
def settings():
    return render_template('auth/settings.html')


@auth.route('/settings/change-email', methods=['POST'])
@login_required
def change_email():
    new_email = request.form.get('email', '').strip().lower()

    if not new_email.endswith('@southernct.edu'):
        flash('Email must end in @southernct.edu.', 'danger')
        return redirect(url_for('auth.settings'))

    existing = User.query.filter_by(email=new_email).first()
    if existing and existing.user_id != current_user.user_id:
        flash('That email is already associated with another account.', 'danger')
        return redirect(url_for('auth.settings'))

    current_user.email = new_email
    db.session.commit()
    flash('Email updated successfully.', 'success')
    return redirect(url_for('auth.settings'))


@auth.route('/settings/change-name', methods=['POST'])
@login_required
def change_name():
    first_name = request.form.get('first_name', '').strip()
    last_name  = request.form.get('last_name',  '').strip()

    if not first_name or not last_name:
        flash('Name cannot be empty.', 'danger')
        return redirect(url_for('auth.settings'))

    current_user.first_name = first_name
    current_user.last_name  = last_name
    db.session.commit()
    flash('Name updated successfully.', 'success')
    return redirect(url_for('auth.settings'))