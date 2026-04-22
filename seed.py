# =============================================================================
# RateMyClass — Database Seed Script
# Source: courses_Fall_2026.csv (real SCSU Fall 2026 catalogue)
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
# PROFESSOR RULES (per spec):
#   - Each professor listed only once per course, even if they teach
#     multiple sections of the same course.
#   - If a course has any real professor, TBA Staff is excluded entirely.
#   - If ALL sections are TBA Staff, the course is listed with TBA Staff once.
#   - Instructor pronouns and HTML entities are cleaned automatically.




#below is for in the future if i want to makke it so it doesnt delete everything
#when running the seed file

# Instead of drop_all/create_all
#       db.create_all()  # only creates tables if they don't exist, never drops

# And for departments, check before inserting
#       if not Department.query.filter_by(dept_code=code).first():
#           d = Department(dept_code=code, dept_name=name)
#           db.session.add(d)
# =============================================================================

from dotenv import load_dotenv
load_dotenv()


import csv
import html
import os
import re

from flask_bcrypt import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Course, Department, FlagReason, Professor, Review, Semester, User

app = create_app()


# =============================================================================
# DEPARTMENT CODE → FULL NAME
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
    'CMD':  'Communication Disorders',
    'CMS':  'Communication Studies',
    'COE':  'Counselor Education',
    'CTR':  'Cooperative Education',
    'CRM':  'Criminology',
    'CSC':  'Computer Science',
    'DBA':  'Doctor of Business Administration',
    'DES':  'Design',
    'DGH':  'Digital Humanities',
    'DSC':  'Data Science',
    'ECO':  'Economics',
    'EDL':  'Educational Leadership',
    'EDU':  'Education',
    'EGR':  'Engineering',
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
    'IBD':  'Interdisciplinary Biology',
    'IDS':  'Interdisciplinary Studies',
    'ILS':  'Information & Library Science',
    'INQ':  'Inquiry & Research',
    'ITA':  'Italian',
    'JRN':  'Journalism',
    'JST':  'Jewish Studies',
    'LAC':  'Latin American & Caribbean Studies',
    'LAT':  'Latin',
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
    'T2GA': 'Transfer General Education',
    'THE':  'Tourism & Hospitality Education',
    'THR':  'Theatre',
    'TSL':  'Teaching of Second Languages',
    'WGS':  "Women's & Gender Studies",
    'WLL':  'World Languages & Literatures',
}


# =============================================================================
# HELPER — parse raw instructor string into clean professor name list
# =============================================================================

def parse_instructors(raw: str) -> list[str]:
    if not raw or not raw.strip():
        return []

    raw = html.unescape(raw)
    parts = [p.strip() for p in raw.split(';')]

    cleaned = []
    for part in parts:
        if not part:
            continue
        name = re.sub(r'\s*\(.*?\)', '', part).strip()
        name = re.sub(r'\s+', ' ', name).strip()
        if name:
            cleaned.append(name)

    real_names = [n for n in cleaned if n.upper() != 'TBA STAFF']
    if real_names:
        return real_names
    elif cleaned:
        return ['TBA Staff']
    return []


# =============================================================================
# CSV PARSING
# =============================================================================

def load_csv(filepath: str):
    courses_meta = {}
    course_profs = {}

    with open(filepath, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            subject = row['Subject'].strip()
            number  = row['Course Number'].strip()
            title   = html.unescape(row['Title'].strip())
            credits = row['Credits'].strip()
            key     = (subject, number)

            if key not in courses_meta:
                courses_meta[key] = (title, credits)
                course_profs[key] = set()

            names = parse_instructors(row['Instructor'])
            for name in names:
                course_profs[key].add(name)

    # Post-process TBA Staff rule
    for key in course_profs:
        real = {n for n in course_profs[key] if n.upper() != 'TBA STAFF'}
        if real:
            course_profs[key] = real
        elif not course_profs[key]:
            course_profs[key] = {'TBA Staff'}

    return courses_meta, course_profs


# =============================================================================
# SEED
# =============================================================================

def seed():
    csv_path = os.path.join(os.path.dirname(__file__), 'Spring_2026_Courses.csv')

    if not os.path.exists(csv_path):
        print(f"\n[ERROR] CSV file not found at:\n  {csv_path}")
        print("Place Spring_2026_Courses.csv in the same folder as seed.py and retry.\n")
        return

    print("=" * 60)
    print("RateMyClass — Database Seeder")
    print("=" * 60)

    print("\n[0/8] Parsing CSV...")
    courses_meta, course_profs = load_csv(csv_path)
    print(f"      {len(courses_meta)} unique courses found across "
          f"{len(set(s for s, _ in courses_meta))} subjects.")

    with app.app_context():

        # 1. Drop and recreate all tables
        print("\n[1/6] Recreating tables...")
        db.drop_all()
        db.create_all()
        print("      Done.")

        # 2. Semesters
        print("[2/6] Seeding semesters...")
        semesters = {}
        for year in range(2026, 2027):
            for term in ['Spring', 'Summer', 'Fall', 'Winter']:
                s = Semester(term=term, year=year)
                db.session.add(s)
                semesters[(term, year)] = s
        db.session.flush()
        print(f"      {len(semesters)} semesters created.")

        # 3. Departments
        print("[3/6] Seeding departments...")
        dept_objects = {}
        subjects_in_csv = sorted(set(s for s, _ in courses_meta))
        missing_depts = []

        for code in subjects_in_csv:
            name = DEPARTMENT_NAMES.get(code)
            if not name:
                name = code
                missing_depts.append(code)
            d = Department(dept_code=code, dept_name=name)
            db.session.add(d)
            dept_objects[code] = d

        db.session.flush()
        print(f"      {len(dept_objects)} departments created.")
        if missing_depts:
            print(f"      WARNING: No display name found for: {missing_depts}")

        # 4. Flag Reasons
        print("[4/6] Seeding flag reasons...")
        flag_reasons = ['Spam', 'Inappropriate Content', 'Plagiarism', 'Cheating']
        for reason in flag_reasons:
            db.session.add(FlagReason(reason_name=reason))
        db.session.flush()
        print(f"      {len(flag_reasons)} flag reasons created.")

        # 5. Professors — now using the proper Professor model
        print("[5/6] Seeding professors...")
        all_prof_names = set()
        for names in course_profs.values():
            all_prof_names.update(names)

        prof_objects = {}
        for name in sorted(all_prof_names):
            p = Professor(full_name=name)
            db.session.add(p)
            prof_objects[name] = p

        db.session.flush()
        print(f"      {len(prof_objects)} professors created.")

        # 6. Courses + professor links — now using ORM relationships
        print("[6/6] Seeding courses...")
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

            # Link professors via ORM relationship instead of raw SQL
            for prof_name in sorted(course_profs.get((subject, number), [])):
                prof = prof_objects.get(prof_name)
                if prof:
                    c.professors.append(prof)
                    link_count += 1

        db.session.flush()
        print(f"      {len(course_objects)} courses created.")
        print(f"      {link_count} course–professor links created.")


        db.session.commit()

        print("\n" + "=" * 60)
        print("Seed complete!")
        print("=" * 60)
        print(f"  Departments     : {len(dept_objects)}")
        print(f"  Courses         : {len(course_objects)}")
        print(f"  Professors      : {len(prof_objects)}")
        print(f"  Prof links      : {link_count}")
        print(f"  Semesters       : {len(semesters)}")
        print(f"  Flag Reasons    : {len(flag_reasons)}")
        print()
        print("=" * 60)


if __name__ == '__main__':
    seed()