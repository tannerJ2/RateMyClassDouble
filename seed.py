# =============================================================================
# RateMyClass — Database Seed Script
# Source: courses_Fall_2026 CSV (real SCSU Fall 2026 catalogue)
#
# Usage:
#   python3 seed.py
#
# What this script does:
#   1. Drops and recreates all tables
#   2. Seeds Semesters (2022–2026, all terms)
#   3. Seeds Departments (all unique subjects from CSV)
#   4. Seeds Courses (all unique courses, one entry per subject+number)
#   5. Seeds Professors + course_professor join table
#   6. Seeds FlagReasons (4 standard categories)
#   7. Seeds a test Admin account
#   8. Seeds a test User account + a sample review
#
# PROFESSOR NOTE:
#   schema.sql does not currently have a Professor table.
#   This script creates two extra tables automatically:
#     - professor         (professor_id, full_name)
#     - course_professor  (course_id FK, professor_id FK)  [many-to-many]
#   To make these permanent, add them to schema.sql and models.py.
#
# PROFESSOR RULES (per spec):
#   - Each professor listed only once per course, even if they teach
#     multiple sections of the same course.
#   - If a course has any real professor, TBA Staff is excluded entirely.
#   - If ALL sections are TBA Staff, the course is listed with no professors.
#   - Instructor pronouns and HTML entities are cleaned automatically.
# =============================================================================

import csv
import html
import os
import re

from sqlalchemy import Table, Column, Integer, String, ForeignKey, UniqueConstraint
from flask_bcrypt import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Course, Department, FlagReason, Review, Semester, User

app = create_app()

# =============================================================================
# EXTRA TABLES  (professor + course_professor join)
# =============================================================================

professor_table = Table(
    'professor', db.metadata,
    Column('professor_id', Integer, primary_key=True, autoincrement=True),
    Column('full_name',    String(255), nullable=False, unique=True),
    extend_existing=True,
)

course_professor_table = Table(
    'course_professor', db.metadata,
    Column('course_id',    Integer, ForeignKey('course.course_id',         ondelete='CASCADE'), nullable=False),
    Column('professor_id', Integer, ForeignKey('professor.professor_id',   ondelete='CASCADE'), nullable=False),
    UniqueConstraint('course_id', 'professor_id', name='uq_course_professor'),
    extend_existing=True,
)


# =============================================================================
# DEPARTMENT CODE → FULL NAME  (all 78 subjects in the Fall 2026 catalogue)
# =============================================================================

DEPARTMENT_NAMES = {
    'AAC':  'Arts Administration',
    'ACC':  'Accounting',
    'AFR':  'Africana Studies',
    'ANT':  'Anthropology',
    'ARB':  'Arabic',
    'ART':  'Art',
    'AST':  'Astronomy',
    'ATH':  'Athletic Training & Health',
    'BIO':  'Biology',
    'BIS':  'Business Information Systems',
    'CDS':  'Communication Disorders & Sciences',
    'CED':  'Community Economic Development',
    'CHE':  'Chemistry',
    'CMS':  'Communication Studies',
    'COE':  'Counselor Education',
    'CRM':  'Criminology',
    'CSC':  'Computer Science',
    'DBA':  'Doctor of Business Administration',
    'DES':  'Design',
    'DGH':  'Digital Humanities',
    'DSC':  'Data Science',
    'ECO':  'Economics',
    'EDL':  'Educational Leadership',
    'EDU':  'Education',
    'ENG':  'English',
    'ENV':  'Environmental Studies',
    'ESC':  'Earth Science',
    'FIN':  'Finance',
    'FRE':  'French',
    'GEO':  'Geography',
    'GER':  'German',
    'HCM':  'Healthcare Management',
    'HIS':  'History',
    'HLS':  'Homeland Security',
    'HMS':  'Human Services',
    'HON':  'Honors Program',
    'HSC':  'Health Sciences',
    'IDS':  'Interdisciplinary Studies',
    'ILS':  'Information & Library Science',
    'INQ':  'Inquiry & Research',
    'ITA':  'Italian',
    'JRN':  'Journalism',
    'JST':  'Jewish Studies',
    'LAC':  'Latin American & Caribbean Studies',
    'LIT':  'Literature',
    'MAR':  'Marine Sciences',
    'MAT':  'Mathematics',
    'MBA':  'Master of Business Administration',
    'MFT':  'Marriage & Family Therapy',
    'MGT':  'Management',
    'MHS':  'Mental Health & Substance Abuse Services',
    'MKT':  'Marketing',
    'MPA':  'Master of Public Administration',
    'MUS':  'Music',
    'MUT':  'Music Theory',
    'NUR':  'Nursing',
    'OTR':  'Occupational Therapy',
    'PCH':  'Public & Community Health',
    'PHI':  'Philosophy',
    'PHY':  'Physics',
    'PSC':  'Political Science',
    'PSY':  'Psychology',
    'RDG':  'Reading',
    'REC':  'Recreation & Leisure Studies',
    'RSP':  'Respiratory Care',
    'SCE':  'Science Education',
    'SED':  'Special Education',
    'SHE':  'School Health Education',
    'SLH':  'Speech-Language & Hearing',
    'SMT':  'Sport Management',
    'SOC':  'Sociology',
    'SPA':  'Spanish',
    'SWK':  'Social Work',
    'T2AE': 'Teacher Education',
    'THE':  'Tourism & Hospitality Education',
    'THR':  'Theatre',
    'TSL':  'Teaching of Second Languages',
    'WGS':  "Women's & Gender Studies",
    'WLL':  'World Languages & Literatures',
}


# =============================================================================
# HELPER — clean a single raw instructor string into a list of professor names
# =============================================================================

def parse_instructors(raw: str) -> list[str]:
    """
    Takes a raw Instructor cell value and returns a clean list of
    professor name strings, with TBA Staff removed if any real name exists.

    Handles:
      - Semicolon-separated multiple instructors
      - HTML entities  (&#39; → ', &amp; → &)
      - Pronoun declarations  (she/her/hers), (he/him/his), (they/them/their)
      - Misc parentheticals   (Please ask), (Prefer not to answer), nicknames
      - TBA Staff logic       excluded when real professor exists
    """
    if not raw or not raw.strip():
        return []

    # Decode HTML entities
    raw = html.unescape(raw)

    # Split on semicolons to get individual names
    parts = [p.strip() for p in raw.split(';')]

    cleaned = []
    for part in parts:
        if not part:
            continue

        # Remove anything inside parentheses (pronouns, nicknames, notes)
        name = re.sub(r'\s*\(.*?\)', '', part).strip()

        # Normalise whitespace
        name = re.sub(r'\s+', ' ', name).strip()

        if name:
            cleaned.append(name)

    # Apply TBA Staff rule:
    # If there is at least one real name alongside TBA Staff, drop TBA Staff.
    real_names = [n for n in cleaned if n.upper() != 'TBA STAFF']
    if real_names:
        return real_names      # real professor exists — drop TBA Staff
    elif cleaned:
        return ['TBA Staff']   # all TBA — keep one TBA Staff entry
    return []


# =============================================================================
# CSV PARSING — build course → professors mapping
# =============================================================================

def load_csv(filepath: str):
    """
    Reads the CSV and returns:
      courses_meta  : dict  (subject, number) → (title, credits)
      course_profs  : dict  (subject, number) → set of professor name strings
    """
    courses_meta  = {}   # (subject, number) → (title, credits)
    course_profs  = {}   # (subject, number) → set of name strings

    with open(filepath, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            subject = row['Subject'].strip()
            number  = row['Course Number'].strip()
            title   = html.unescape(row['Title'].strip())
            credits = row['Credits'].strip()
            key     = (subject, number)

            # First time we see this course — store metadata
            if key not in courses_meta:
                courses_meta[key]  = (title, credits)
                course_profs[key]  = set()

            # Parse and accumulate professors for this course
            names = parse_instructors(row['Instructor'])
            for name in names:
                course_profs[key].add(name)

    # Post-process: if a course has any real professor, remove TBA Staff.
    # Only keep TBA Staff if it is the only entry (all sections were TBA).
    for key in course_profs:
        real = {n for n in course_profs[key] if n.upper() != 'TBA STAFF'}
        if real:
            course_profs[key] = real          # drop TBA Staff
        elif not course_profs[key]:
            course_profs[key] = {'TBA Staff'} # all sections had no instructor at all

    return courses_meta, course_profs


# =============================================================================
# SEED
# =============================================================================

def seed():
    csv_path = os.path.join(os.path.dirname(__file__), 'courses_Fall_2026.csv')

    if not os.path.exists(csv_path):
        print(f"\n[ERROR] CSV file not found at:\n  {csv_path}")
        print("Place courses_Fall_2026__View_Only_.csv in the same folder as seed.py and retry.\n")
        return

    print("=" * 60)
    print("RateMyClass — Database Seeder")
    print("=" * 60)

    # ── Parse CSV first (fail-fast before touching DB) ───────────────────────
    print("\n[0/8] Parsing CSV...")
    courses_meta, course_profs = load_csv(csv_path)
    print(f"      {len(courses_meta)} unique courses found across "
          f"{len(set(s for s, _ in courses_meta))} subjects.")

    with app.app_context():

        # ── 1. Drop and recreate all tables ──────────────────────────────────
        print("\n[1/8] Recreating tables...")
        db.drop_all()
        db.create_all()
        print("      Done.")

        # ── 2. Semesters ─────────────────────────────────────────────────────
        print("[2/8] Seeding semesters...")
        semesters = {}
        for year in range(2022, 2027):
            for term in ['Spring', 'Summer', 'Fall', 'Winter']:
                s = Semester(term=term, year=year)
                db.session.add(s)
                semesters[(term, year)] = s
        db.session.flush()
        print(f"      {len(semesters)} semesters created.")

        # ── 3. Departments ───────────────────────────────────────────────────
        print("[3/8] Seeding departments...")
        dept_objects = {}
        subjects_in_csv = sorted(set(s for s, _ in courses_meta))
        missing_depts   = []

        for code in subjects_in_csv:
            name = DEPARTMENT_NAMES.get(code)
            if not name:
                name = code   # fallback: use code as name
                missing_depts.append(code)
            d = Department(dept_code=code, dept_name=name)
            db.session.add(d)
            dept_objects[code] = d

        db.session.flush()
        print(f"      {len(dept_objects)} departments created.")
        if missing_depts:
            print(f"      WARNING: No display name found for: {missing_depts}")

        # ── 4. Flag Reasons ──────────────────────────────────────────────────
        print("[4/8] Seeding flag reasons...")
        flag_reasons = ['Spam', 'Inappropriate Content', 'Plagiarism', 'Cheating']
        for reason in flag_reasons:
            db.session.add(FlagReason(reason_name=reason))
        db.session.flush()
        print(f"      {len(flag_reasons)} flag reasons created.")

        # ── 5. Professors ────────────────────────────────────────────────────
        print("[5/8] Seeding professors...")
        all_prof_names = set()
        for names in course_profs.values():
            all_prof_names.update(names)

        prof_id_map = {}
        for name in sorted(all_prof_names):
            result = db.session.execute(
                professor_table.insert().values(full_name=name)
            )
            prof_id_map[name] = result.inserted_primary_key[0]
        db.session.flush()
        print(f"      {len(prof_id_map)} professors created.")

        # ── 6. Courses + professor links ──────────────────────────────────────
        print("[6/8] Seeding courses...")
        course_objects = {}
        link_count = 0

        for (subject, number), (title, credits) in sorted(courses_meta.items()):
            dept = dept_objects.get(subject)
            if not dept:
                print(f"      WARNING: Skipping {subject} {number} — no department found.")
                continue

            c = Course(
                dept_id            = dept.dept_id,
                course_number      = number,
                course_title       = title,
                course_description = None,
            )
            db.session.add(c)
            db.session.flush()
            course_objects[(subject, number)] = c

            for prof_name in sorted(course_profs.get((subject, number), [])):
                pid = prof_id_map.get(prof_name)
                if pid:
                    db.session.execute(
                        course_professor_table.insert().values(
                            course_id    = c.course_id,
                            professor_id = pid,
                        )
                    )
                    link_count += 1

        print(f"      {len(course_objects)} courses created.")
        print(f"      {link_count} course–professor links created.")

        # ── 7. Test accounts ─────────────────────────────────────────────────
        print("[7/8] Seeding test accounts...")
        admin = User(
            first_name    = 'Admin',
            last_name     = 'User',
            email         = 'admin@southernct.edu',
            password_hash = generate_password_hash('Admin1234!').decode('utf-8'),
            role          = 'admin',
            is_active     = True,
        )
        db.session.add(admin)

        student = User(
            first_name    = 'Test',
            last_name     = 'Student',
            email         = 'student@southernct.edu',
            password_hash = generate_password_hash('Student1234!').decode('utf-8'),
            role          = 'user',
            is_active     = True,
        )
        db.session.add(student)
        db.session.flush()
        print("      admin@southernct.edu  / Admin1234!")
        print("      student@southernct.edu / Student1234!")

        # ── 8. Sample review ─────────────────────────────────────────────────
        print("[8/8] Seeding sample review...")
        csc_152   = course_objects.get(('CSC', '152'))
        fall_2025 = semesters.get(('Fall', 2025))
        if csc_152 and fall_2025:
            db.session.add(Review(
                course_id        = csc_152.course_id,
                user_id          = student.user_id,
                semester_id      = fall_2025.semester_id,
                rating_overall   = 4,
                workload_level   = 3,
                difficulty_level = 3,
                assessment_style = 'Weekly labs and a final project',
                review_text      = (
                    'Great intro course for anyone just starting out with programming. '
                    'The professor explains things clearly and the assignments are well structured. '
                    'Expect weekly coding labs and a final project at the end of the semester. '
                    'Would highly recommend for all CS majors.'
                ),
            ))
            print("      Sample review added to CSC 152 — Fall 2025.")
        else:
            print("      WARNING: CSC 152 or Fall 2025 semester not found — skipping sample review.")

        # ── Commit everything ─────────────────────────────────────────────────
        db.session.commit()

        # ── Summary ───────────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("Seed complete!")
        print("=" * 60)
        print(f"  Departments     : {len(dept_objects)}")
        print(f"  Courses         : {len(course_objects)}")
        print(f"  Professors      : {len(prof_id_map)}")
        print(f"  Prof links      : {link_count}")
        print(f"  Semesters       : {len(semesters)}")
        print(f"  Flag Reasons    : {len(flag_reasons)}")
        print()
        print("  Test Accounts:")
        print("    Admin   → admin@southernct.edu    / Admin1234!")
        print("    Student → student@southernct.edu  / Student1234!")
        print("=" * 60)


if __name__ == '__main__':
    seed()