'''
Storage helper — switches between local filesystem (dev) and
Google Cloud Storage (production) based on USE_GCS config flag.
'''

import os
import uuid
from flask import current_app


def _get_gcs_client():
    from google.cloud import storage
    return storage.Client()


def upload_file(file_object, original_filename: str) -> str:
    '''
    Save a file and return the stored filename/path.
    - Local: saves to MATERIAL_UPLOAD_FOLDER, returns UUID filename
    - GCS:   uploads to bucket, returns UUID filename (used as GCS blob name)
    '''
    ext         = os.path.splitext(original_filename)[1].lower() or '.pdf'
    stored_name = uuid.uuid4().hex + ext

    if current_app.config.get('USE_GCS'):
        client = _get_gcs_client()
        bucket = client.bucket(current_app.config['GCS_BUCKET_NAME'])
        blob   = bucket.blob(stored_name)
        file_object.seek(0)
        blob.upload_from_file(file_object, content_type='application/pdf')
    else:
        upload_dir = current_app.config['MATERIAL_UPLOAD_FOLDER']
        os.makedirs(upload_dir, exist_ok=True)
        file_object.seek(0)
        file_object.save(os.path.join(upload_dir, stored_name))

    return stored_name


def get_file_response(stored_name: str, download_name: str = None, inline: bool = False):
    '''
    Return a Flask response that serves the file.
    - Local: uses send_from_directory
    - GCS:   redirects to a signed URL (valid 15 minutes)
    '''
    if current_app.config.get('USE_GCS'):
        import datetime
        from flask import redirect
        client = _get_gcs_client()
        bucket = client.bucket(current_app.config['GCS_BUCKET_NAME'])
        blob   = bucket.blob(stored_name)

        disposition = 'inline' if inline else f'attachment; filename="{download_name or stored_name}"'
        url = blob.generate_signed_url(
            version            = 'v4',
            expiration         = datetime.timedelta(minutes=15),
            method             = 'GET',
            response_disposition = disposition,
            response_type      = 'application/pdf',
        )
        return redirect(url)
    else:
        from flask import send_from_directory
        upload_dir = current_app.config['MATERIAL_UPLOAD_FOLDER']
        return send_from_directory(
            upload_dir,
            stored_name,
            as_attachment = not inline,
            download_name = download_name,
            mimetype      = 'application/pdf',
        )


def delete_file(stored_name: str):
    '''
    Delete a file from storage. Called if a DB save fails after upload.
    '''
    if current_app.config.get('USE_GCS'):
        try:
            client = _get_gcs_client()
            bucket = client.bucket(current_app.config['GCS_BUCKET_NAME'])
            blob   = bucket.blob(stored_name)
            blob.delete()
        except Exception:
            pass
    else:
        upload_dir = current_app.config['MATERIAL_UPLOAD_FOLDER']
        path = os.path.join(upload_dir, stored_name)
        if os.path.exists(path):
            os.remove(path)