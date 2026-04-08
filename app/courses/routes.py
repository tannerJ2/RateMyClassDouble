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
            'avg_rating': round(
                db.session.query(func.avg(Review.rating_overall))
                .filter_by(course_id=c.Course.course_id, review_type='opinion')
                .scalar() or 0, 1
            ),
            'rating_count': Review.query.filter_by(
                course_id=c.Course.course_id, review_type='opinion'
            ).count(),
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
    active_materials  = (
        Material.query
        .filter_by(course_id=course_id, is_removed=False)
        .order_by(Material.created_at.desc())
        .all()
    )
    material_count    = len(active_materials)

    avg_difficulty = (
        db.session.query(func.avg(Review.difficulty_level))
        .filter_by(course_id=course_id, review_type='opinion')
        .scalar()
    )
    avg_workload = (
        db.session.query(func.avg(Review.workload_level))
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
        active_materials  = active_materials,
        avg_difficulty    = avg_difficulty,
        avg_workload      = avg_workload,
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

@courses.route('/course/<int:course_id>/materials')
def all_materials(course_id):
    course = Course.query.get_or_404(course_id)
    sort   = request.args.get('sort', 'recent')

    materials = (
        Material.query
        .filter_by(course_id=course_id, is_removed=False)
        .all()
    )

    if sort == 'recent':
        materials = sorted(materials, key=lambda m: m.created_at, reverse=True)
    elif sort == 'yours' and current_user.is_authenticated:
        mine     = [m for m in materials if m.user_id == current_user.user_id]
        others   = [m for m in materials if m.user_id != current_user.user_id]
        materials = mine + sorted(others, key=lambda m: m.created_at, reverse=True)
    else:
        materials = sorted(materials, key=lambda m: m.created_at, reverse=True)

    return render_template(
        'courses/all_materials.html',
        course    = course,
        materials = materials,
        sort      = sort,
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

    upload_dir = current_app.config['MATERIAL_UPLOAD_FOLDER']
    return send_from_directory(
        upload_dir,
        material.file_url,
        mimetype='application/pdf',
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
            return render_template('courses/submit_opinion.html',
                course            = course,
                semesters         = semesters,
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
        stored_name = uuid.uuid4().hex + '.pdf'

        # SECURITY 6: upload directory lives in instance/ which is outside
        # static/ — the web server (Nginx) must NOT alias this path, so files
        # can only be retrieved through the controlled download route below.
        upload_dir = current_app.config['MATERIAL_UPLOAD_FOLDER']
        os.makedirs(upload_dir, exist_ok=True)
        file.save(os.path.join(upload_dir, stored_name))

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

    # SECURITY 7: soft-deleted files cannot be downloaded by anyone.
    if material.is_removed:
        flash('This material has been removed and is no longer available.', 'danger')
        return redirect(url_for('courses.course_detail', course_id=material.course_id))

    upload_dir  = current_app.config['MATERIAL_UPLOAD_FOLDER']

    # SECURITY 8: construct the download filename from the DB title (not from
    # the stored UUID), sanitized through secure_filename to strip any special
    # characters, then force a .pdf extension.
    safe_title    = secure_filename(material.title) or 'material'
    download_name = safe_title + '.pdf'

    # SECURITY 9: send_from_directory validates that the resolved path stays
    # inside upload_dir (raises 404 if someone injects ../ sequences).
    # Content-Disposition: attachment prevents the browser from rendering the
    # PDF inline as an active document, reducing XSS-via-PDF risk.
    return send_from_directory(
        upload_dir,
        material.file_url,
        as_attachment=True,
        download_name=download_name,
        mimetype='application/pdf',
    )

@courses.route('/my/reviews')
@login_required
def my_reviews():
    opinions = (
        Review.query
        .filter_by(user_id=current_user.user_id, review_type='opinion')
        .order_by(Review.created_at.desc())
        .all()
    )
    descriptions = (
        Review.query
        .filter_by(user_id=current_user.user_id, review_type='description')
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
        .order_by(Material.created_at.desc())
        .all()
    )
    return render_template('courses/my_uploads.html', materials=materials)

@courses.route('/my/saved')
@login_required
def my_saved():
    saved_courses = SavedCourse.query.filter_by(
        user_id=current_user.user_id
    ).order_by(SavedCourse.created_at.desc()).all()

    saved_materials = SavedMaterial.query.filter_by(
        user_id=current_user.user_id
    ).order_by(SavedMaterial.created_at.desc()).all()

    return render_template('courses/my_saved.html',
        saved_courses   = saved_courses,
        saved_materials = saved_materials,
    )


@courses.route('/course/<int:course_id>/save', methods=['POST'])
@login_required
def save_course(course_id):
    Course.query.get_or_404(course_id)
    existing = SavedCourse.query.filter_by(
        user_id=current_user.user_id, course_id=course_id
    ).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'action': 'unsaved'})
    db.session.add(SavedCourse(user_id=current_user.user_id, course_id=course_id))
    db.session.commit()
    return jsonify({'action': 'saved'})


@courses.route('/material/<int:material_id>/save', methods=['POST'])
@login_required
def save_material(material_id):
    Material.query.get_or_404(material_id)
    existing = SavedMaterial.query.filter_by(
        user_id=current_user.user_id, material_id=material_id
    ).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'action': 'unsaved'})
    db.session.add(SavedMaterial(user_id=current_user.user_id, material_id=material_id))
    db.session.commit()
    return jsonify({'action': 'saved'})