-- =============================================================================
-- RateMyClass — Production Database Schema
-- Southern Connecticut State University Capstone Project
-- Database:   MySQL 8.0
-- ORM:        Flask-SQLAlchemy
-- Encoding:   UTF8MB4
-- Engine:     InnoDB
-- Generated:  2026-03-02
-- Version:    1.1 (PATCHED — user→users rename, visitor flag uniqueness)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Database creation
-- -----------------------------------------------------------------------------

CREATE DATABASE IF NOT EXISTS ratemyclass
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE ratemyclass;

-- Enforce foreign key checks during all operations
SET FOREIGN_KEY_CHECKS = 1;


-- =============================================================================
-- TABLE: Department
-- Represents academic departments for course categorization.
-- Referenced by: Course
-- =============================================================================

CREATE TABLE IF NOT EXISTS department (
    dept_id     INT             NOT NULL AUTO_INCREMENT,
    dept_code   VARCHAR(10)     NOT NULL,
    dept_name   VARCHAR(255)    NOT NULL,

    CONSTRAINT pk_department PRIMARY KEY (dept_id),
    CONSTRAINT uq_department_dept_code UNIQUE (dept_code)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Academic departments for course categorization.';


-- =============================================================================
-- TABLE: Users
-- Stores all registered user accounts and authentication-related data.
-- Referenced by: Review, Material, Flag (reporter), Flag (admin),
--               PasswordResetToken
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    user_id         INT             NOT NULL AUTO_INCREMENT,
    first_name      VARCHAR(100)    NOT NULL,
    last_name       VARCHAR(100)    NOT NULL,
    email           VARCHAR(255)    NOT NULL,
    password_hash   VARCHAR(255)    NOT NULL,
    role            ENUM('user', 'admin')
                                    NOT NULL DEFAULT 'user',
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at   DATETIME                 DEFAULT NULL,

    CONSTRAINT pk_users PRIMARY KEY (user_id),
    CONSTRAINT uq_users_email UNIQUE (email),

    -- Email must belong to @southernct.edu domain
    CONSTRAINT chk_users_email_domain
        CHECK (email LIKE '%@southernct.edu')
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Registered user accounts and authentication data.';


-- =============================================================================
-- TABLE: Course
-- Stores course-level metadata linked to departments.
-- Referenced by: Review, Material
-- =============================================================================

CREATE TABLE IF NOT EXISTS course (
    course_id           INT             NOT NULL AUTO_INCREMENT,
    dept_id             INT             NOT NULL,
    course_number       VARCHAR(20)     NOT NULL,
    course_title        VARCHAR(255)    NOT NULL,
    course_description  TEXT                     DEFAULT NULL,
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_course PRIMARY KEY (course_id),

    CONSTRAINT fk_course_dept
        FOREIGN KEY (dept_id)
        REFERENCES department (dept_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    -- Composite unique: a course_number is unique within a department
    CONSTRAINT uq_course_dept_number UNIQUE (dept_id, course_number),

    INDEX idx_course_dept_id     (dept_id),
    INDEX idx_course_number      (course_number),
    -- Composite index for the primary search pattern: dept + number
    INDEX idx_course_dept_number (dept_id, course_number)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Course-level metadata linked to departments.';


-- =============================================================================
-- TABLE: Semester
-- Represents academic term and year for time-specific context.
-- Referenced by: Review, Material
-- =============================================================================

CREATE TABLE IF NOT EXISTS semester (
    semester_id INT  NOT NULL AUTO_INCREMENT,
    term        ENUM('Spring', 'Summer', 'Fall', 'Winter')
                     NOT NULL,
    year        INT  NOT NULL,

    CONSTRAINT pk_semester PRIMARY KEY (semester_id),

    -- A term+year combination must be unique
    CONSTRAINT uq_semester_term_year UNIQUE (term, year),

    -- Reasonable academic year range
    CONSTRAINT chk_semester_year
        CHECK (year >= 2000 AND year <= 2100),

    INDEX idx_semester_year (year)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Academic terms and years for time-specific reviews and materials.';


-- =============================================================================
-- TABLE: Review
-- Stores structured, semester-specific course reviews submitted by users.
-- =============================================================================

CREATE TABLE IF NOT EXISTS review (
    review_id           INT         NOT NULL AUTO_INCREMENT,
    course_id           INT         NOT NULL,
    user_id             INT         NOT NULL,
    semester_id         INT         NOT NULL,
    rating_overall      TINYINT     NOT NULL,
    workload_level      TINYINT     NOT NULL,
    difficulty_level    TINYINT     NOT NULL,
    assessment_style    VARCHAR(255)         DEFAULT NULL,
    review_text         TEXT        NOT NULL,
    created_at          DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME             DEFAULT NULL
                            ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT pk_review PRIMARY KEY (review_id),

    CONSTRAINT fk_review_course
        FOREIGN KEY (course_id)
        REFERENCES course (course_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_review_users
        FOREIGN KEY (user_id)
        REFERENCES users (user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_review_semester
        FOREIGN KEY (semester_id)
        REFERENCES semester (semester_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    -- Rating range enforcement (1–5)
    CONSTRAINT chk_review_rating_overall
        CHECK (rating_overall BETWEEN 1 AND 5),
    CONSTRAINT chk_review_workload_level
        CHECK (workload_level BETWEEN 1 AND 5),
    CONSTRAINT chk_review_difficulty_level
        CHECK (difficulty_level BETWEEN 1 AND 5),

    -- Minimum review text length (30 characters per SRS)
    CONSTRAINT chk_review_text_min_length
        CHECK (CHAR_LENGTH(review_text) >= 30),

    -- One review per user per course per semester
    CONSTRAINT uq_review_user_course_semester
        UNIQUE (user_id, course_id, semester_id),

    INDEX idx_review_course_id   (course_id),
    INDEX idx_review_user_id     (user_id),
    INDEX idx_review_semester_id (semester_id),
    -- Composite index for rating-filtered course queries
    INDEX idx_review_course_rating (course_id, rating_overall),
    -- Sorting by submission date
    INDEX idx_review_created_at  (created_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Semester-specific course reviews submitted by authenticated users.';


-- =============================================================================
-- TABLE: Material
-- Stores uploaded course-related academic materials.
-- Referenced by: Flag
-- Soft-deletion via is_removed / removed_at.
-- =============================================================================

CREATE TABLE IF NOT EXISTS material (
    material_id     INT             NOT NULL AUTO_INCREMENT,
    course_id       INT             NOT NULL,
    user_id         INT             NOT NULL,
    semester_id     INT             NOT NULL,
    title           VARCHAR(255)    NOT NULL,
    description     TEXT                     DEFAULT NULL,
    file_url        VARCHAR(500)    NOT NULL,
    material_type   ENUM('notes', 'study_guide', 'exam', 'other')
                                    NOT NULL,
    is_removed      BOOLEAN         NOT NULL DEFAULT FALSE,
    removed_at      DATETIME                 DEFAULT NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_material PRIMARY KEY (material_id),

    CONSTRAINT fk_material_course
        FOREIGN KEY (course_id)
        REFERENCES course (course_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_material_users
        FOREIGN KEY (user_id)
        REFERENCES users (user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_material_semester
        FOREIGN KEY (semester_id)
        REFERENCES semester (semester_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    -- removed_at must be set when and only when is_removed is TRUE
    CONSTRAINT chk_material_removed_consistency
        CHECK (
            (is_removed = FALSE AND removed_at IS NULL) OR
            (is_removed = TRUE  AND removed_at IS NOT NULL)
        ),

    INDEX idx_material_course_id   (course_id),
    INDEX idx_material_user_id     (user_id),
    INDEX idx_material_semester_id (semester_id),
    -- Frequent filter: active materials per course
    INDEX idx_material_course_active (course_id, is_removed),
    INDEX idx_material_created_at    (created_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Uploaded course materials with soft-deletion support.';


-- =============================================================================
-- TABLE: FlagReason
-- Defines standardized reasons for reporting flagged materials.
-- Referenced by: Flag
-- =============================================================================

CREATE TABLE IF NOT EXISTS flag_reason (
    reason_id   INT             NOT NULL AUTO_INCREMENT,
    reason_name VARCHAR(100)    NOT NULL,

    CONSTRAINT pk_flag_reason PRIMARY KEY (reason_id),
    CONSTRAINT uq_flag_reason_name UNIQUE (reason_name)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Standardized moderation categories for flagged content.';


-- =============================================================================
-- TABLE: Flag
-- Stores reports submitted by users against materials.
-- Flags apply to Materials ONLY (per SRS constraint).
-- =============================================================================

CREATE TABLE IF NOT EXISTS flag (
    flag_id                 INT     NOT NULL AUTO_INCREMENT,
    material_id             INT     NOT NULL,
    reporter_user_id        INT              DEFAULT NULL,   -- nullable: visitor flags
    reporter_ip_hash        CHAR(64)         DEFAULT NULL,   -- SHA-256 of visitor IP; set only when reporter_user_id IS NULL
    reason_id               INT     NOT NULL,
    details                 TEXT             DEFAULT NULL,
    status                  ENUM('pending', 'reviewed', 'dismissed')
                                    NOT NULL DEFAULT 'pending',
    reviewed_by_admin_id    INT              DEFAULT NULL,
    reviewed_at             DATETIME         DEFAULT NULL,
    created_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_flag PRIMARY KEY (flag_id),

    CONSTRAINT fk_flag_material
        FOREIGN KEY (material_id)
        REFERENCES material (material_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_flag_reporter
        FOREIGN KEY (reporter_user_id)
        REFERENCES users (user_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE,

    CONSTRAINT fk_flag_reason
        FOREIGN KEY (reason_id)
        REFERENCES flag_reason (reason_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT fk_flag_admin
        FOREIGN KEY (reviewed_by_admin_id)
        REFERENCES users (user_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE,

    -- reviewed_at and reviewed_by_admin_id must be consistent
    CONSTRAINT chk_flag_review_consistency
        CHECK (
            (status = 'pending'  AND reviewed_by_admin_id IS NULL AND reviewed_at IS NULL) OR
            (status != 'pending' AND reviewed_by_admin_id IS NOT NULL AND reviewed_at IS NOT NULL)
        ),

    -- Exactly one of reporter_user_id or reporter_ip_hash must be provided (XOR)
    CONSTRAINT chk_flag_reporter_xor
        CHECK (
            (reporter_user_id IS NOT NULL AND reporter_ip_hash IS NULL) OR
            (reporter_user_id IS NULL     AND reporter_ip_hash IS NOT NULL)
        ),

    -- Authenticated user: max 1 flag per material (US011 SRS constraint)
    CONSTRAINT uq_flag_user_material
        UNIQUE (reporter_user_id, material_id),

    -- Visitor: max 1 flag per material (ip_hash uniqueness)
    CONSTRAINT uq_flag_ip_material
        UNIQUE (reporter_ip_hash, material_id),

    INDEX idx_flag_material_id  (material_id),
    INDEX idx_flag_reason_id    (reason_id),
    INDEX idx_flag_status       (status),
    -- Admin moderation queue: pending flags sorted by date
    INDEX idx_flag_status_created (status, created_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='User-submitted content reports against materials.';


-- =============================================================================
-- TABLE: PasswordResetToken
-- Stores single-use, time-limited tokens for password recovery.
-- =============================================================================

CREATE TABLE IF NOT EXISTS password_reset_token (
    token_id    INT             NOT NULL AUTO_INCREMENT,
    user_id     INT             NOT NULL,
    token       VARCHAR(255)    NOT NULL,
    expires_at  DATETIME        NOT NULL,
    used_at     DATETIME                 DEFAULT NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_password_reset_token PRIMARY KEY (token_id),
    CONSTRAINT uq_password_reset_token UNIQUE (token),

    CONSTRAINT fk_prt_users
        FOREIGN KEY (user_id)
        REFERENCES users (user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    -- used_at must not precede created_at
    CONSTRAINT chk_prt_used_after_created
        CHECK (used_at IS NULL OR used_at >= created_at),

    -- expires_at must not precede created_at
    CONSTRAINT chk_prt_expires_after_created
        CHECK (expires_at > created_at),

    INDEX idx_prt_user_id    (user_id),
    -- Token lookup by value (primary query path)
    -- Covered by UNIQUE(token) — no additional index needed
    -- Active token lookup: find unused, non-expired tokens per user
    INDEX idx_prt_user_active (user_id, used_at, expires_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Single-use time-limited tokens for password recovery (30-min expiry).';


-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
