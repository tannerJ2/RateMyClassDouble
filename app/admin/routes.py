import hashlib
from functools import wraps
from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Flag, FlagReason, Review, Material

admin = Blueprint('admin', __name__, url_prefix='/admin')


@admin.context_processor
def admin_context():
    if current_user.is_authenticated and current_user.is_admin():
        count = Flag.query.filter_by(status='pending').count()
        return dict(pending_flag_count=count)
    return dict(pending_flag_count=0)


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ──────────────────────────────────
@admin.route('/')
@admin_required
def dashboard():
    total_users      = User.query.count()
    active_users     = User.query.filter_by(status='active').count()
    suspended_users  = User.query.filter_by(status='suspended').count()
    banned_users     = User.query.filter_by(status='banned').count()
    pending_flags    = Flag.query.filter_by(status='pending').count()
    total_reviews    = Review.query.count()
    total_materials  = Material.query.count()
    removed_reviews  = Review.query.filter_by(is_removed=True).count()
    removed_materials = Material.query.filter_by(is_removed=True).count()

    recent_flags = (
        Flag.query.filter_by(status='pending')
        .order_by(Flag.created_at.desc())
        .limit(5).all()
    )
    recent_users = (
        User.query.order_by(User.created_at.desc())
        .limit(5).all()
    )

    return render_template('admin/dashboard.html',
        total_users=total_users, active_users=active_users,
        suspended_users=suspended_users, banned_users=banned_users,
        pending_flags=pending_flags, total_reviews=total_reviews,
        total_materials=total_materials, removed_reviews=removed_reviews,
        removed_materials=removed_materials, recent_flags=recent_flags,
        recent_users=recent_users,
    )


# ── User List ──────────────────────────────────
@admin.route('/users')
@admin_required
def user_list():
    status_filter = request.args.get('status', 'all')
    search_q      = request.args.get('q', '').strip()
    query         = User.query

    if status_filter == 'active':
        query = query.filter_by(status='active')
    elif status_filter == 'suspended':
        query = query.filter_by(status='suspended')
    elif status_filter == 'banned':
        query = query.filter_by(status='banned')
    elif status_filter == 'admin':
        query = query.filter_by(role='admin')

    if search_q:
        like = f'%{search_q}%'
        query = query.filter(
            db.or_(
                User.first_name.ilike(like),
                User.last_name.ilike(like),
                User.email.ilike(like),
            )
        )

    users = query.order_by(User.created_at.desc()).all()
    return render_template('admin/user_list.html',
        users=users, status_filter=status_filter, search_q=search_q,
    )


# ── User Detail ────────────────────────────────
@admin.route('/users/<int:user_id>')
@admin_required
def user_detail(user_id):
    user           = User.query.get_or_404(user_id)
    reviews        = user.reviews.order_by(Review.created_at.desc()).all()
    materials      = user.materials.order_by(Material.created_at.desc()).all()
    flags_reported = user.flags_reported.order_by(Flag.created_at.desc()).all()
    return render_template('admin/user_detail.html',
        user=user, reviews=reviews, materials=materials,
        flags_reported=flags_reported,
    )


# ── Suspend ────────────────────────────────────
@admin.route('/users/<int:user_id>/suspend', methods=['POST'])
@admin_required
def suspend_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.user_id == current_user.user_id:
        flash('You cannot suspend yourself.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    if user.is_admin():
        flash('You cannot suspend an admin.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))

    reason        = request.form.get('reason', '').strip()
    duration_days = request.form.get('duration', type=int, default=7)

    if not reason:
        flash('A reason is required for suspension.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))

    user.status           = 'suspended'
    user.suspension_reason = reason
    user.suspended_until  = datetime.now(timezone.utc) + timedelta(days=duration_days)
    user.status_changed_at = datetime.now(timezone.utc)
    user.status_changed_by = current_user.user_id
    db.session.commit()

    flash(f'{user.first_name} {user.last_name} suspended for {duration_days} days.', 'success')
    return redirect(url_for('admin.user_detail', user_id=user_id))


# ── Unsuspend ──────────────────────────────────
@admin.route('/users/<int:user_id>/unsuspend', methods=['POST'])
@admin_required
def unsuspend_user(user_id):
    user = User.query.get_or_404(user_id)
    user.status            = 'active'
    user.suspension_reason = None
    user.suspended_until   = None
    user.status_changed_at = datetime.now(timezone.utc)
    user.status_changed_by = current_user.user_id
    db.session.commit()
    flash(f'{user.first_name} {user.last_name} has been unsuspended.', 'success')
    return redirect(url_for('admin.user_detail', user_id=user_id))


# ── Ban ────────────────────────────────────────
@admin.route('/users/<int:user_id>/ban', methods=['POST'])
@admin_required
def ban_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.user_id == current_user.user_id:
        flash('You cannot ban yourself.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    if user.is_admin():
        if User.query.filter_by(role='admin', status='active').count() <= 1:
            flash('Cannot ban the last active admin.', 'danger')
            return redirect(url_for('admin.user_detail', user_id=user_id))

    reason = request.form.get('reason', '').strip()
    if not reason:
        flash('A reason is required for banning.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))

    user.status            = 'banned'
    user.ban_reason        = reason
    user.is_active         = False
    user.suspended_until   = None
    user.suspension_reason = None
    user.status_changed_at = datetime.now(timezone.utc)
    user.status_changed_by = current_user.user_id
    db.session.commit()
    flash(f'{user.first_name} {user.last_name} has been banned.', 'success')
    return redirect(url_for('admin.user_detail', user_id=user_id))


# ── Unban ──────────────────────────────────────
@admin.route('/users/<int:user_id>/unban', methods=['POST'])
@admin_required
def unban_user(user_id):
    user = User.query.get_or_404(user_id)
    user.status            = 'active'
    user.ban_reason        = None
    user.is_active         = True
    user.status_changed_at = datetime.now(timezone.utc)
    user.status_changed_by = current_user.user_id
    db.session.commit()
    flash(f'{user.first_name} {user.last_name} has been unbanned.', 'success')
    return redirect(url_for('admin.user_detail', user_id=user_id))


# ── Moderation Queue ───────────────────────────
@admin.route('/moderation')
@admin_required
def moderation():
    status_filter = request.args.get('status', 'pending')
    type_filter   = request.args.get('type',   'all')
    query         = Flag.query

    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if type_filter == 'review':
        query = query.filter(Flag.review_id.isnot(None))
    elif type_filter == 'material':
        query = query.filter(Flag.material_id.isnot(None))

    flags   = query.order_by(Flag.created_at.desc()).all()
    reasons = FlagReason.query.all()
    return render_template('admin/moderation.html',
        flags=flags, reasons=reasons,
        status_filter=status_filter, type_filter=type_filter,
    )


# ── Approve Flag (content stays) ───────────────
@admin.route('/moderation/<int:flag_id>/approve', methods=['POST'])
@admin_required
def approve_flag(flag_id):
    flag = Flag.query.get_or_404(flag_id)
    if flag.status != 'pending':
        flash('This flag has already been reviewed.', 'info')
        return redirect(url_for('admin.moderation'))
    flag.status               = 'dismissed'
    flag.reviewed_by_admin_id = current_user.user_id
    flag.reviewed_at          = datetime.now(timezone.utc)
    db.session.commit()
    flash('Flag dismissed — content approved.', 'success')
    return redirect(url_for('admin.moderation'))


# ── Remove Flagged Content ─────────────────────
@admin.route('/moderation/<int:flag_id>/remove', methods=['POST'])
@admin_required
def remove_flagged(flag_id):
    flag = Flag.query.get_or_404(flag_id)
    if flag.status != 'pending':
        flash('This flag has already been reviewed.', 'info')
        return redirect(url_for('admin.moderation'))

    flag.status               = 'reviewed'
    flag.reviewed_by_admin_id = current_user.user_id
    flag.reviewed_at          = datetime.now(timezone.utc)

    now = datetime.now(timezone.utc)
    if flag.material_id and flag.material:
        flag.material.is_removed = True
        flag.material.removed_at = now
    elif flag.review_id and flag.review:
        flag.review.is_removed = True
        flag.review.removed_at = now

    db.session.commit()
    flash('Content removed successfully.', 'success')
    return redirect(url_for('admin.moderation'))


# ── Restore Content ────────────────────────────
@admin.route('/moderation/<int:flag_id>/restore', methods=['POST'])
@admin_required
def restore_flagged(flag_id):
    flag = Flag.query.get_or_404(flag_id)
    if flag.material_id and flag.material:
        flag.material.is_removed = False
        flag.material.removed_at = None
    elif flag.review_id and flag.review:
        flag.review.is_removed = False
        flag.review.removed_at = None
    flag.status               = 'dismissed'
    flag.reviewed_by_admin_id = current_user.user_id
    flag.reviewed_at          = datetime.now(timezone.utc)
    db.session.commit()
    flash('Content restored successfully.', 'success')
    return redirect(url_for('admin.moderation'))


# ── Submit Flag (from course pages) ────────────
@admin.route('/flag', methods=['POST'])
def submit_flag():
    content_type = request.form.get('content_type')
    content_id   = request.form.get('content_id', type=int)
    reason_id    = request.form.get('reason_id',  type=int)
    details      = request.form.get('details', '').strip() or None

    if not content_type or not content_id or not reason_id:
        flash('Invalid flag submission.', 'danger')
        return redirect(request.referrer or url_for('courses.index'))

    reporter_user_id = None
    reporter_ip_hash = None

    if current_user.is_authenticated:
        reporter_user_id = current_user.user_id
        existing = Flag.query.filter_by(reporter_user_id=reporter_user_id)
        if content_type == 'review':
            existing = existing.filter_by(review_id=content_id).first()
        else:
            existing = existing.filter_by(material_id=content_id).first()
        if existing:
            flash('You have already flagged this content.', 'info')
            return redirect(request.referrer or url_for('courses.index'))
    else:
        ip               = request.remote_addr or '0.0.0.0'
        reporter_ip_hash = hashlib.sha256(ip.encode()).hexdigest()
        existing         = Flag.query.filter_by(reporter_ip_hash=reporter_ip_hash)
        if content_type == 'review':
            existing = existing.filter_by(review_id=content_id).first()
        else:
            existing = existing.filter_by(material_id=content_id).first()
        if existing:
            flash('You have already flagged this content.', 'info')
            return redirect(request.referrer or url_for('courses.index'))

    flag = Flag(
        material_id      = content_id if content_type == 'material' else None,
        review_id        = content_id if content_type == 'review'   else None,
        reporter_user_id = reporter_user_id,
        reporter_ip_hash = reporter_ip_hash,
        reason_id        = reason_id,
        details          = details,
    )
    db.session.add(flag)
    db.session.commit()
    flash('Your report has been submitted for review.', 'success')
    return redirect(request.referrer or url_for('courses.index'))