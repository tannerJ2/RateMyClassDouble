'''
Course routes — search, browse, detail, review submission, likes.
'''

from datetime import datetime, timezone
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import current_user, login_required
from app.models import Course, Department, Review, ReviewLike, Material, MaterialLike, Semester, Professor, SavedCourse, SavedMaterial, FlagReason
from app.extensions import db
from sqlalchemy import func, case
from sqlalchemy.orm import joinedload

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
    q        = request.args.get('q', '').strip()
    dept     = request.args.get('dept', '').strip()
    sort_by  = request.args.get('sort', '').strip()
    dir_     = request.args.get('dir', 'desc').strip()
    page     = request.args.get('page', 1, type=int)
    per_page = 20

    # ── Rating aggregate subquery — single JOIN eliminates N+1 queries ────────
    rating_sq = (
        db.session.query(
            Review.course_id,
            func.avg(Review.rating_overall).label('avg_rating'),
            func.avg(Review.workload_level).label('avg_workload'),
            func.avg(Review.difficulty_level).label('avg_difficulty'),
            func.count(Review.review_id).label('rating_count'),
        )
        .filter(Review.review_type.in_(['opinion', 'rating']))
        .group_by(Review.course_id)
        .subquery()
    )

    # ── Shared filter conditions (reused for count + main query) ──────────────
    filters = []
    if dept:
        filters.append(Department.dept_code == dept)
    if q:
        like      = f'%{q}%'
        concat_cn = func.concat(Department.dept_code, ' ', Course.course_number)
        filters.append(db.or_(
            Course.course_title.ilike(like),
            Course.course_number.ilike(like),
            Department.dept_code.ilike(like),
            concat_cn.ilike(like),
        ))

    # ── Lightweight count (no rating join needed) ─────────────────────────────
    count_q = (
        db.session.query(func.count(Course.course_id))
        .join(Department, Course.dept_id == Department.dept_id)
    )
    for f in filters:
        count_q = count_q.filter(f)
    total = count_q.scalar() or 0

    # ── Main query with rating aggregates ─────────────────────────────────────
    query = (
        db.session.query(
            Course,
            Department.dept_code,
            Department.dept_name,
            func.coalesce(rating_sq.c.avg_rating,    0).label('avg_rating'),
            func.coalesce(rating_sq.c.avg_workload,   0).label('avg_workload'),
            func.coalesce(rating_sq.c.avg_difficulty, 0).label('avg_difficulty'),
            func.coalesce(rating_sq.c.rating_count,   0).label('rating_count'),
        )
        .join(Department, Course.dept_id == Department.dept_id)
        .outerjoin(rating_sq, Course.course_id == rating_sq.c.course_id)
    )
    for f in filters:
        query = query.filter(f)

    # ── Ordering ──────────────────────────────────────────────────────────────
    sort_cols = {
        'avg_rating':     rating_sq.c.avg_rating,
        'avg_workload':   rating_sq.c.avg_workload,
        'avg_difficulty': rating_sq.c.avg_difficulty,
    }
    if sort_by in sort_cols:
        col = sort_cols[sort_by]
        query = query.order_by(
            col.desc() if dir_ == 'desc' else col.asc(),
            Department.dept_code,
            Course.course_number,
        )
    elif q:
        concat_cn = func.concat(Department.dept_code, ' ', Course.course_number)
        query = query.order_by(
            db.case((Department.dept_code.ilike(q), 0),         else_=1),
            db.case((concat_cn.ilike(f'{q}%'), 0),              else_=1),
            db.case((Course.course_number.ilike(f'{q}%'), 0),   else_=1),
            db.case((Course.course_title.ilike(f'{q}%'), 0),    else_=1),
            Course.course_number,
        )
    else:
        query = query.order_by(Department.dept_code, Course.course_number)

    # ── Paginate ──────────────────────────────────────────────────────────────
    pages   = max(1, -(-total // per_page))
    results = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'courses': [
            {
                'id':             r.Course.course_id,
                'title':          r.Course.course_title,
                'number':         r.Course.course_number,
                'dept_code':      r.dept_code,
                'dept_name':      r.dept_name,
                'avg_rating':     round(float(r.avg_rating),     1),
                'avg_workload':   round(float(r.avg_workload),   1),
                'avg_difficulty': round(float(r.avg_difficulty), 1),
                'rating_count':   int(r.rating_count),
            }
            for r in results
        ],
        'total':    total,
        'page':     page,
        'per_page': per_page,
        'pages':    pages,
    })

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
    saved_course_ids = set()
    if current_user.is_authenticated:
        saved_course_ids = {
            sc.course_id
            for sc in SavedCourse.query.filter_by(user_id=current_user.user_id).all()
        }
    return render_template('courses/search.html',
        departments      = departments,
        dept_counts      = dept_counts,
        saved_course_ids = saved_course_ids,
    )

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
    quick_rate_count  = Review.query.filter_by(
        course_id=course_id, review_type='rating'
    ).count()
    rating_count      = opinion_count + quick_rate_count
    
    description_count = len(descriptions)
    like_score = func.coalesce(func.sum(case(
        (MaterialLike.like_type == 'really_helpful', 2),
        (MaterialLike.like_type == 'helpful', 1),
        else_=0
    )), 0)
    active_materials = (
        Material.query
        .outerjoin(Material.likes)
        .filter(Material.course_id == course_id, Material.is_removed.is_(False))
        .group_by(Material.material_id)
        .order_by(like_score.desc(), Material.created_at.desc())
        .limit(3)
        .all()
    )
    material_count = (
        Material.query
        .filter_by(course_id=course_id, is_removed=False)
        .count()
    )

    all_ratings = (
        Review.query
        .filter(
            Review.course_id == course_id,
            Review.review_type.in_(['opinion', 'rating'])
        )
        .with_entities(Review.rating_overall, Review.workload_level, Review.difficulty_level)
        .all()
    )

    if all_ratings:
        avg_rating     = round(sum(r[0] for r in all_ratings) / len(all_ratings), 2)
        avg_workload   = round(sum(r[1] for r in all_ratings) / len(all_ratings), 2)
        avg_difficulty = round(sum(r[2] for r in all_ratings) / len(all_ratings), 2)
    else:
        avg_rating     = None
        avg_workload   = None
        avg_difficulty = None

    user_opinion = user_description = None
    user_likes   = {}
    is_course_saved    = False
    saved_course_note  = ''
    saved_material_ids = set()
    user_quick_rating  = None

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

        user_quick_rating = Review.query.filter_by(
            user_id=current_user.user_id,
            course_id=course_id,
            review_type='rating'
        ).first()

        sc = SavedCourse.query.filter_by(
            user_id=current_user.user_id, course_id=course_id
        ).first()
        is_course_saved   = sc is not None
        saved_course_note = sc.note or '' if sc else ''

        if active_materials:
            mat_ids    = [m.material_id for m in active_materials]
            saved_mats = SavedMaterial.query.filter(
                SavedMaterial.user_id    == current_user.user_id,
                SavedMaterial.material_id.in_(mat_ids)
            ).all()
            saved_material_ids = {sm.material_id for sm in saved_mats}


    return render_template(
        'courses/course_detail.html',
        course             = course,
        professors         = professors,
        opinions           = top_opinions,
        descriptions       = top_descriptions,
        opinion_count      = opinion_count,
        description_count  = description_count,
        material_count     = material_count,
        active_materials   = active_materials,
        avg_difficulty     = avg_difficulty,
        avg_workload       = avg_workload,
        avg_rating         = avg_rating,
        user_opinion       = user_opinion,
        user_description   = user_description,
        user_likes         = user_likes,
        is_course_saved    = is_course_saved,
        saved_course_note  = saved_course_note,
        saved_material_ids   = saved_material_ids,
        user_quick_rating    = user_quick_rating,
        rating_count         = rating_count
    )


# ─────────────────────────────────────────────
# All opinions
# ─────────────────────────────────────────────
@courses.route('/course/<int:course_id>/opinions')
def all_opinions(course_id):
    course   = Course.query.get_or_404(course_id)
    sort     = request.args.get('sort', 'liked')
    page     = request.args.get('page', 1, type=int)
    per_page = 15

    # ── Like score subquery — eliminates N+1 scoring in Python ───────────────
    like_sq = (
        db.session.query(
            ReviewLike.review_id,
            func.sum(case(
                (ReviewLike.like_type == 'really_helpful', 2),
                (ReviewLike.like_type == 'helpful', 1),
                else_=0
            )).label('score')
        )
        .group_by(ReviewLike.review_id)
        .subquery()
    )

    base = (
        db.session.query(Review)
        .filter(Review.course_id == course_id, Review.review_type == 'opinion')
        .outerjoin(like_sq, Review.review_id == like_sq.c.review_id)
    )

    if sort == 'recent':
        base = base.order_by(Review.created_at.desc())
    elif sort == 'yours' and current_user.is_authenticated:
        base = base.order_by(
            db.case((Review.user_id == current_user.user_id, 0), else_=1),
            func.coalesce(like_sq.c.score, 0).desc(),
            Review.created_at.desc(),
        )
    else:
        base = base.order_by(
            func.coalesce(like_sq.c.score, 0).desc(),
            Review.created_at.desc(),
        )

    total    = Review.query.filter_by(course_id=course_id, review_type='opinion').count()
    pages    = max(1, -(-total // per_page))
    opinions = base.offset((page - 1) * per_page).limit(per_page).all()

    user_likes = {}
    if current_user.is_authenticated and opinions:
        ids        = [r.review_id for r in opinions]
        likes      = ReviewLike.query.filter(
            ReviewLike.review_id.in_(ids),
            ReviewLike.user_id == current_user.user_id
        ).all()
        user_likes = {like.review_id: like.like_type for like in likes}

    flag_reasons = FlagReason.query.all()
    return render_template(
        'courses/all_opinions.html',
        course       = course,
        opinions     = opinions,
        sort         = sort,
        user_likes   = user_likes,
        flag_reasons = flag_reasons,
        page         = page,
        pages        = pages,
        total        = total,
        per_page     = per_page,
    )


# ─────────────────────────────────────────────
# All descriptions
# ─────────────────────────────────────────────
@courses.route('/course/<int:course_id>/descriptions')
def all_descriptions(course_id):
    course   = Course.query.get_or_404(course_id)
    sort     = request.args.get('sort', 'liked')
    page     = request.args.get('page', 1, type=int)
    per_page = 15

    # ── Like score subquery ───────────────────────────────────────────────────
    like_sq = (
        db.session.query(
            ReviewLike.review_id,
            func.sum(case(
                (ReviewLike.like_type == 'really_helpful', 2),
                (ReviewLike.like_type == 'helpful', 1),
                else_=0
            )).label('score')
        )
        .group_by(ReviewLike.review_id)
        .subquery()
    )

    base = (
        db.session.query(Review)
        .filter(Review.course_id == course_id, Review.review_type == 'description')
        .outerjoin(like_sq, Review.review_id == like_sq.c.review_id)
    )

    if sort == 'recent':
        base = base.order_by(Review.created_at.desc())
    elif sort == 'yours' and current_user.is_authenticated:
        base = base.order_by(
            db.case((Review.user_id == current_user.user_id, 0), else_=1),
            func.coalesce(like_sq.c.score, 0).desc(),
            Review.created_at.desc(),
        )
    else:
        base = base.order_by(
            func.coalesce(like_sq.c.score, 0).desc(),
            Review.created_at.desc(),
        )

    total        = Review.query.filter_by(course_id=course_id, review_type='description').count()
    pages        = max(1, -(-total // per_page))
    descriptions = base.offset((page - 1) * per_page).limit(per_page).all()

    user_likes = {}
    if current_user.is_authenticated and descriptions:
        ids        = [r.review_id for r in descriptions]
        likes      = ReviewLike.query.filter(
            ReviewLike.review_id.in_(ids),
            ReviewLike.user_id == current_user.user_id
        ).all()
        user_likes = {like.review_id: like.like_type for like in likes}

    flag_reasons = FlagReason.query.all()
    return render_template(
        'courses/all_descriptions.html',
        course       = course,
        descriptions = descriptions,
        sort         = sort,
        user_likes   = user_likes,
        flag_reasons = flag_reasons,
        page         = page,
        pages        = pages,
        total        = total,
        per_page     = per_page,
    )

@courses.route('/course/<int:course_id>/materials')
def all_materials(course_id):
    course   = Course.query.get_or_404(course_id)
    sort     = request.args.get('sort', 'recent')
    pin_id   = request.args.get('pin', type=int)
    page     = request.args.get('page', 1, type=int)
    per_page = 15

    # ── Like score subquery ───────────────────────────────────────────────────
    like_sq = (
        db.session.query(
            MaterialLike.material_id,
            func.sum(case(
                (MaterialLike.like_type == 'really_helpful', 2),
                (MaterialLike.like_type == 'helpful', 1),
                else_=0
            )).label('score')
        )
        .group_by(MaterialLike.material_id)
        .subquery()
    )

    # ── Fetch saved IDs upfront — needed for ORDER BY ─────────────────────────
    saved_material_ids  = set()
    user_material_likes = {}

    if current_user.is_authenticated:
        saved_rows = (
            db.session.query(SavedMaterial.material_id)
            .join(Material, SavedMaterial.material_id == Material.material_id)
            .filter(
                SavedMaterial.user_id == current_user.user_id,
                Material.course_id   == course_id,
                Material.is_removed  == False,
            )
            .all()
        )
        saved_material_ids = {row.material_id for row in saved_rows}

    # ── Base query ────────────────────────────────────────────────────────────
    base = (
        Material.query
        .filter_by(course_id=course_id, is_removed=False)
        .outerjoin(like_sq, Material.material_id == like_sq.c.material_id)
    )

    # ── ORDER BY: pin first, saved second, then user-chosen sort ─────────────
    order_clauses = []

    if pin_id:
        order_clauses.append(db.case((Material.material_id == pin_id, 0), else_=1))

    if saved_material_ids:
        order_clauses.append(
            db.case((Material.material_id.in_(list(saved_material_ids)), 0), else_=1)
        )

    if sort == 'liked':
        order_clauses += [func.coalesce(like_sq.c.score, 0).desc(), Material.created_at.desc()]
    elif sort == 'type':
        order_clauses += [Material.material_type, Material.created_at.desc()]
    elif sort == 'yours' and current_user.is_authenticated:
        order_clauses += [
            db.case((Material.user_id == current_user.user_id, 0), else_=1),
            Material.created_at.desc(),
        ]
    else:
        order_clauses.append(Material.created_at.desc())

    base = base.order_by(*order_clauses)

    total     = Material.query.filter_by(course_id=course_id, is_removed=False).count()
    pages     = max(1, -(-total // per_page))
    materials = base.offset((page - 1) * per_page).limit(per_page).all()

    mat_ids = [m.material_id for m in materials]

    # ── Single query for all like counts on this page ─────────────────────────
    raw_counts = db.session.query(
        MaterialLike.material_id,
        MaterialLike.like_type,
        func.count(MaterialLike.like_id)
    ).filter(MaterialLike.material_id.in_(mat_ids)).group_by(
        MaterialLike.material_id, MaterialLike.like_type
    ).all() if mat_ids else []

    counts_map = {}
    for mid, ltype, cnt in raw_counts:
        counts_map.setdefault(mid, {'really_helpful': 0, 'helpful': 0, 'not_helpful': 0})[ltype] = cnt
    for m in materials:
        counts_map.setdefault(m.material_id, {'really_helpful': 0, 'helpful': 0, 'not_helpful': 0})

    if current_user.is_authenticated and mat_ids:
        user_material_likes = {
            ml.material_id: ml.like_type
            for ml in MaterialLike.query.filter(
                MaterialLike.user_id == current_user.user_id,
                MaterialLike.material_id.in_(mat_ids)
            ).all()
        }

    flag_reasons = FlagReason.query.all()
    return render_template(
        'courses/all_materials.html',
        course               = course,
        materials            = materials,
        sort                 = sort,
        saved_material_ids   = saved_material_ids,
        user_material_likes  = user_material_likes,
        counts_map           = counts_map,
        pin_id               = pin_id,
        flag_reasons         = flag_reasons,
        page                 = page,
        pages                = pages,
        total                = total,
        per_page             = per_page,
    )

@courses.route('/material/<int:material_id>/view')
def view_material(material_id):
    material = Material.query.get_or_404(material_id)
    if material.is_removed:
        flash('This material has been removed.', 'danger')
        return redirect(url_for('courses.course_detail', course_id=material.course_id))
    return render_template('courses/view_material.html', material=material)


@courses.route('/material/<int:material_id>/serve')
def serve_material(material_id):
    import os
    from flask import current_app, send_from_directory
    from app.models import Material

    material = Material.query.get_or_404(material_id)
    if material.is_removed:
        return 'Removed', 404
    from app.storage import get_file_response
    return get_file_response(material.file_url, inline=True)
    
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

    user_quick_rating = Review.query.filter_by(
        user_id=current_user.user_id,
        course_id=course_id,
        review_type='rating'
    ).first()

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
            return render_template('courses/submit_opinion.html',
                course            = course,
                semesters         = semesters,
                user_quick_rating = user_quick_rating,
                prev_semester_id  = semester_id,
                prev_rating       = rating_overall,
                prev_workload     = workload_level,
                prev_difficulty   = difficulty_level,
                prev_assessment   = assessment_style or '',
                prev_text         = review_text,
            )

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

        if user_quick_rating:
            db.session.delete(user_quick_rating)
            db.session.commit()

        flash('Your opinion has been submitted!', 'success')
        return redirect(url_for('courses.all_opinions', course_id=course_id))

    return render_template('courses/submit_opinion.html',
        course            = course,
        semesters         = semesters,
        user_quick_rating = user_quick_rating,
    )

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
            return render_template('courses/submit_description.html', course=course, prev_text=review_text)
        if len(review_text) > 5000:
            flash('Your description cannot exceed 5000 characters.', 'danger')
            return render_template('courses/submit_description.html', course=course, prev_text=review_text)

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


# ─────────────────────────────────────────────
# Like material — AJAX POST
# ─────────────────────────────────────────────
@courses.route('/material/<int:material_id>/like', methods=['POST'])
@login_required
def like_material(material_id):
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400

    material  = db.get_or_404(Material, material_id)
    like_type = request.json.get('like_type')

    if material.is_removed:
        return jsonify({'error': 'Material no longer available'}), 404

    if like_type not in ('really_helpful', 'helpful', 'not_helpful'):
        return jsonify({'error': 'Invalid like type'}), 400

    existing = MaterialLike.query.filter_by(
        material_id=material_id, user_id=current_user.user_id
    ).first()

    if existing:
        if existing.like_type == like_type:
            db.session.delete(existing)
            action = 'removed'
        else:
            existing.like_type = like_type
            action = 'updated'
    else:
        db.session.add(MaterialLike(
            material_id = material_id,
            user_id     = current_user.user_id,
            like_type   = like_type,
        ))
        action = 'added'

    db.session.commit()

    score, counts = material.get_like_data()
    return jsonify({
        'action': action,
        'counts': counts,
        'score':  score,
    })

# ─────────────────────────────────────────────
# Quick rate — AJAX POST
# ─────────────────────────────────────────────
@courses.route('/course/<int:course_id>/quick-rate', methods=['POST'])
@login_required
def quick_rate(course_id):
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400

    Course.query.get_or_404(course_id)

    rating_overall   = request.json.get('rating_overall')
    workload_level   = request.json.get('workload_level')
    difficulty_level = request.json.get('difficulty_level')

    if not all([rating_overall, workload_level, difficulty_level]):
        return jsonify({'error': 'All three ratings are required'}), 400

    if not all(1 <= v <= 5 for v in [rating_overall, workload_level, difficulty_level]):
        return jsonify({'error': 'Ratings must be between 1 and 5'}), 400

    # If user has a full opinion, update its ratings directly
    opinion = Review.query.filter_by(
        user_id=current_user.user_id,
        course_id=course_id,
        review_type='opinion'
    ).first()

    if opinion:
        opinion.rating_overall   = rating_overall
        opinion.workload_level   = workload_level
        opinion.difficulty_level = difficulty_level
        opinion.updated_at       = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({'action': 'updated'})

    # Otherwise create or update a quick rating
    existing = Review.query.filter_by(
        user_id=current_user.user_id,
        course_id=course_id,
        review_type='rating'
    ).first()

    if existing:
        existing.rating_overall   = rating_overall
        existing.workload_level   = workload_level
        existing.difficulty_level = difficulty_level
        existing.updated_at       = datetime.now(timezone.utc)
        action = 'updated'
    else:
        db.session.add(Review(
            user_id          = current_user.user_id,
            course_id        = course_id,
            review_type      = 'rating',
            rating_overall   = rating_overall,
            workload_level   = workload_level,
            difficulty_level = difficulty_level,
            review_text      = '',
        ))
        action = 'created'

    db.session.commit()
    return jsonify({'action': action})



# ─────────────────────────────────────────────
# Upload material
# Security measures applied (see inline comments).
# ─────────────────────────────────────────────
@courses.route('/course/<int:course_id>/upload', methods=['GET', 'POST'])
@login_required
def upload_material(course_id):
    import os, uuid
    from flask import current_app
    from werkzeug.utils import secure_filename
    from app.models import Material, Semester

    course    = Course.query.get_or_404(course_id)
    semesters = Semester.query.order_by(Semester.year.desc(), Semester.term).all()

    if request.method == 'POST':
        title         = request.form.get('title', '').strip()
        description   = request.form.get('description', '').strip() or None
        material_type = request.form.get('material_type', '').strip()
        semester_id   = request.form.get('semester_id', type=int)
        file          = request.files.get('file')

        errors = []

        # ── Field validation ──────────────────────────────────────────────────
        if not title:
            errors.append('Title is required.')
        elif len(title) > 255:
            errors.append('Title must be 255 characters or fewer.')

        if description and len(description) > 1000:
            errors.append('Description must be 1000 characters or fewer.')

        if material_type not in ('notes', 'study_guide', 'exam', 'other'):
            errors.append('Please select a valid material type.')

        if not semester_id:
            errors.append('Please select the semester this material is from.')

        # ── File validation ───────────────────────────────────────────────────
        if not file or file.filename == '':
            errors.append('Please select a PDF file to upload.')
        else:
            # SECURITY 1: sanitize the original filename (strips path traversal,
            # null bytes, shell metacharacters).
            original_name = secure_filename(file.filename)

            # SECURITY 2: extension whitelist — only .pdf allowed.
            ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
            if ext != 'pdf':
                errors.append('Only PDF files (.pdf) are allowed.')
            else:
                # SECURITY 3: server-side size check independent of
                # MAX_CONTENT_LENGTH (defence-in-depth).
                file.seek(0, 2)          # seek to end of stream
                file_size = file.tell()  # bytes
                file.seek(0)             # reset for reading
                MAX_BYTES = 10 * 1024 * 1024  # 10 MB

                if file_size == 0:
                    errors.append('The uploaded file is empty.')
                elif file_size > MAX_BYTES:
                    errors.append('File must be 10 MB or smaller.')
                else:
                    # SECURITY 4: magic-byte check — read the first 4 bytes
                    # and verify the PDF signature (%PDF).  This catches files
                    # that have been renamed to .pdf but are not actually PDFs
                    # (e.g. a .exe or .js with a renamed extension).
                    header = file.read(4)
                    file.seek(0)
                    if header != b'%PDF':
                        errors.append('The file does not appear to be a valid PDF.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template(
                'courses/upload_material.html',
                course           = course,
                semesters        = semesters,
                prev_title       = title,
                prev_description = description or '',
                prev_type        = material_type,
                prev_semester_id = semester_id,
            )

        # ── Save file securely ────────────────────────────────────────────────
        # SECURITY 5: replace the original filename with a random UUID on disk.
        # The original name is never written to the filesystem, which prevents
        # path traversal and avoids leaking user-supplied strings to the OS.

        # SECURITY 6: upload directory lives in instance/ which is outside
        # static/ — the web server (Nginx) must NOT alias this path, so files
        # can only be retrieved through the controlled download route below.
        from app.storage import upload_file
        stored_name = upload_file(file, original_name)

        # ── Persist metadata ──────────────────────────────────────────────────
        material = Material(
            course_id     = course_id,
            user_id       = current_user.user_id,
            semester_id   = semester_id,
            title         = title,
            description   = description,
            file_url      = stored_name,   # UUID filename only — not a public URL
            material_type = material_type,
        )
        db.session.add(material)
        db.session.commit()

        flash('Material uploaded successfully!', 'success')
        return redirect(url_for('courses.course_detail', course_id=course_id))

    return render_template(
        'courses/upload_material.html',
        course=course, semesters=semesters
    )


# ─────────────────────────────────────────────
# Download / serve a material file
# Streams through Flask — never directly accessible from disk.
# ─────────────────────────────────────────────
@courses.route('/material/<int:material_id>/download')
def download_material(material_id):
    import os
    from flask import current_app, send_from_directory
    from werkzeug.utils import secure_filename
    from app.models import Material

    material = Material.query.get_or_404(material_id)
    if material.is_removed:
        flash('This material has been removed and is no longer available.', 'danger')
        return redirect(url_for('courses.course_detail', course_id=material.course_id))
    from werkzeug.utils import secure_filename
    from app.storage import get_file_response
    safe_title    = secure_filename(material.title) or 'material'
    download_name = safe_title + '.pdf'
    return get_file_response(material.file_url, download_name=download_name, inline=False)

@courses.route('/my/reviews')
@login_required
def my_reviews():
    opinions = (
        Review.query
        .filter_by(user_id=current_user.user_id, review_type='opinion')
        .options(
            joinedload(Review.course).joinedload(Course.department),
            joinedload(Review.semester),
        )
        .order_by(Review.created_at.desc())
        .all()
    )
    descriptions = (
        Review.query
        .filter_by(user_id=current_user.user_id, review_type='description')
        .options(
            joinedload(Review.course).joinedload(Course.department),
        )
        .order_by(Review.created_at.desc())
        .all()
    )
    return render_template('courses/my_reviews.html',
        opinions     = opinions,
        descriptions = descriptions,
    )


@courses.route('/my/uploads')
@login_required
def my_uploads():
    materials = (
        Material.query
        .filter_by(user_id=current_user.user_id, is_removed=False)
        .options(
            joinedload(Material.course).joinedload(Course.department),
            joinedload(Material.semester),
        )
        .order_by(Material.created_at.desc())
        .all()
    )
    return render_template('courses/my_uploads.html', materials=materials)

@courses.route('/my/saved')
@login_required
def my_saved():
    saved_courses = (
        SavedCourse.query
        .filter_by(user_id=current_user.user_id)
        .options(
            joinedload(SavedCourse.course).joinedload(Course.department),
        )
        .order_by(SavedCourse.created_at.desc())
        .all()
    )

    saved_materials = (
        SavedMaterial.query
        .filter_by(user_id=current_user.user_id)
        .options(
            joinedload(SavedMaterial.material).joinedload(Material.course).joinedload(Course.department),
            joinedload(SavedMaterial.material).joinedload(Material.semester),
            joinedload(SavedMaterial.material).joinedload(Material.user),
        )
        .order_by(SavedMaterial.created_at.desc())
        .all()
    )

    # ── Single GROUP BY query replaces the per-course loop ────────────────────
    course_ids = [sc.course_id for sc in saved_courses]
    course_ratings = {}
    if course_ids:
        rating_rows = (
            db.session.query(
                Review.course_id,
                func.avg(Review.rating_overall).label('avg'),
                func.count(Review.review_id).label('count'),
            )
            .filter(
                Review.course_id.in_(course_ids),
                Review.review_type == 'opinion',
            )
            .group_by(Review.course_id)
            .all()
        )
        course_ratings = {
            row.course_id: {
                'avg':   round(float(row.avg), 1),
                'count': row.count,
            }
            for row in rating_rows
        }

    all_saved = sorted(
        [('course', sc) for sc in saved_courses] +
        [('material', sm) for sm in saved_materials],
        key=lambda x: x[1].created_at,
        reverse=True,
    )

    return render_template('courses/my_saved.html',
        all_saved       = all_saved,
        course_ratings  = course_ratings,
        total_courses   = len(saved_courses),
        total_materials = len(saved_materials),
    )


@courses.route('/course/<int:course_id>/save', methods=['POST'])
@login_required
def save_course(course_id):
    Course.query.get_or_404(course_id)
    note     = ((request.json or {}).get('note') or '').strip() or None
    existing = SavedCourse.query.filter_by(
        user_id=current_user.user_id, course_id=course_id
    ).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'action': 'unsaved'})
    db.session.add(SavedCourse(
        user_id   = current_user.user_id,
        course_id = course_id,
        note      = note,
    ))
    db.session.commit()
    return jsonify({'action': 'saved'})


@courses.route('/material/<int:material_id>/save', methods=['POST'])
@login_required
def save_material(material_id):
    Material.query.get_or_404(material_id)
    note     = ((request.json or {}).get('note') or '').strip() or None
    existing = SavedMaterial.query.filter_by(
        user_id=current_user.user_id, material_id=material_id
    ).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'action': 'unsaved'})
    db.session.add(SavedMaterial(
        user_id     = current_user.user_id,
        material_id = material_id,
        note        = note,
    ))
    db.session.commit()
    return jsonify({'action': 'saved'})

# ─────────────────────────────────────────────
# Update note on a saved course
# ─────────────────────────────────────────────
@courses.route('/saved/course/<int:course_id>/note', methods=['POST'])
@login_required
def update_saved_course_note(course_id):
    saved      = SavedCourse.query.filter_by(
        user_id=current_user.user_id, course_id=course_id
    ).first_or_404()
    saved.note = ((request.json or {}).get('note') or '').strip() or None
    db.session.commit()
    return jsonify({'ok': True})


# ─────────────────────────────────────────────
# Update note on a saved material
# ─────────────────────────────────────────────
@courses.route('/saved/material/<int:material_id>/note', methods=['POST'])
@login_required
def update_saved_material_note(material_id):
    saved      = SavedMaterial.query.filter_by(
        user_id=current_user.user_id, material_id=material_id
    ).first_or_404()
    saved.note = ((request.json or {}).get('note') or '').strip() or None
    db.session.commit()
    return jsonify({'ok': True})