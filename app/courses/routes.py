'''

contains all the course search and detail route functions

'''

from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user
from app.models import Course, Department
from app.extensions import db

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
    q = request.args.get('q', '').strip()
    dept = request.args.get('dept', '').strip()

    query = Course.query.join(Department, Course.dept_id == Department.dept_id)

    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Course.course_title.ilike(like),
                Course.course_number.ilike(like),
                Department.dept_code.ilike(like),
            )
        )
        # Exact dept_code match sorts to top, everything else after
        query = query.order_by(
            db.case(
                (Department.dept_code.ilike(q), 0),
                else_=1
            ),
            Course.course_number
        )
    else:
        query = query.order_by(Course.course_number)

    if dept:
        query = query.filter(Department.dept_code == dept)

    results = query.add_columns(Department.dept_code, Department.dept_name).limit(100).all()

    return jsonify([
        {
            'id': c.Course.course_id,
            'title': c.Course.course_title,
            'number': c.Course.course_number,
            'dept_code': c.dept_code,
            'dept_name': c.dept_name,
        }
        for c in results
    ])