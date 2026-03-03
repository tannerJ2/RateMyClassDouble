'''
this is where you define all your database tables as
Python classes (User, Course, Review, etc.) based on
the schema in your SRS
'''

from datetime import datetime, timezone
from flask_login import UserMixin
from sqlalchemy.dialects.mysql import TINYINT
from app.extensions import db


# ─────────────────────────────────────────────
# Department
# ─────────────────────────────────────────────
class Department(db.Model):
    __tablename__ = "department"

    dept_id   = db.Column(db.Integer,     nullable=False, primary_key=True, autoincrement=True)
    dept_code = db.Column(db.String(10),  nullable=False)
    dept_name = db.Column(db.String(255), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("dept_code", name="uq_department_dept_code"),
    )

    courses = db.relationship(
        "Course",
        back_populates="department",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Department {self.dept_code}>"


# ─────────────────────────────────────────────
# User
# ─────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = "users"

    user_id       = db.Column(db.Integer,     nullable=False, primary_key=True, autoincrement=True)
    first_name    = db.Column(db.String(100), nullable=False)
    last_name     = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role          = db.Column(
        db.Enum("user", "admin", name="users_role"),
        nullable=False,
        server_default="user",
    )
    is_active     = db.Column(db.Boolean,  nullable=False, server_default="1")
    created_at    = db.Column(db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP"))
    last_login_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("email", name="uq_users_email"),
        db.CheckConstraint("email LIKE '%@southernct.edu'", name="chk_users_email_domain"),
    )

    reviews = db.relationship(
        "Review",
        foreign_keys="Review.user_id",
        back_populates="user",
        passive_deletes=True,
    )
    materials = db.relationship(
        "Material",
        foreign_keys="Material.user_id",
        back_populates="user",
        passive_deletes=True,
    )
    flags_reported = db.relationship(
        "Flag",
        foreign_keys="Flag.reporter_user_id",
        back_populates="reporter",
        passive_deletes=True,
    )
    flags_reviewed = db.relationship(
        "Flag",
        foreign_keys="Flag.reviewed_by_admin_id",
        back_populates="reviewing_admin",
        passive_deletes=True,
    )
    password_reset_tokens = db.relationship(
        "PasswordResetToken",
        back_populates="user",
        passive_deletes=True,
    )

    # Flask-Login required
    def get_id(self):
        return str(self.user_id)

    def is_admin(self):
        return self.role == "admin"

    def __repr__(self):
        return f"<User {self.email}>"


# ─────────────────────────────────────────────
# Course
# ─────────────────────────────────────────────
class Course(db.Model):
    __tablename__ = "course"

    course_id          = db.Column(db.Integer,     nullable=False, primary_key=True, autoincrement=True)
    dept_id            = db.Column(db.Integer,     db.ForeignKey("department.dept_id", ondelete="RESTRICT"), nullable=False)
    course_number      = db.Column(db.String(20),  nullable=False)
    course_title       = db.Column(db.String(255), nullable=False)
    course_description = db.Column(db.Text,        nullable=True)
    created_at         = db.Column(db.DateTime,    nullable=False, server_default=db.text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        db.UniqueConstraint("dept_id", "course_number", name="uq_course_dept_number"),
        db.Index("idx_course_dept_id",     "dept_id"),
        db.Index("idx_course_number",      "course_number"),
        db.Index("idx_course_dept_number", "dept_id", "course_number"),
    )

    department = db.relationship("Department", back_populates="courses")
    reviews = db.relationship(
        "Review",
        back_populates="course",
        passive_deletes=True,
    )
    materials = db.relationship(
        "Material",
        back_populates="course",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Course {self.course_number} - {self.course_title}>"


# ─────────────────────────────────────────────
# Semester
# ─────────────────────────────────────────────
class Semester(db.Model):
    __tablename__ = "semester"

    semester_id = db.Column(db.Integer, nullable=False, primary_key=True, autoincrement=True)
    term        = db.Column(
        db.Enum("Spring", "Summer", "Fall", "Winter", name="semester_term"),
        nullable=False,
    )
    year        = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("term", "year", name="uq_semester_term_year"),
        db.CheckConstraint("year >= 2000 AND year <= 2100", name="chk_semester_year"),
        db.Index("idx_semester_year", "year"),
    )

    reviews = db.relationship(
        "Review",
        back_populates="semester",
        passive_deletes=True,
    )
    materials = db.relationship(
        "Material",
        back_populates="semester",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Semester {self.term} {self.year}>"


# ─────────────────────────────────────────────
# Review
# ─────────────────────────────────────────────
class Review(db.Model):
    __tablename__ = "review"

    review_id        = db.Column(db.Integer,  nullable=False, primary_key=True, autoincrement=True)
    course_id        = db.Column(db.Integer,  db.ForeignKey("course.course_id",     ondelete="CASCADE"),  nullable=False)
    user_id          = db.Column(db.Integer,  db.ForeignKey("users.user_id",        ondelete="CASCADE"),  nullable=False)
    semester_id      = db.Column(db.Integer,  db.ForeignKey("semester.semester_id", ondelete="RESTRICT"), nullable=False)
    rating_overall   = db.Column(TINYINT,     nullable=False)
    workload_level   = db.Column(TINYINT,     nullable=False)
    difficulty_level = db.Column(TINYINT,     nullable=False)
    assessment_style = db.Column(db.String(255), nullable=True)
    review_text      = db.Column(db.Text,     nullable=False)
    created_at       = db.Column(db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP"))
    updated_at       = db.Column(db.DateTime, nullable=True,  server_onupdate=db.text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        db.UniqueConstraint("user_id", "course_id", "semester_id", name="uq_review_user_course_semester"),
        db.CheckConstraint("rating_overall BETWEEN 1 AND 5",   name="chk_review_rating_overall"),
        db.CheckConstraint("workload_level BETWEEN 1 AND 5",   name="chk_review_workload_level"),
        db.CheckConstraint("difficulty_level BETWEEN 1 AND 5", name="chk_review_difficulty_level"),
        db.CheckConstraint("CHAR_LENGTH(review_text) >= 30",   name="chk_review_text_min_length"),
        db.Index("idx_review_course_id",     "course_id"),
        db.Index("idx_review_user_id",       "user_id"),
        db.Index("idx_review_semester_id",   "semester_id"),
        db.Index("idx_review_course_rating", "course_id", "rating_overall"),
        db.Index("idx_review_created_at",    "created_at"),
    )

    course   = db.relationship("Course",   back_populates="reviews")
    user     = db.relationship("User",     foreign_keys=[user_id], back_populates="reviews")
    semester = db.relationship("Semester", back_populates="reviews")

    def __repr__(self):
        return f"<Review {self.review_id} - Course {self.course_id}>"


# ─────────────────────────────────────────────
# Material
# ─────────────────────────────────────────────
class Material(db.Model):
    __tablename__ = "material"

    material_id   = db.Column(db.Integer,     nullable=False, primary_key=True, autoincrement=True)
    course_id     = db.Column(db.Integer,     db.ForeignKey("course.course_id",     ondelete="CASCADE"),  nullable=False)
    user_id       = db.Column(db.Integer,     db.ForeignKey("users.user_id",        ondelete="CASCADE"),  nullable=False)
    semester_id   = db.Column(db.Integer,     db.ForeignKey("semester.semester_id", ondelete="RESTRICT"), nullable=False)
    title         = db.Column(db.String(255), nullable=False)
    description   = db.Column(db.Text,        nullable=True)
    file_url      = db.Column(db.String(500), nullable=False)
    material_type = db.Column(
        db.Enum("notes", "study_guide", "exam", "other", name="material_material_type"),
        nullable=False,
    )
    is_removed    = db.Column(db.Boolean,  nullable=False, server_default="0")
    removed_at    = db.Column(db.DateTime, nullable=True)
    created_at    = db.Column(db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        db.CheckConstraint(
            "(is_removed = FALSE AND removed_at IS NULL) OR (is_removed = TRUE AND removed_at IS NOT NULL)",
            name="chk_material_removed_consistency",
        ),
        db.Index("idx_material_course_id",     "course_id"),
        db.Index("idx_material_user_id",       "user_id"),
        db.Index("idx_material_semester_id",   "semester_id"),
        db.Index("idx_material_course_active", "course_id", "is_removed"),
        db.Index("idx_material_created_at",    "created_at"),
    )

    course   = db.relationship("Course",   back_populates="materials")
    user     = db.relationship("User",     foreign_keys=[user_id], back_populates="materials")
    semester = db.relationship("Semester", back_populates="materials")
    flags    = db.relationship(
        "Flag",
        back_populates="material",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Material {self.material_id} - {self.title}>"


# ─────────────────────────────────────────────
# FlagReason
# ─────────────────────────────────────────────
class FlagReason(db.Model):
    __tablename__ = "flag_reason"

    reason_id   = db.Column(db.Integer,     nullable=False, primary_key=True, autoincrement=True)
    reason_name = db.Column(db.String(100), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("reason_name", name="uq_flag_reason_name"),
    )

    flags = db.relationship(
        "Flag",
        back_populates="reason",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<FlagReason {self.reason_name}>"


# ─────────────────────────────────────────────
# Flag
# ─────────────────────────────────────────────
class Flag(db.Model):
    __tablename__ = "flag"

    flag_id              = db.Column(db.Integer,  nullable=False, primary_key=True, autoincrement=True)
    material_id          = db.Column(db.Integer,  db.ForeignKey("material.material_id",  ondelete="CASCADE"),  nullable=False)
    reporter_user_id     = db.Column(db.Integer,  db.ForeignKey("users.user_id",         ondelete="SET NULL"), nullable=True)
    reporter_ip_hash     = db.Column(db.CHAR(64), nullable=True)
    reason_id            = db.Column(db.Integer,  db.ForeignKey("flag_reason.reason_id", ondelete="RESTRICT"), nullable=False)
    details              = db.Column(db.Text,     nullable=True)
    status               = db.Column(
        db.Enum("pending", "reviewed", "dismissed", name="flag_status"),
        nullable=False,
        server_default="pending",
    )
    reviewed_by_admin_id = db.Column(db.Integer,  db.ForeignKey("users.user_id",         ondelete="SET NULL"), nullable=True)
    reviewed_at          = db.Column(db.DateTime, nullable=True)
    created_at           = db.Column(db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        db.UniqueConstraint("reporter_user_id", "material_id", name="uq_flag_user_material"),
        db.UniqueConstraint("reporter_ip_hash", "material_id", name="uq_flag_ip_material"),
        db.CheckConstraint(
            "(status = 'pending' AND reviewed_by_admin_id IS NULL AND reviewed_at IS NULL) OR "
            "(status != 'pending' AND reviewed_by_admin_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="chk_flag_review_consistency",
        ),
        db.CheckConstraint(
            "(reporter_user_id IS NOT NULL AND reporter_ip_hash IS NULL) OR "
            "(reporter_user_id IS NULL AND reporter_ip_hash IS NOT NULL)",
            name="chk_flag_reporter_xor",
        ),
        db.Index("idx_flag_material_id",    "material_id"),
        db.Index("idx_flag_reason_id",      "reason_id"),
        db.Index("idx_flag_status",         "status"),
        db.Index("idx_flag_status_created", "status", "created_at"),
    )

    material        = db.relationship("Material",   back_populates="flags")
    reporter        = db.relationship("User",       foreign_keys=[reporter_user_id],     back_populates="flags_reported")
    reviewing_admin = db.relationship("User",       foreign_keys=[reviewed_by_admin_id], back_populates="flags_reviewed")
    reason          = db.relationship("FlagReason", back_populates="flags")

    def __repr__(self):
        return f"<Flag {self.flag_id} - Status: {self.status}>"


# ─────────────────────────────────────────────
# PasswordResetToken
# ─────────────────────────────────────────────
class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_token"

    token_id   = db.Column(db.Integer,     nullable=False, primary_key=True, autoincrement=True)
    user_id    = db.Column(db.Integer,     db.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    token      = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime,   nullable=False)
    used_at    = db.Column(db.DateTime,   nullable=True)
    created_at = db.Column(db.DateTime,   nullable=False, server_default=db.text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        db.UniqueConstraint("token", name="uq_password_reset_token"),
        db.CheckConstraint("used_at IS NULL OR used_at >= created_at", name="chk_prt_used_after_created"),
        db.CheckConstraint("expires_at > created_at",                  name="chk_prt_expires_after_created"),
        db.Index("idx_prt_user_id",     "user_id"),
        db.Index("idx_prt_user_active", "user_id", "used_at", "expires_at"),
    )

    user = db.relationship("User", back_populates="password_reset_tokens")

    def is_expired(self):
        return datetime.now(timezone.utc).replace(tzinfo=None) > self.expires_at

    def is_used(self):
        return self.used_at is not None

    def is_valid(self):
        return not self.is_expired() and not self.is_used()

    def __repr__(self):
        return f"<PasswordResetToken user={self.user_id} expires={self.expires_at}>"