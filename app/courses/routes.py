'''

contains all the course search and detail route functions

'''

from flask import Blueprint, render_template
from flask_login import current_user
from app.models import Course

courses = Blueprint('courses', __name__)

@courses.route('/')
@courses.route('/index')
def index():
    all_courses = Course.query.all()
    return render_template('courses/index.html', courses=all_courses)