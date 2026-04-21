'''
Database models for RateMyClass.
All SQLAlchemy table definitions live here.
'''

from datetime import datetime, timezone
from flask_login import UserMixin
from app.extensions import db, login_manager


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─────────────────────────────────────────────
# CourseProfessor — many-to-many join table
# A course can have many professors; a professor can teach many courses.
# ─────────────────────────────────────────────
course_professor = db.Table(
    'course_professor',
    db.Column('course_id',    db.Integer, db.ForeignKey('course.course_id',       ondelete='CASCADE'), nullable=False),
    db.Column('professor_id', db.Integer, db.ForeignKey('professor.professor_id', ondelete='CASCADE'), nullable=False),
    db.UniqueConstraint('course_id', 'professor_id', name='uq_course_professor')
)


# ─────────────────────────────────────────────
# User
# ─────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    user_id       = db.Column(db.Integer,      primary_key=True, autoincrement=True)
    first_name    = db.Column(db.String(100),  nullable=False)
    last_name     = db.Column(db.String(100),  nullable=False)
    email         = db.Column(db.String(255),  unique=True, nullable=False)
    password_hash = db.Column(db.String(255),  nullable=False)
    role          = db.Column(db.Enum('user', 'admin'), default='user', nullable=False)
    is_active          = db.Column(db.Boolean,      default=True, nullable=False)
    status             = db.Column(db.Enum('active', 'suspended', 'banned'), default='active', nullable=False)
    suspended_until    = db.Column(db.DateTime,  nullable=True)
    suspension_reason  = db.Column(db.Text,      nullable=True)
    ban_reason         = db.Column(db.Text,      nullable=True)
    status_changed_at  = db.Column(db.DateTime,  nullable=True)
    status_changed_by  = db.Column(db.Integer,   db.ForeignKey('users.user_id'), nullable=True)
    created_at    = db.Column(db.DateTime,     default=datetime.now(timezone.utc), nullable=False)
    last_login_at = db.Column(db.DateTime,     nullable=True)

    bio    = db.Column(db.Text,        nullable=True)
    school = db.Column(db.String(255), nullable=True)
    major  = db.Column(db.String(100), nullable=True)
    minor  = db.Column(db.String(100), nullable=True)

    reviews         = db.relationship('Review',              back_populates='user',    lazy='dynamic')
    review_likes    = db.relationship('ReviewLike',          back_populates='user',    lazy='dynamic')
    material_likes  = db.relationship('MaterialLike',        back_populates='user',    lazy='dynamic')
    materials       = db.relationship('Material',            back_populates='user',    lazy='dynamic')
    flags_reported  = db.relationship('Flag',                foreign_keys='Flag.reporter_user_id',     back_populates='reporter',          lazy='dynamic')
    flags_reviewed  = db.relationship('Flag',                foreign_keys='Flag.reviewed_by_admin_id', back_populates='reviewed_by_admin', lazy='dynamic')
    reset_tokens    = db.relationship('PasswordResetToken',  back_populates='user',    lazy='dynamic')
    saved_courses   = db.relationship('SavedCourse',         back_populates='user',    lazy='dynamic')
    saved_materials = db.relationship('SavedMaterial',       back_populates='user',    lazy='dynamic')

    def get_id(self):
        return str(self.user_id)

    def is_admin(self):
        return self.role == 'admin'

    def is_banned(self):
        return self.status == 'banned'

    def is_suspended(self):
        if self.status != 'suspended':
            return False
        if self.suspended_until and datetime.now(timezone.utc) >= self.suspended_until:
            self.status = 'active'
            self.suspended_until = None
            self.suspension_reason = None
            return False
        return True

    def __repr__(self):
        return f'<User {self.email}>'


# ─────────────────────────────────────────────
# Department
# ─────────────────────────────────────────────
class Department(db.Model):
    __tablename__ = 'department'

    dept_id   = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    dept_code = db.Column(db.String(10),  unique=True, nullable=False)
    dept_name = db.Column(db.String(255), nullable=False)

    courses = db.relationship('Course', back_populates='department', lazy='dynamic')

    def __repr__(self):
        return f'<Department {self.dept_code}>'


# ─────────────────────────────────────────────
# Professor
# ─────────────────────────────────────────────
class Professor(db.Model):
    __tablename__ = 'professor'

    professor_id = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    full_name    = db.Column(db.String(255),  nullable=False, unique=True)

    courses = db.relationship('Course', secondary=course_professor, back_populates='professors', lazy='dynamic')

    def __repr__(self):
        return f'<Professor {self.full_name}>'


# ─────────────────────────────────────────────
# Course
# ─────────────────────────────────────────────
class Course(db.Model):
    __tablename__ = 'course'

    course_id          = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    dept_id            = db.Column(db.Integer,     db.ForeignKey('department.dept_id'), nullable=False, index=True)
    course_number      = db.Column(db.String(20),  nullable=False, index=True)
    course_title       = db.Column(db.String(255), nullable=False)
    course_description = db.Column(db.Text,        nullable=True)
    created_at         = db.Column(db.DateTime,    default=datetime.now(timezone.utc), nullable=False)

    department = db.relationship('Department', back_populates='courses')
    professors = db.relationship('Professor',  secondary=course_professor, back_populates='courses', lazy='dynamic')
    reviews    = db.relationship('Review',     back_populates='course',    lazy='dynamic')
    materials      = db.relationship('Material',    back_populates='course',    lazy='dynamic')
    saved_by_users = db.relationship('SavedCourse', back_populates='course',    lazy='dynamic')

    def __repr__(self):
        return f'<Course {self.course_number} - {self.course_title}>'


# ─────────────────────────────────────────────
# Semester
# ─────────────────────────────────────────────
class Semester(db.Model):
    __tablename__ = 'semester'

    semester_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    term        = db.Column(db.Enum('Spring', 'Summer', 'Fall', 'Winter'), nullable=False)
    year        = db.Column(db.Integer, nullable=False, index=True)

    reviews   = db.relationship('Review',   back_populates='semester', lazy='dynamic')
    materials = db.relationship('Material', back_populates='semester', lazy='dynamic')

    def __repr__(self):
        return f'<Semester {self.term} {self.year}>'


# ─────────────────────────────────────────────
# Review
# Handles both Opinions and Descriptions.
#
# review_type = 'opinion'
#   semester_id, rating_overall, workload_level, difficulty_level are required.
#   assessment_style is optional.
#
# review_type = 'description'
#   All rating fields and semester_id are null — factual text only.
#
# One opinion and one description allowed per user per course.
# ─────────────────────────────────────────────
class Review(db.Model):
    __tablename__ = 'review'

    __table_args__ = (
        db.UniqueConstraint('user_id', 'course_id', 'review_type', name='uq_review_user_course_type'),
    )

    review_id        = db.Column(db.Integer,                                        primary_key=True, autoincrement=True)
    course_id        = db.Column(db.Integer, db.ForeignKey('course.course_id'),     nullable=False, index=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.user_id'),        nullable=False, index=True)
    review_type      = db.Column(db.Enum('opinion', 'description', 'rating'),                 nullable=False, index=True)
    semester_id      = db.Column(db.Integer, db.ForeignKey('semester.semester_id'), nullable=True,  index=True)
    rating_overall   = db.Column(db.Integer, nullable=True)
    workload_level   = db.Column(db.Integer, nullable=True)
    difficulty_level = db.Column(db.Integer, nullable=True)
    assessment_style = db.Column(db.String(255), nullable=True)
    review_text      = db.Column(db.Text,    nullable=False)
    is_edited        = db.Column(db.Boolean,  default=False, nullable=False)
    is_removed       = db.Column(db.Boolean,  default=False, nullable=False)
    removed_at       = db.Column(db.DateTime, nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at       = db.Column(db.DateTime, nullable=True)

    course   = db.relationship('Course',     back_populates='reviews')
    user     = db.relationship('User',       back_populates='reviews')
    semester = db.relationship('Semester',   back_populates='reviews')
    likes    = db.relationship('ReviewLike', back_populates='review', lazy='dynamic', cascade='all, delete-orphan')
    flags    = db.relationship('Flag',       back_populates='review', lazy='dynamic')

    def get_like_data(self):
        '''
        Returns (score, counts) in a single DB query.
        score: really_helpful=2pts, helpful=1pt, not_helpful=0pts
        counts: dict with count per like type
        '''
        counts = {'really_helpful': 0, 'helpful': 0, 'not_helpful': 0}
        score  = 0
        for like in self.likes:
            counts[like.like_type] += 1
            if like.like_type == 'really_helpful':
                score += 2
            elif like.like_type == 'helpful':
                score += 1
        return score, counts

    def like_score(self):
        score, _ = self.get_like_data()
        return score

    def like_counts(self):
        _, counts = self.get_like_data()
        return counts

    def __repr__(self):
        return f'<Review {self.review_id} [{self.review_type}] course={self.course_id}>'


# ─────────────────────────────────────────────
# ReviewLike
# One like per user per review.
# really_helpful = 2pts | helpful = 1pt | not_helpful = 0pts
# ─────────────────────────────────────────────
class ReviewLike(db.Model):
    __tablename__ = 'review_like'

    __table_args__ = (
        db.UniqueConstraint('review_id', 'user_id', name='uq_review_like_user'),
    )

    like_id    = db.Column(db.Integer, primary_key=True, autoincrement=True)
    review_id  = db.Column(db.Integer, db.ForeignKey('review.review_id', ondelete='CASCADE'), nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.user_id',    ondelete='CASCADE'), nullable=False, index=True)
    like_type  = db.Column(db.Enum('really_helpful', 'helpful', 'not_helpful'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)

    review = db.relationship('Review', back_populates='likes')
    user   = db.relationship('User',   back_populates='review_likes')

    def __repr__(self):
        return f'<ReviewLike review={self.review_id} user={self.user_id} [{self.like_type}]>'


# ─────────────────────────────────────────────
# Material
# PDF uploads linked to a course and user.
# is_removed used for soft deletion by admins.
# ─────────────────────────────────────────────
class Material(db.Model):
    __tablename__ = 'material'

    material_id   = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    course_id     = db.Column(db.Integer,     db.ForeignKey('course.course_id'),     nullable=False, index=True)
    user_id       = db.Column(db.Integer,     db.ForeignKey('users.user_id'),        nullable=False, index=True)
    semester_id   = db.Column(db.Integer,     db.ForeignKey('semester.semester_id'), nullable=False, index=True)
    title         = db.Column(db.String(255), nullable=False)
    description   = db.Column(db.Text,        nullable=True)
    file_url      = db.Column(db.String(500), nullable=False)
    material_type = db.Column(db.Enum('notes', 'study_guide', 'exam', 'other'), nullable=False)
    is_removed    = db.Column(db.Boolean,     default=False, nullable=False)
    removed_at    = db.Column(db.DateTime,    nullable=True)
    created_at    = db.Column(db.DateTime,    default=datetime.now(timezone.utc), nullable=False)

    course   = db.relationship('Course',   back_populates='materials')
    user     = db.relationship('User',     back_populates='materials')
    semester = db.relationship('Semester', back_populates='materials')
    likes          = db.relationship('MaterialLike',   back_populates='material', lazy='dynamic', cascade='all, delete-orphan')
    flags          = db.relationship('Flag',          back_populates='material', lazy='dynamic')
    saved_by_users = db.relationship('SavedMaterial', back_populates='material', lazy='dynamic')

    def get_like_data(self):
        counts = {'really_helpful': 0, 'helpful': 0, 'not_helpful': 0}
        score  = 0
        for like in self.likes:
            counts[like.like_type] += 1
            if like.like_type == 'really_helpful':
                score += 2
            elif like.like_type == 'helpful':
                score += 1
        return score, counts

    def like_score(self):
        score, _ = self.get_like_data()
        return score

    def like_counts(self):
        _, counts = self.get_like_data()
        return counts

    def __repr__(self):
        return f'<Material {self.material_id} - {self.title}>'
    

# ─────────────────────────────────────────────
# MaterialLike
# One like per user per material.
# really_helpful = 2pts | helpful = 1pt | not_helpful = 0pts
# ─────────────────────────────────────────────
class MaterialLike(db.Model):
    __tablename__ = 'material_like'

    __table_args__ = (
        db.UniqueConstraint('material_id', 'user_id', name='uq_material_like_user'),
    )

    like_id     = db.Column(db.Integer, primary_key=True, autoincrement=True)
    material_id = db.Column(db.Integer, db.ForeignKey('material.material_id', ondelete='CASCADE'), nullable=False, index=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.user_id',       ondelete='CASCADE'), nullable=False, index=True)
    like_type   = db.Column(db.Enum('really_helpful', 'helpful', 'not_helpful'), nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)

    material = db.relationship('Material', back_populates='likes')
    user     = db.relationship('User',     back_populates='material_likes')

    def __repr__(self):
        return f'<MaterialLike material={self.material_id} user={self.user_id} [{self.like_type}]>'


# ─────────────────────────────────────────────
# FlagReason
# Seeded at setup. Not created by users or admins.
# ─────────────────────────────────────────────
class FlagReason(db.Model):
    __tablename__ = 'flag_reason'

    reason_id   = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    reason_name = db.Column(db.String(100), nullable=False)

    flags = db.relationship('Flag', back_populates='reason', lazy='dynamic')

    def __repr__(self):
        return f'<FlagReason {self.reason_name}>'


# ─────────────────────────────────────────────
# Flag
# User-submitted reports against materials.
# Visitors can flag using IP hash; users via user_id.
# Status flow: pending → reviewed | dismissed
# ─────────────────────────────────────────────
class Flag(db.Model):
    __tablename__ = 'flag'

    __table_args__ = (
        db.UniqueConstraint('reporter_user_id', 'material_id', name='uq_flag_user_material'),
        db.UniqueConstraint('reporter_ip_hash', 'material_id', name='uq_flag_ip_material'),
        db.UniqueConstraint('reporter_user_id', 'review_id',   name='uq_flag_user_review'),
        db.UniqueConstraint('reporter_ip_hash', 'review_id',   name='uq_flag_ip_review'),
    )

    flag_id              = db.Column(db.Integer,  primary_key=True, autoincrement=True)
    material_id          = db.Column(db.Integer,  db.ForeignKey('material.material_id'), nullable=True, index=True)
    review_id            = db.Column(db.Integer,  db.ForeignKey('review.review_id'),     nullable=True, index=True)
    reporter_user_id     = db.Column(db.Integer,  db.ForeignKey('users.user_id'),        nullable=True)
    reporter_ip_hash     = db.Column(db.String(64), nullable=True)
    reason_id            = db.Column(db.Integer,  db.ForeignKey('flag_reason.reason_id'), nullable=False, index=True)
    details              = db.Column(db.Text,     nullable=True)
    status               = db.Column(db.Enum('pending', 'reviewed', 'dismissed'), default='pending', nullable=False, index=True)
    reviewed_by_admin_id = db.Column(db.Integer,  db.ForeignKey('users.user_id'), nullable=True)
    reviewed_at          = db.Column(db.DateTime, nullable=True)
    created_at           = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)

    material          = db.relationship('Material',   back_populates='flags')
    review            = db.relationship('Review',     back_populates='flags')
    reporter          = db.relationship('User', foreign_keys=[reporter_user_id],     back_populates='flags_reported')
    reviewed_by_admin = db.relationship('User', foreign_keys=[reviewed_by_admin_id], back_populates='flags_reviewed')
    reason            = db.relationship('FlagReason', back_populates='flags')

    def content_type(self):
        return 'review' if self.review_id else 'material'

    def content_item(self):
        return self.review if self.review_id else self.material

    def __repr__(self):
        return f'<Flag {self.flag_id} [{self.status}]>'


# ─────────────────────────────────────────────
# PasswordResetToken
# Single-use, 30-minute expiry tokens for password recovery.
# ─────────────────────────────────────────────
class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_token'

    token_id   = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    user_id    = db.Column(db.Integer,     db.ForeignKey('users.user_id'), nullable=False, index=True)
    token      = db.Column(db.String(255), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime,    nullable=False)
    used_at    = db.Column(db.DateTime,    nullable=True)
    created_at = db.Column(db.DateTime,    default=datetime.now(timezone.utc), nullable=False)

    user = db.relationship('User', back_populates='reset_tokens')

    def is_expired(self):
        return datetime.utcnow() > self.expires_at

    def is_used(self):
        return self.used_at is not None

    def is_valid(self):
        return not self.is_expired() and not self.is_used()

    def __repr__(self):
        return f'<PasswordResetToken user={self.user_id} expires={self.expires_at}>'


# ─────────────────────────────────────────────
# SavedCourse
# Bookmarked courses per user, with optional note.
# ─────────────────────────────────────────────
class SavedCourse(db.Model):
    __tablename__ = 'saved_course'

    __table_args__ = (
        db.UniqueConstraint('user_id', 'course_id', name='uq_saved_course'),
    )

    id         = db.Column(db.Integer,  primary_key=True, autoincrement=True)
    user_id    = db.Column(db.Integer,  db.ForeignKey('users.user_id',    ondelete='CASCADE'), nullable=False, index=True)
    course_id  = db.Column(db.Integer,  db.ForeignKey('course.course_id', ondelete='CASCADE'), nullable=False, index=True)
    note       = db.Column(db.Text,     nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)

    user   = db.relationship('User',   back_populates='saved_courses')
    course = db.relationship('Course', back_populates='saved_by_users')

    def __repr__(self):
        return f'<SavedCourse user={self.user_id} course={self.course_id}>'


# ─────────────────────────────────────────────
# SavedMaterial
# Bookmarked materials per user, with optional note.
# ─────────────────────────────────────────────
class SavedMaterial(db.Model):
    __tablename__ = 'saved_material'

    __table_args__ = (
        db.UniqueConstraint('user_id', 'material_id', name='uq_saved_material'),
    )

    id          = db.Column(db.Integer,  primary_key=True, autoincrement=True)
    user_id     = db.Column(db.Integer,  db.ForeignKey('users.user_id',        ondelete='CASCADE'), nullable=False, index=True)
    material_id = db.Column(db.Integer,  db.ForeignKey('material.material_id', ondelete='CASCADE'), nullable=False, index=True)
    note        = db.Column(db.Text,     nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)

    user     = db.relationship('User',     back_populates='saved_materials')
    material = db.relationship('Material', back_populates='saved_by_users')

    def __repr__(self):
        return f'<SavedMaterial user={self.user_id} material={self.material_id}>'