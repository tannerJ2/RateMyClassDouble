'''
Course routes — search, browse, detail, review submission, likes.
'''

from datetime import datetime, timezone
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import current_user, login_required
from app.models import Course, Department, Review, ReviewLike, Material, Semester, Professor
from app.extensions import db
from sqlalchemy import func

courses = Blueprint('courses', __name__)


# ─────────────────────────────────────────────
# Home
# ─────────────────────────────────────────────
@courses.route('/')
@courses.route('/index')
def index():
    departments = Department.query.order_by(Department.dept_name).all()
    return render_template('courses/index.html', departments=departments)


# ─────────────────────────────────────────────
# Search — JSON endpoint used by the search page
# ─────────────────────────────────────────────
@courses.route('/search')
def search():
    q    = request.args.get('q', '').strip()
    dept = request.args.get('dept', '').strip()

    query = Course.query.join(Department, Course.dept_id == Department.dept_id)

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
        ).order_by(
            db.case((Department.dept_code.ilike(q), 0),      else_=1),
            db.case((Course.course_number.ilike(f'{q}%'), 0), else_=1),
            db.case((Course.course_title.ilike(f'{q}%'), 0),  else_=1),
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


# ─────────────────────────────────────────────
# Search page — department grid + course browser
# ─────────────────────────────────────────────
@courses.route('/courses')
def search_page():
    departments = Department.query.order_by(Department.dept_name).all()
    dept_counts = dict(
        db.session.query(Department.dept_code, func.count(Course.course_id))
        .join(Course, Course.dept_id == Department.dept_id)
        .group_by(Department.dept_code)
        .all()
    )
    return render_template('courses/search.html', departments=departments, dept_counts=dept_counts)


# ─────────────────────────────────────────────
# Course detail
# ─────────────────────────────────────────────
@courses.route('/course/<int:course_id>')
def course_detail(course_id):
    course     = Course.query.get_or_404(course_id)
    professors = course.professors.order_by(Professor.full_name).all()

    opinions     = Review.query.filter_by(course_id=course_id, review_type='opinion').all()
    descriptions = Review.query.filter_by(course_id=course_id, review_type='description').all()

    # Top 3 of each by like score for the carousel
    top_opinions     = sorted(opinions,     key=lambda r: r.like_score(), reverse=True)[:3]
    top_descriptions = sorted(descriptions, key=lambda r: r.like_score(), reverse=True)[:3]

    opinion_count     = len(opinions)
    description_count = len(descriptions)
    material_count    = Material.query.filter_by(course_id=course_id, is_removed=False).count()

    avg_difficulty = (
        db.session.query(func.avg(Review.difficulty_level))
        .filter_by(course_id=course_id, review_type='opinion')
        .scalar()
    )
    avg_rating = (
        db.session.query(func.avg(Review.rating_overall))
        .filter_by(course_id=course_id, review_type='opinion')
        .scalar()
    )

    user_opinion = user_description = None
    user_likes   = {}

    if current_user.is_authenticated:
        user_opinion = Review.query.filter_by(
            course_id=course_id, user_id=current_user.user_id, review_type='opinion'
        ).first()
        user_description = Review.query.filter_by(
            course_id=course_id, user_id=current_user.user_id, review_type='description'
        ).first()

        all_ids = [r.review_id for r in top_opinions + top_descriptions]
        if all_ids:
            likes      = ReviewLike.query.filter(
                ReviewLike.review_id.in_(all_ids),
                ReviewLike.user_id == current_user.user_id
            ).all()
            user_likes = {like.review_id: like.like_type for like in likes}

    return render_template(
        'courses/course_detail.html',
        course            = course,
        professors        = professors,
        opinions          = top_opinions,
        descriptions      = top_descriptions,
        opinion_count     = opinion_count,
        description_count = description_count,
        material_count    = material_count,
        avg_difficulty    = avg_difficulty,
        avg_rating        = avg_rating,
        user_opinion      = user_opinion,
        user_description  = user_description,
        user_likes        = user_likes,
    )


# ─────────────────────────────────────────────
# All opinions
# ─────────────────────────────────────────────
@courses.route('/course/<int:course_id>/opinions')
def all_opinions(course_id):
    course = Course.query.get_or_404(course_id)
    sort   = request.args.get('sort', 'liked')

    opinions = Review.query.filter_by(course_id=course_id, review_type='opinion').all()

    if sort == 'recent':
        opinions = sorted(opinions, key=lambda r: r.created_at, reverse=True)
    elif sort == 'yours' and current_user.is_authenticated:
        mine     = [r for r in opinions if r.user_id == current_user.user_id]
        others   = [r for r in opinions if r.user_id != current_user.user_id]
        opinions = mine + sorted(others, key=lambda r: r.like_score(), reverse=True)
    else:
        opinions = sorted(opinions, key=lambda r: r.like_score(), reverse=True)

    user_likes = {}
    if current_user.is_authenticated and opinions:
        ids   = [r.review_id for r in opinions]
        likes = ReviewLike.query.filter(
            ReviewLike.review_id.in_(ids),
            ReviewLike.user_id == current_user.user_id
        ).all()
        user_likes = {like.review_id: like.like_type for like in likes}

    return render_template(
        'courses/all_opinions.html',
        course     = course,
        opinions   = opinions,
        sort       = sort,
        user_likes = user_likes,
    )


# ─────────────────────────────────────────────
# All descriptions
# ─────────────────────────────────────────────
@courses.route('/course/<int:course_id>/descriptions')
def all_descriptions(course_id):
    course = Course.query.get_or_404(course_id)
    sort   = request.args.get('sort', 'liked')

    descriptions = Review.query.filter_by(course_id=course_id, review_type='description').all()

    if sort == 'recent':
        descriptions = sorted(descriptions, key=lambda r: r.created_at, reverse=True)
    elif sort == 'yours' and current_user.is_authenticated:
        mine         = [r for r in descriptions if r.user_id == current_user.user_id]
        others       = [r for r in descriptions if r.user_id != current_user.user_id]
        descriptions = mine + sorted(others, key=lambda r: r.like_score(), reverse=True)
    else:
        descriptions = sorted(descriptions, key=lambda r: r.like_score(), reverse=True)

    user_likes = {}
    if current_user.is_authenticated and descriptions:
        ids   = [r.review_id for r in descriptions]
        likes = ReviewLike.query.filter(
            ReviewLike.review_id.in_(ids),
            ReviewLike.user_id == current_user.user_id
        ).all()
        user_likes = {like.review_id: like.like_type for like in likes}

    return render_template(
        'courses/all_descriptions.html',
        course       = course,
        descriptions = descriptions,
        sort         = sort,
        user_likes   = user_likes,
    )


# ─────────────────────────────────────────────
# Submit choice — pick opinion or description
# ─────────────────────────────────────────────
@courses.route('/course/<int:course_id>/submit')
@login_required
def submit_choice(course_id):
    course = Course.query.get_or_404(course_id)

    user_opinion = Review.query.filter_by(
        course_id=course_id, user_id=current_user.user_id, review_type='opinion'
    ).first()
    user_description = Review.query.filter_by(
        course_id=course_id, user_id=current_user.user_id, review_type='description'
    ).first()

    return render_template(
        'courses/submit_choice.html',
        course           = course,
        user_opinion     = user_opinion,
        user_description = user_description,
    )


# ─────────────────────────────────────────────
# Submit opinion
# ─────────────────────────────────────────────
@courses.route('/course/<int:course_id>/submit/opinion', methods=['GET', 'POST'])
@login_required
def submit_opinion(course_id):
    course = Course.query.get_or_404(course_id)

    existing = Review.query.filter_by(
        course_id=course_id, user_id=current_user.user_id, review_type='opinion'
    ).first()
    if existing:
        flash('You have already submitted an opinion for this course. Edit it from My Reviews.', 'info')
        return redirect(url_for('courses.course_detail', course_id=course_id))

    semesters = Semester.query.order_by(Semester.year.desc(), Semester.term).all()

    if request.method == 'POST':
        semester_id      = request.form.get('semester_id', type=int)
        rating_overall   = request.form.get('rating_overall', type=int)
        workload_level   = request.form.get('workload_level', type=int)
        difficulty_level = request.form.get('difficulty_level', type=int)
        assessment_style = request.form.get('assessment_style', '').strip() or None
        review_text      = request.form.get('review_text', '').strip()

        errors = []
        if not semester_id:
            errors.append('Please select the semester you took this course.')
        if not rating_overall or not (1 <= rating_overall <= 5):
            errors.append('Please select an overall rating (1–5).')
        if not workload_level or not (1 <= workload_level <= 5):
            errors.append('Please select a workload level (1–5).')
        if not difficulty_level or not (1 <= difficulty_level <= 5):
            errors.append('Please select a difficulty level (1–5).')
        if len(review_text) < 30:
            errors.append('Your opinion must be at least 30 characters.')
        if len(review_text) > 2000:
            errors.append('Your opinion cannot exceed 2000 characters.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('courses/submit_opinion.html', course=course, semesters=semesters)

        db.session.add(Review(
            course_id        = course_id,
            user_id          = current_user.user_id,
            review_type      = 'opinion',
            semester_id      = semester_id,
            rating_overall   = rating_overall,
            workload_level   = workload_level,
            difficulty_level = difficulty_level,
            assessment_style = assessment_style,
            review_text      = review_text,
        ))
        db.session.commit()

        flash('Your opinion has been submitted!', 'success')
        return redirect(url_for('courses.all_opinions', course_id=course_id))

    return render_template('courses/submit_opinion.html', course=course, semesters=semesters)


# ─────────────────────────────────────────────
# Submit description
# ─────────────────────────────────────────────
@courses.route('/course/<int:course_id>/submit/description', methods=['GET', 'POST'])
@login_required
def submit_description(course_id):
    course = Course.query.get_or_404(course_id)

    existing = Review.query.filter_by(
        course_id=course_id, user_id=current_user.user_id, review_type='description'
    ).first()
    if existing:
        flash('You have already submitted a description for this course. Edit it from My Reviews.', 'info')
        return redirect(url_for('courses.course_detail', course_id=course_id))

    if request.method == 'POST':
        review_text = request.form.get('review_text', '').strip()

        if len(review_text) < 30:
            flash('Your description must be at least 30 characters.', 'danger')
            return render_template('courses/submit_description.html', course=course)
        if len(review_text) > 5000:
            flash('Your description cannot exceed 5000 characters.', 'danger')
            return render_template('courses/submit_description.html', course=course)

        db.session.add(Review(
            course_id   = course_id,
            user_id     = current_user.user_id,
            review_type = 'description',
            review_text = review_text,
        ))
        db.session.commit()

        flash('Your description has been submitted!', 'success')
        return redirect(url_for('courses.all_descriptions', course_id=course_id))

    return render_template('courses/submit_description.html', course=course)


# ─────────────────────────────────────────────
# Edit opinion
# ─────────────────────────────────────────────
@courses.route('/course/<int:course_id>/edit/opinion', methods=['GET', 'POST'])
@login_required
def edit_opinion(course_id):
    course    = Course.query.get_or_404(course_id)
    review    = Review.query.filter_by(
        course_id=course_id, user_id=current_user.user_id, review_type='opinion'
    ).first_or_404()
    semesters = Semester.query.order_by(Semester.year.desc(), Semester.term).all()

    if request.method == 'POST':
        semester_id      = request.form.get('semester_id', type=int)
        rating_overall   = request.form.get('rating_overall', type=int)
        workload_level   = request.form.get('workload_level', type=int)
        difficulty_level = request.form.get('difficulty_level', type=int)
        assessment_style = request.form.get('assessment_style', '').strip() or None
        review_text      = request.form.get('review_text', '').strip()

        errors = []
        if not semester_id:
            errors.append('Please select the semester you took this course.')
        if not rating_overall or not (1 <= rating_overall <= 5):
            errors.append('Please select an overall rating (1–5).')
        if not workload_level or not (1 <= workload_level <= 5):
            errors.append('Please select a workload level (1–5).')
        if not difficulty_level or not (1 <= difficulty_level <= 5):
            errors.append('Please select a difficulty level (1–5).')
        if len(review_text) < 30:
            errors.append('Your opinion must be at least 30 characters.')
        if len(review_text) > 2000:
            errors.append('Your opinion cannot exceed 2000 characters.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('courses/edit_opinion.html', course=course, review=review, semesters=semesters)

        review.semester_id      = semester_id
        review.rating_overall   = rating_overall
        review.workload_level   = workload_level
        review.difficulty_level = difficulty_level
        review.assessment_style = assessment_style
        review.review_text      = review_text
        review.is_edited        = True
        review.updated_at       = datetime.now(timezone.utc)
        db.session.commit()

        flash('Your opinion has been updated.', 'success')
        return redirect(url_for('courses.all_opinions', course_id=course_id) + f'#review-{review.review_id}')

    return render_template('courses/edit_opinion.html', course=course, review=review, semesters=semesters)


# ─────────────────────────────────────────────
# Edit description
# ─────────────────────────────────────────────
@courses.route('/course/<int:course_id>/edit/description', methods=['GET', 'POST'])
@login_required
def edit_description(course_id):
    course = Course.query.get_or_404(course_id)
    review = Review.query.filter_by(
        course_id=course_id, user_id=current_user.user_id, review_type='description'
    ).first_or_404()

    if request.method == 'POST':
        review_text = request.form.get('review_text', '').strip()

        if len(review_text) < 30:
            flash('Your description must be at least 30 characters.', 'danger')
            return render_template('courses/edit_description.html', course=course, review=review)
        if len(review_text) > 5000:
            flash('Your description cannot exceed 5000 characters.', 'danger')
            return render_template('courses/edit_description.html', course=course, review=review)

        review.review_text = review_text
        review.is_edited   = True
        review.updated_at  = datetime.now(timezone.utc)
        db.session.commit()

        flash('Your description has been updated.', 'success')
        return redirect(url_for('courses.all_descriptions', course_id=course_id) + f'#review-{review.review_id}')

    return render_template('courses/edit_description.html', course=course, review=review)


# ─────────────────────────────────────────────
# Like a review — AJAX POST
# Returns updated counts and score.
# Clicking the same type again removes the like.
# ─────────────────────────────────────────────
@courses.route('/review/<int:review_id>/like', methods=['POST'])
@login_required
def like_review(review_id):
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400

    review    = Review.query.get_or_404(review_id)
    like_type = request.json.get('like_type')

    if like_type not in ('really_helpful', 'helpful', 'not_helpful'):
        return jsonify({'error': 'Invalid like type'}), 400

    existing = ReviewLike.query.filter_by(
        review_id=review_id, user_id=current_user.user_id
    ).first()

    if existing:
        if existing.like_type == like_type:
            db.session.delete(existing)
            action = 'removed'
        else:
            existing.like_type = like_type
            action = 'updated'
    else:
        db.session.add(ReviewLike(
            review_id = review_id,
            user_id   = current_user.user_id,
            like_type = like_type,
        ))
        action = 'added'

    db.session.commit()
    db.session.refresh(review)

    return jsonify({
        'action': action,
        'counts': review.like_counts(),
        'score':  review.like_score(),
    })