'''

contains all the course search and detail route functions

'''

from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user
from app.models import Course, Department, Review, Material
from app.extensions import db
from sqlalchemy import func, text

courses = Blueprint('courses', __name__)


@courses.route('/')
@courses.route('/index')
def index():
    all_courses = (
        Course.query
        .join(Department, Course.dept_id == Department.dept_id)
        .add_columns(Department.dept_code, Department.dept_name)
        .order_by(Course.course_number)
        .all()
    )
    departments = Department.query.order_by(Department.dept_name).all()
    return render_template('courses/index.html', courses=all_courses, departments=departments)


@courses.route('/search')
def search():
    q    = request.args.get('q', '').strip()
    dept = request.args.get('dept', '').strip()

    query = Course.query.join(Department, Course.dept_id == Department.dept_id)

    # Department dropdown filter — applied first, hard filter by dept_code
    if dept:
        query = query.filter(Department.dept_code == dept)

    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Course.course_title.ilike(like),
                Course.course_number.ilike(like),
                Department.dept_code.ilike(like),
            )
        )
        # Ordering priority:
        # 1. Exact dept_code match (e.g. typing "MAT" → all MAT courses first)
        # 2. Course number starts with query
        # 3. Course title starts with query
        # 4. Everything else (contains the word somewhere)
        query = query.order_by(
            db.case(
                (Department.dept_code.ilike(q), 0),
                else_=1
            ),
            db.case(
                (Course.course_number.ilike(f'{q}%'), 0),
                else_=1
            ),
            db.case(
                (Course.course_title.ilike(f'{q}%'), 0),
                else_=1
            ),
            Course.course_number
        )
    else:
        query = query.order_by(Department.dept_code, Course.course_number)

    results = query.add_columns(Department.dept_code, Department.dept_name).limit(1500).all()

    return jsonify([
        {
            'id':        c.Course.course_id,
            'title':     c.Course.course_title,
            'number':    c.Course.course_number,
            'dept_code': c.dept_code,
            'dept_name': c.dept_name,
        }
        for c in results
    ])


@courses.route('/course/<int:course_id>')
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)

    # Get professors for this course via raw SQL (professor table is not in models.py yet)
    professors = db.session.execute(
        text('''
            SELECT p.full_name
            FROM professor p
            JOIN course_professor cp ON p.professor_id = cp.professor_id
            WHERE cp.course_id = :course_id
            ORDER BY p.full_name
        '''),
        {'course_id': course_id}
    ).fetchall()

    # Reviews for this course, newest first
    reviews = (
        Review.query
        .filter_by(course_id=course_id)
        .order_by(Review.created_at.desc())
        .all()
    )
    review_count = len(reviews)

    # Active material count
    material_count = (
        Material.query
        .filter_by(course_id=course_id, is_removed=False)
        .count()
    )

    # Average difficulty (None if no reviews yet)
    avg_difficulty = (
        db.session.query(func.avg(Review.difficulty_level))
        .filter_by(course_id=course_id)
        .scalar()
    )

    return render_template(
        'courses/course_detail.html',
        course          = course,
        professors      = professors,
        reviews         = reviews,
        review_count    = review_count,
        material_count  = material_count,
        avg_difficulty  = avg_difficulty,
    )

@courses.route('/courses')
def search_page():
    all_courses = (
        Course.query
        .join(Department, Course.dept_id == Department.dept_id)
        .add_columns(Department.dept_code, Department.dept_name)
        .order_by(Department.dept_code, Course.course_number)
        .all()
    )
    departments = Department.query.order_by(Department.dept_name).all()
    return render_template('courses/search.html', courses=all_courses, departments=departments)