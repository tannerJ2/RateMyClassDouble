'''

this is where you define all your database tables as 
Python classes (User, Course, Review, etc.) based on 
the schema in your SRS

'''


from datetime import datetime, timezone
from flask_login import UserMixin
from app.extensions import db, login_manager


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─────────────────────────────────────────────
# CourseProfessor (join table)
# ─────────────────────────────────────────────
# Many-to-many: a course can have many professors,
# a professor can teach many courses.
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
    """
    Stores all registered user accounts and authentication-related data.
    Roles: 'user' (default) or 'admin'
    """
    __tablename__ = "users"

    user_id       = db.Column(db.Integer, primary_key=True, autoincrement=True)
    first_name    = db.Column(db.String(100), nullable=False)
    last_name     = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role          = db.Column(db.Enum("user", "admin"), default="user", nullable=False)
    is_active     = db.Column(db.Boolean, default=True, nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    reviews        = db.relationship("Review",             back_populates="user",                        lazy="dynamic")
    materials      = db.relationship("Material",           back_populates="user",                        lazy="dynamic")
    flags_reported = db.relationship("Flag",               foreign_keys="Flag.reporter_user_id",         back_populates="reporter",          lazy="dynamic")
    flags_reviewed = db.relationship("Flag",               foreign_keys="Flag.reviewed_by_admin_id",     back_populates="reviewed_by_admin", lazy="dynamic")
    reset_tokens   = db.relationship("PasswordResetToken", back_populates="user",                        lazy="dynamic")

    def get_id(self):
        return str(self.user_id)

    def is_admin(self):
        return self.role == "admin"

    def __repr__(self):
        return f"<User {self.email}>"


# ─────────────────────────────────────────────
# Department
# ─────────────────────────────────────────────
class Department(db.Model):
    """
    Represents academic departments used to categorize courses.
    Example: dept_code='CSC', dept_name='Computer Science'
    """
    __tablename__ = "department"

    dept_id   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    dept_code = db.Column(db.String(10), unique=True, nullable=False)
    dept_name = db.Column(db.String(255), nullable=False)

    # Relationships
    courses = db.relationship("Course", back_populates="department", lazy="dynamic")

    def __repr__(self):
        return f"<Department {self.dept_code}>"


# ─────────────────────────────────────────────
# Professor
# ─────────────────────────────────────────────
class Professor(db.Model):
    """
    Stores professor names sourced from the SCSU course catalogue.
    Linked to courses via the course_professor join table.
    'TBA Staff' is stored as a professor when all sections are unassigned.
    """
    __tablename__ = "professor"

    professor_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    full_name    = db.Column(db.String(255), nullable=False, unique=True)

    # Relationships
    courses = db.relationship("Course", secondary=course_professor, back_populates="professors", lazy="dynamic")

    def __repr__(self):
        return f"<Professor {self.full_name}>"


# ─────────────────────────────────────────────
# Course
# ─────────────────────────────────────────────
class Course(db.Model):
    """
    Stores course-level metadata. Linked to a department.
    Example: course_number='152', course_title='Programming Fundamentals'
    """
    __tablename__ = "course"

    course_id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    dept_id            = db.Column(db.Integer, db.ForeignKey("department.dept_id"), nullable=False, index=True)
    course_number      = db.Column(db.String(20), nullable=False, index=True)
    course_title       = db.Column(db.String(255), nullable=False)
    course_description = db.Column(db.Text, nullable=True)
    created_at         = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)

    # Relationships
    department = db.relationship("Department", back_populates="courses")
    professors = db.relationship("Professor",  secondary=course_professor, back_populates="courses", lazy="dynamic")
    reviews    = db.relationship("Review",     back_populates="course",  lazy="dynamic")
    materials  = db.relationship("Material",   back_populates="course",  lazy="dynamic")

    def __repr__(self):
        return f"<Course {self.course_number} - {self.course_title}>"


# ─────────────────────────────────────────────
# Semester
# ─────────────────────────────────────────────
class Semester(db.Model):
    """
    Represents an academic term and year.
    Used to give context to reviews and materials (e.g., 'Fall 2025').
    """
    __tablename__ = "semester"

    semester_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    term        = db.Column(db.Enum("Spring", "Summer", "Fall", "Winter"), nullable=False)
    year        = db.Column(db.Integer, nullable=False, index=True)

    # Relationships
    reviews   = db.relationship("Review",   back_populates="semester", lazy="dynamic")
    materials = db.relationship("Material", back_populates="semester", lazy="dynamic")

    def __repr__(self):
        return f"<Semester {self.term} {self.year}>"


# ─────────────────────────────────────────────
# Review
# ─────────────────────────────────────────────
class Review(db.Model):
    """
    Stores structured course reviews submitted by verified users.
    Includes overall rating, workload, difficulty, and written feedback.
    Min review_text: 30 characters (enforced at route level).
    One review per user per course per semester.
    """
    __tablename__ = "review"

    review_id        = db.Column(db.Integer, primary_key=True, autoincrement=True)
    course_id        = db.Column(db.Integer, db.ForeignKey("course.course_id"),     nullable=False, index=True)
    user_id          = db.Column(db.Integer, db.ForeignKey("users.user_id"),        nullable=False, index=True)
    semester_id      = db.Column(db.Integer, db.ForeignKey("semester.semester_id"), nullable=False, index=True)
    rating_overall   = db.Column(db.Integer, nullable=False)   # 1–5
    workload_level   = db.Column(db.Integer, nullable=False)   # 1–5
    difficulty_level = db.Column(db.Integer, nullable=False)   # 1–5
    assessment_style = db.Column(db.String(255), nullable=True)
    review_text      = db.Column(db.Text, nullable=False)
    created_at       = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at       = db.Column(db.DateTime, nullable=True)

    # Relationships
    course   = db.relationship("Course",   back_populates="reviews")
    user     = db.relationship("User",     back_populates="reviews")
    semester = db.relationship("Semester", back_populates="reviews")

    def __repr__(self):
        return f"<Review {self.review_id} - Course {self.course_id}>"


# ─────────────────────────────────────────────
# Material
# ─────────────────────────────────────────────
class Material(db.Model):
    """
    Stores uploaded course-related academic materials (PDFs only).
    file_url references the file in Google Cloud Storage.
    is_removed is used for soft deletion by admins.
    """
    __tablename__ = "material"

    material_id   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    course_id     = db.Column(db.Integer, db.ForeignKey("course.course_id"),     nullable=False, index=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.user_id"),        nullable=False, index=True)
    semester_id   = db.Column(db.Integer, db.ForeignKey("semester.semester_id"), nullable=False, index=True)
    title         = db.Column(db.String(255), nullable=False)
    description   = db.Column(db.Text, nullable=True)
    file_url      = db.Column(db.String(500), nullable=False)
    material_type = db.Column(db.Enum("notes", "study_guide", "exam", "other"), nullable=False)
    is_removed    = db.Column(db.Boolean, default=False, nullable=False)
    removed_at    = db.Column(db.DateTime, nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)

    # Relationships
    course   = db.relationship("Course",   back_populates="materials")
    user     = db.relationship("User",     back_populates="materials")
    semester = db.relationship("Semester", back_populates="materials")
    flags    = db.relationship("Flag",     back_populates="material", lazy="dynamic")

    def __repr__(self):
        return f"<Material {self.material_id} - {self.title}>"


# ─────────────────────────────────────────────
# FlagReason
# ─────────────────────────────────────────────
class FlagReason(db.Model):
    """
    Lookup table for standardized moderation categories.
    Examples: 'Spam', 'Inappropriate Content', 'Plagiarism', 'Cheating'
    Seeded once at setup — admins don't create these manually.
    """
    __tablename__ = "flag_reason"

    reason_id   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    reason_name = db.Column(db.String(100), nullable=False)

    # Relationships
    flags = db.relationship("Flag", back_populates="reason", lazy="dynamic")

    def __repr__(self):
        return f"<FlagReason {self.reason_name}>"


# ─────────────────────────────────────────────
# Flag
# ─────────────────────────────────────────────
class Flag(db.Model):
    """
    Stores content reports submitted against materials.
    reporter_user_id is nullable — visitors can flag content too.
    reporter_ip_hash stores hashed IP for visitor flags.
    reviewed_by_admin_id is set when an admin takes action.
    Status flow: 'pending' → 'reviewed' or 'dismissed'
    """
    __tablename__ = "flag"

    __table_args__ = (
        db.UniqueConstraint('reporter_user_id', 'material_id', name='uq_flag_user_material'),
        db.UniqueConstraint('reporter_ip_hash', 'material_id', name='uq_flag_ip_material'),
    )

    flag_id              = db.Column(db.Integer, primary_key=True, autoincrement=True)
    material_id          = db.Column(db.Integer, db.ForeignKey("material.material_id"), nullable=False, index=True)
    reporter_user_id     = db.Column(db.Integer, db.ForeignKey("users.user_id"),        nullable=True)
    reporter_ip_hash     = db.Column(db.String(64), nullable=True)
    reason_id            = db.Column(db.Integer, db.ForeignKey("flag_reason.reason_id"), nullable=False, index=True)
    details              = db.Column(db.Text, nullable=True)
    status               = db.Column(db.Enum("pending", "reviewed", "dismissed"), default="pending", nullable=False, index=True)
    reviewed_by_admin_id = db.Column(db.Integer, db.ForeignKey("users.user_id"),        nullable=True)
    reviewed_at          = db.Column(db.DateTime, nullable=True)
    created_at           = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)

    # Relationships
    material          = db.relationship("Material",   back_populates="flags")
    reporter          = db.relationship("User", foreign_keys=[reporter_user_id],     back_populates="flags_reported")
    reviewed_by_admin = db.relationship("User", foreign_keys=[reviewed_by_admin_id], back_populates="flags_reviewed")
    reason            = db.relationship("FlagReason", back_populates="flags")

    def __repr__(self):
        return f"<Flag {self.flag_id} - Status: {self.status}>"


# ─────────────────────────────────────────────
# PasswordResetToken
# ─────────────────────────────────────────────
class PasswordResetToken(db.Model):
    """
    Stores time-limited, single-use tokens for password recovery.
    Tokens expire after 30 minutes (enforced at route level).
    used_at is set when the token is consumed so it can't be reused.
    """
    __tablename__ = "password_reset_token"

    token_id   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True)
    token      = db.Column(db.String(255), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at    = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = db.relationship("User", back_populates="reset_tokens")

    def is_expired(self):
        return datetime.utcnow() > self.expires_at

    def is_used(self):
        return self.used_at is not None

    def is_valid(self):
        return not self.is_expired() and not self.is_used()

    def __repr__(self):
        return f"<PasswordResetToken user={self.user_id} expires={self.expires_at}>"