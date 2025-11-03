#!/usr/bin/env python3
"""
Historical Figures Administration Interface
A web-based admin panel for managing historical figures and their documents.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, Response, send_from_directory, session
import os
import json
import logging
from werkzeug.utils import secure_filename
from pathlib import Path
import sys
import time
from functools import wraps

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from figure_manager import get_figure_manager
from document_processor import DocumentProcessor
from validators import validate_figure_data, sanitize_figure_id, sanitize_figure_name
from config import ADMIN_PORT, DEBUG_MODE, ALLOWED_EXTENSIONS, ALLOWED_IMAGE_EXTENSIONS, FIGURE_IMAGES_DIR, ADMIN_PASSWORD

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'historical_figures_admin_key_change_in_production')

app.config['APPLICATION_ROOT'] = '/admin'
class PrefixMiddleware:
    def __init__(self, app, prefix=''):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        if environ['PATH_INFO'].startswith(self.prefix):
            environ['PATH_INFO'] = environ['PATH_INFO'][len(self.prefix):]
            environ['SCRIPT_NAME'] = self.prefix
            return self.app(environ, start_response)
        else:
            environ['SCRIPT_NAME'] = self.prefix
            return self.app(environ, start_response)

from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.wsgi_app = PrefixMiddleware(app.wsgi_app, '/admin')

logging.basicConfig(level=logging.INFO)

from config import TEMP_UPLOAD_DIR, MAX_CONTENT_LENGTH
app.config['UPLOAD_FOLDER'] = TEMP_UPLOAD_DIR
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['MAX_FORM_MEMORY_SIZE'] = None

os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)
os.makedirs(FIGURE_IMAGES_DIR, exist_ok=True)

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_image_file(filename):
    """Check if image file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def login_required(f):
    """Decorator to require login for admin routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access the admin panel.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page for admin panel."""
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session.permanent = True
            flash('Successfully logged in!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid password. Please try again.', 'error')
    return render_template('admin/login.html')

@app.route('/logout')
def logout():
    """Logout from admin panel."""
    session.pop('logged_in', None)
    flash('Successfully logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """Main dashboard showing all figures."""
    try:
        figure_manager = get_figure_manager()
        figures = figure_manager.get_figure_list()
        return render_template('admin/dashboard.html', figures=figures)
    except Exception as e:
        flash(f'Error loading figures: {str(e)}', 'error')
        return render_template('admin/dashboard.html', figures=[])

@app.route('/figure/new')
@login_required
def new_figure():
    """Form to create a new figure."""
    return render_template('admin/new_figure.html')

@app.route('/figure/create', methods=['POST'])
@login_required
def create_figure():
    """Create a new historical figure."""
    try:
        # Collect form data
        form_data = {
            'figure_id': request.form.get('figure_id', '').strip(),
            'name': request.form.get('name', '').strip(),
            'description': request.form.get('description', '').strip(),
            'personality_prompt': request.form.get('personality_prompt', '').strip(),
            'birth_year': request.form.get('birth_year', '').strip(),
            'death_year': request.form.get('death_year', '').strip(),
            'nationality': request.form.get('nationality', '').strip(),
            'occupation': request.form.get('occupation', '').strip(),
            'max_length': request.form.get('max_length', '250').strip(),
            'max_chunk_chars': request.form.get('max_chunk_chars', '1000').strip()
        }
        
        # Validate all input
        validation_errors = validate_figure_data(form_data, is_update=False)
        if validation_errors:
            for field, error in validation_errors.items():
                flash(f'{field.replace("_", " ").title()}: {error}', 'error')
            return redirect(url_for('new_figure'))
        
        # Sanitize figure_id and name
        figure_id = sanitize_figure_id(form_data['figure_id'])
        name = sanitize_figure_name(form_data['name'])
        description = form_data['description'][:400]  # Enforce max length
        personality_prompt = form_data['personality_prompt'][:400]  # Enforce max length
        
        # Parse metadata with validated years
        metadata = {}
        if form_data['birth_year']:
            metadata['birth_year'] = int(form_data['birth_year'])
        if form_data['death_year']:
            metadata['death_year'] = int(form_data['death_year'])
        if form_data['nationality']:
            metadata['nationality'] = form_data['nationality'][:100]  # Limit length
        if form_data['occupation']:
            metadata['occupation'] = form_data['occupation'][:200]  # Limit length
        
        # Parse and validate max_length (words, legacy/semantic parameter)
        try:
            max_length = int(form_data['max_length'])
            max_length = max(50, min(1000, max_length))  # Clamp between 50 and 1000 words
        except (ValueError, TypeError):
            max_length = 250  # Default value (words)
        
        # Parse and validate max_chunk_chars (characters, primary chunking parameter)
        try:
            max_chunk_chars = int(form_data['max_chunk_chars'])
            max_chunk_chars = max(500, min(3000, max_chunk_chars))  # Clamp between 500 and 3000 chars
        except (ValueError, TypeError):
            max_chunk_chars = 1000  # Default value (characters)
        
        # Handle image upload
        image_filename = None
        if 'image' in request.files:
            image_file = request.files['image']
            if image_file and image_file.filename != '' and allowed_image_file(image_file.filename):
                try:
                    # Create secure filename
                    file_extension = Path(image_file.filename).suffix.lower()
                    image_filename = f"{figure_id}{file_extension}"
                    image_path = os.path.join(FIGURE_IMAGES_DIR, image_filename)
                    
                    # Save the image
                    image_file.save(image_path)
                    logging.info(f"Saved image for figure {figure_id}: {image_path}")
                except Exception as e:
                    logging.error(f"Error saving image for figure {figure_id}: {str(e)}")
                    flash(f'Warning: Image could not be saved: {str(e)}', 'warning')
        
        # Add image filename to metadata if available
        if image_filename:
            metadata['image'] = image_filename
        
        # Create figure
        figure_manager = get_figure_manager()
        success = figure_manager.create_figure(
            figure_id=figure_id,
            name=name,
            description=description,
            personality_prompt=personality_prompt,
            metadata=metadata,
            max_length=max_length,
            max_chunk_chars=max_chunk_chars
        )
        
        if success:
            flash(f'Successfully created figure: {name}', 'success')
            return redirect(url_for('figure_detail', figure_id=figure_id))
        else:
            flash(f'Failed to create figure: {figure_id}', 'error')
            return redirect(url_for('new_figure'))
    
    except Exception as e:
        flash(f'Error creating figure: {str(e)}', 'error')
        return redirect(url_for('new_figure'))

@app.route('/figure/<figure_id>')
@login_required
def figure_detail(figure_id):
    """Show detailed information about a figure."""
    try:
        figure_manager = get_figure_manager()
        metadata = figure_manager.get_figure_metadata(figure_id)
        if not metadata:
            flash(f'Figure {figure_id} not found', 'error')
            return redirect(url_for('index'))
        
        stats = figure_manager.get_figure_stats(figure_id)
        return render_template('admin/figure_detail.html', 
                             figure=metadata, 
                             stats=stats)
    except Exception as e:
        flash(f'Error loading figure: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/figure/<figure_id>/edit')
@login_required
def edit_figure(figure_id):
    """Form to edit a figure."""
    try:
        figure_manager = get_figure_manager()
        metadata = figure_manager.get_figure_metadata(figure_id)
        if not metadata:
            flash(f'Figure {figure_id} not found', 'error')
            return redirect(url_for('index'))
        
        return render_template('admin/edit_figure.html', figure=metadata)
    except Exception as e:
        flash(f'Error loading figure: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/figure/<figure_id>/update', methods=['POST'])
@login_required
def update_figure(figure_id):
    """Update a figure's metadata."""
    try:
        figure_manager = get_figure_manager()
        
        # Get current metadata
        current_metadata = figure_manager.get_figure_metadata(figure_id)
        if not current_metadata:
            flash(f'Figure {figure_id} not found', 'error')
            return redirect(url_for('index'))
        
        # Collect form data
        form_data = {
            'name': request.form.get('name', '').strip(),
            'description': request.form.get('description', '').strip(),
            'personality_prompt': request.form.get('personality_prompt', '').strip(),
            'birth_year': request.form.get('birth_year', '').strip(),
            'death_year': request.form.get('death_year', '').strip(),
            'nationality': request.form.get('nationality', '').strip(),
            'occupation': request.form.get('occupation', '').strip()
        }
        
        # Validate input (is_update=True makes figure_id optional)
        validation_errors = validate_figure_data(form_data, is_update=True)
        if validation_errors:
            for field, error in validation_errors.items():
                flash(f'{field.replace("_", " ").title()}: {error}', 'error')
            return redirect(url_for('edit_figure', figure_id=figure_id))
        
        # Prepare updates with sanitized and length-limited values
        updates = {}
        
        name = sanitize_figure_name(form_data['name']) if form_data['name'] else current_metadata.get('name')
        description = form_data['description'][:400]  # Enforce max length
        personality_prompt = form_data['personality_prompt'][:400]  # Enforce max length
        
        if name and name != current_metadata.get('name'):
            updates['name'] = name
        if description != current_metadata.get('description', ''):
            updates['description'] = description
        if personality_prompt != current_metadata.get('personality_prompt', ''):
            updates['personality_prompt'] = personality_prompt
        
        # Handle metadata updates with validated data
        metadata = current_metadata.get('metadata', {})
        
        if form_data['birth_year']:
            metadata['birth_year'] = int(form_data['birth_year'])
        elif 'birth_year' in metadata:
            del metadata['birth_year']
        
        if form_data['death_year']:
            metadata['death_year'] = int(form_data['death_year'])
        elif 'death_year' in metadata:
            del metadata['death_year']
        
        if form_data['nationality']:
            metadata['nationality'] = form_data['nationality'][:100]  # Limit length
        elif 'nationality' in metadata:
            del metadata['nationality']
        
        if form_data['occupation']:
            metadata['occupation'] = form_data['occupation'][:200]  # Limit length
        elif 'occupation' in metadata:
            del metadata['occupation']
        
        # Handle image upload
        if 'image' in request.files:
            image_file = request.files['image']
            if image_file and image_file.filename != '' and allowed_image_file(image_file.filename):
                try:
                    # Remove old image if it exists
                    old_image = metadata.get('image')
                    if old_image:
                        old_image_path = os.path.join(FIGURE_IMAGES_DIR, old_image)
                        if os.path.exists(old_image_path):
                            os.remove(old_image_path)
                            logging.info(f"Removed old image: {old_image_path}")
                    
                    # Save new image
                    file_extension = Path(image_file.filename).suffix.lower()
                    image_filename = f"{figure_id}{file_extension}"
                    image_path = os.path.join(FIGURE_IMAGES_DIR, image_filename)
                    image_file.save(image_path)
                    
                    # Update metadata
                    metadata['image'] = image_filename
                    logging.info(f"Updated image for figure {figure_id}: {image_path}")
                except Exception as e:
                    logging.error(f"Error updating image for figure {figure_id}: {str(e)}")
                    flash(f'Warning: Image could not be updated: {str(e)}', 'warning')
        
        updates['metadata'] = metadata
        
        # Apply updates
        success = figure_manager.update_figure_metadata(figure_id, updates)
        
        if success:
            flash(f'Successfully updated figure: {name or figure_id}', 'success')
        else:
            flash(f'Failed to update figure: {figure_id}', 'error')
        
        return redirect(url_for('figure_detail', figure_id=figure_id))
    
    except Exception as e:
        flash(f'Error updating figure: {str(e)}', 'error')
        return redirect(url_for('figure_detail', figure_id=figure_id))

@app.route('/figure/<figure_id>/upload')
@login_required
def upload_documents_form(figure_id):
    """Form to upload documents to a figure."""
    try:
        figure_manager = get_figure_manager()
        metadata = figure_manager.get_figure_metadata(figure_id)
        if not metadata:
            flash(f'Figure {figure_id} not found', 'error')
            return redirect(url_for('index'))
        
        return render_template('admin/upload_documents.html', figure=metadata)
    except Exception as e:
        flash(f'Error loading figure: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/figure/<figure_id>/upload', methods=['POST'])
@login_required
def upload_documents(figure_id):
    """Upload documents to a figure - supports both AJAX and traditional form submission."""
    try:
        figure_manager = get_figure_manager()
        
        # Debug logging for upload issues
        logging.info(f"Upload request received for figure {figure_id}")
        logging.info(f"Request method: {request.method}")
        logging.info(f"Content-Type: {request.content_type}")
        logging.info(f"Files in request: {list(request.files.keys())}")
        logging.info(f"Form data: {list(request.form.keys())}")
        
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Check if figure exists and get metadata
        figure_metadata = figure_manager.get_figure_metadata(figure_id)
        if not figure_metadata:
            if is_ajax:
                return jsonify({'error': f'Figure {figure_id} not found'}), 404
            flash(f'Figure {figure_id} not found', 'error')
            return redirect(url_for('index'))
        
        # Get chunking parameters from figure metadata
        max_length = figure_metadata.get('max_length', 250)  # Words (legacy/semantic)
        max_chunk_chars = figure_metadata.get('max_chunk_chars', 1000)  # Characters (primary)
        
        # Create document processor using figure-specific chunk size (both char and word-based)
        document_processor = DocumentProcessor(
            chunk_size=max_length,
            max_chunk_chars=max_chunk_chars
        )
        
        # Check if files were uploaded
        if 'files' not in request.files:
            if is_ajax:
                return jsonify({'error': 'No files selected'}), 400
            flash('No files selected', 'error')
            return redirect(url_for('upload_documents_form', figure_id=figure_id))
        
        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            if is_ajax:
                return jsonify({'error': 'No files selected'}), 400
            flash('No files selected', 'error')
            return redirect(url_for('upload_documents_form', figure_id=figure_id))
        
        successful_uploads = 0
        total_files = len([f for f in files if f.filename != ''])
        all_results = []
        
        for file_index, file in enumerate(files):
            if file.filename == '':
                continue
            
            file_result = {
                'filename': file.filename,
                'status': 'processing',
                'chunks': [],
                'total_chunks': 0,
                'error': None
            }
            
            if file and allowed_file(file.filename):
                try:
                    # Read file content
                    file_content = file.read()
                    original_filename = file.filename
                    
                    # Handle Unicode filenames: secure_filename strips non-ASCII chars
                    # Generate safe filename while preserving original in metadata
                    safe_filename = secure_filename(original_filename)
                    if not safe_filename or safe_filename.startswith('.'):
                        # If secure_filename results in empty or just extension, use timestamp
                        import time
                        file_ext = Path(original_filename).suffix.lower()
                        safe_filename = f"upload_{int(time.time() * 1000)}{file_ext}"
                    
                    filename = safe_filename
                    
                    # Determine file type
                    file_extension = Path(original_filename).suffix.lower()
                    if file_extension == '.pdf':
                        file_type = 'pdf'
                    elif file_extension in ['.txt', '.text']:
                        file_type = 'txt'
                    else:
                        file_result['status'] = 'error'
                        file_result['error'] = f'Unsupported file type'
                        all_results.append(file_result)
                        continue
                    
                    # Process the file into chunks (use safe filename for internal processing)
                    chunks = document_processor.process_file(file_content, filename, file_type)
                    file_result['total_chunks'] = len(chunks)
                    
                    # Add each chunk to the figure's collection
                    chunk_count = 0
                    for chunk_index, chunk in enumerate(chunks):
                        # Update metadata to use original filename
                        chunk_metadata = chunk['metadata'].copy()
                        chunk_metadata['original_filename'] = original_filename
                        
                        doc_id = figure_manager.add_document_to_figure(
                            figure_id=figure_id,
                            text=chunk['text'],
                            metadata=chunk_metadata
                        )
                        if doc_id:
                            chunk_count += 1
                            file_result['chunks'].append({
                                'index': chunk_index,
                                'success': True
                            })
                        # Log progress for debugging
                        if (chunk_index + 1) % 5 == 0 or chunk_index == len(chunks) - 1:
                            logging.info(f"Processed {chunk_index + 1}/{len(chunks)} chunks for {filename}")
                    
                    if chunk_count > 0:
                        file_result['status'] = 'success'
                        file_result['message'] = f'{chunk_count} chunks added'
                        successful_uploads += 1
                        if not is_ajax:
                            flash(f'Successfully uploaded {filename}: {chunk_count} chunks added', 'success')
                    else:
                        file_result['status'] = 'error'
                        file_result['error'] = 'Failed to process file'
                        if not is_ajax:
                            flash(f'Failed to process {filename}', 'error')
                
                except Exception as e:
                    file_result['status'] = 'error'
                    file_result['error'] = str(e)
                    if not is_ajax:
                        flash(f'Error processing {file.filename}: {str(e)}', 'error')
            else:
                file_result['status'] = 'error'
                file_result['error'] = 'File type not allowed'
                if not is_ajax:
                    flash(f'File type not allowed: {file.filename}', 'error')
            
            all_results.append(file_result)
        
        if is_ajax:
            return jsonify({
                'success': successful_uploads > 0,
                'successful_uploads': successful_uploads,
                'total_files': total_files,
                'results': all_results
            })
        
        if successful_uploads > 0:
            flash(f'Upload complete: {successful_uploads}/{total_files} files processed successfully', 'info')
        
        return redirect(url_for('figure_detail', figure_id=figure_id))
    
    except Exception as e:
        logging.error(f"Upload error: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': str(e)}), 500
        flash(f'Error uploading documents: {str(e)}', 'error')
        return redirect(url_for('upload_documents_form', figure_id=figure_id))

@app.route('/figure/<figure_id>/upload-stream', methods=['POST'])
@login_required
def upload_documents_stream(figure_id):
    """Upload documents with streaming progress updates."""
    
    # Read all files and their content BEFORE entering the generator
    # This is crucial because the request context ends when we start streaming
    files_data = []
    try:
        files = request.files.getlist('files')
        for file in files:
            if file.filename:
                # Handle Unicode filenames: secure_filename strips non-ASCII chars
                safe_filename = secure_filename(file.filename)
                if not safe_filename or safe_filename.startswith('.'):
                    # If secure_filename results in empty or just extension, use timestamp
                    import time
                    file_ext = Path(file.filename).suffix.lower()
                    safe_filename = f"upload_{int(time.time() * 1000)}{file_ext}"
                
                files_data.append({
                    'filename': safe_filename,
                    'content': file.read(),  # Read the content now while in request context
                    'original_filename': file.filename
                })
    except Exception as e:
        return Response(
            f"data: {json.dumps({'error': f'Failed to read files: {str(e)}'})}\n\n",
            mimetype='text/event-stream'
        )
    
    def generate():
        try:
            figure_manager = get_figure_manager()
            
            # Check if figure exists and get metadata
            figure_metadata = figure_manager.get_figure_metadata(figure_id)
            if not figure_metadata:
                yield f"data: {json.dumps({'error': 'Figure not found'})}\n\n"
                return
            
            # Get chunking parameters from figure metadata
            max_length = figure_metadata.get('max_length', 250)  # Words (legacy/semantic)
            max_chunk_chars = figure_metadata.get('max_chunk_chars', 1000)  # Characters (primary)
            
            # Create document processor using figure-specific chunk size (both char and word-based)
            document_processor = DocumentProcessor(
                chunk_size=max_length,
                max_chunk_chars=max_chunk_chars
            )
            
            # Check if files were provided
            if not files_data:
                yield f"data: {json.dumps({'error': 'No files selected'})}\n\n"
                return
            
            total_files = len(files_data)
            successful_uploads = 0
            
            for file_index, file_data in enumerate(files_data):
                filename = file_data['filename']
                original_filename = file_data['original_filename']
                file_content = file_data['content']
                
                # Send file start event
                yield f"data: {json.dumps({'event': 'file_start', 'file_index': file_index, 'filename': filename})}\n\n"
                
                if not allowed_file(original_filename):
                    yield f"data: {json.dumps({'event': 'file_error', 'file_index': file_index, 'error': 'File type not allowed'})}\n\n"
                    continue
                
                try:
                    # Determine file type from original filename
                    file_extension = Path(original_filename).suffix.lower()
                    if file_extension == '.pdf':
                        file_type = 'pdf'
                    elif file_extension in ['.txt', '.text']:
                        file_type = 'txt'
                    else:
                        yield f"data: {json.dumps({'event': 'file_error', 'file_index': file_index, 'error': 'Unsupported file type'})}\n\n"
                        continue
                    
                    # Process the file into chunks (use safe filename for internal processing)
                    chunks = document_processor.process_file(file_content, filename, file_type)
                    total_chunks = len(chunks)
                    
                    # Send chunks count
                    yield f"data: {json.dumps({'event': 'chunks_count', 'file_index': file_index, 'total_chunks': total_chunks})}\n\n"
                    
                    # Add each chunk to the figure's collection
                    chunk_count = 0
                    for chunk_index, chunk in enumerate(chunks):
                        # Update metadata to use original filename
                        chunk_metadata = chunk['metadata'].copy()
                        chunk_metadata['original_filename'] = original_filename
                        
                        doc_id = figure_manager.add_document_to_figure(
                            figure_id=figure_id,
                            text=chunk['text'],
                            metadata=chunk_metadata
                        )
                        if doc_id:
                            chunk_count += 1
                        
                        # Send progress update every 5 chunks or on the last chunk
                        if (chunk_index + 1) % 5 == 0 or chunk_index == len(chunks) - 1:
                            progress = ((chunk_index + 1) / total_chunks) * 100
                            yield f"data: {json.dumps({'event': 'chunk_progress', 'file_index': file_index, 'chunks_processed': chunk_index + 1, 'total_chunks': total_chunks, 'progress': progress})}\n\n"
                    
                    if chunk_count > 0:
                        successful_uploads += 1
                        yield f"data: {json.dumps({'event': 'file_complete', 'file_index': file_index, 'chunks_added': chunk_count, 'success': True})}\n\n"
                    else:
                        yield f"data: {json.dumps({'event': 'file_error', 'file_index': file_index, 'error': 'Failed to process file'})}\n\n"
                
                except Exception as e:
                    yield f"data: {json.dumps({'event': 'file_error', 'file_index': file_index, 'error': str(e)})}\n\n"
            
            # Send final summary
            yield f"data: {json.dumps({'event': 'upload_complete', 'successful_uploads': successful_uploads, 'total_files': total_files})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/figure/<figure_id>/clean', methods=['POST'])
@login_required
def clean_figure_documents(figure_id):
    """Remove all documents from a figure without deleting the figure itself."""
    try:
        figure_manager = get_figure_manager()
        metadata = figure_manager.get_figure_metadata(figure_id)
        
        if not metadata:
            flash(f'Figure {figure_id} not found', 'error')
            return redirect(url_for('index'))
        
        success = figure_manager.clear_figure_documents(figure_id)
        
        if success:
            flash(f'Successfully removed all documents from {metadata.get("name", figure_id)}', 'success')
        else:
            flash(f'Failed to clean documents for figure: {figure_id}', 'error')
        
        return redirect(url_for('figure_detail', figure_id=figure_id))
    
    except Exception as e:
        flash(f'Error cleaning documents: {str(e)}', 'error')
        return redirect(url_for('figure_detail', figure_id=figure_id))

@app.route('/figure/<figure_id>/delete', methods=['POST'])
@login_required
def delete_figure(figure_id):
    """Delete a figure and all its data."""
    try:
        figure_manager = get_figure_manager()
        metadata = figure_manager.get_figure_metadata(figure_id)
        
        if not metadata:
            flash(f'Figure {figure_id} not found', 'error')
            return redirect(url_for('index'))
        
        success = figure_manager.delete_figure(figure_id)
        
        if success:
            flash(f'Successfully deleted figure: {metadata.get("name", figure_id)}', 'success')
        else:
            flash(f'Failed to delete figure: {figure_id}', 'error')
        
        return redirect(url_for('index'))
    
    except Exception as e:
        flash(f'Error deleting figure: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/api/figures')
def api_figures():
    """API endpoint to get all figures."""
    try:
        figure_manager = get_figure_manager()
        figures = figure_manager.get_figure_list()
        return jsonify(figures)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/figure/<figure_id>/stats')
def api_figure_stats(figure_id):
    """API endpoint to get figure statistics."""
    try:
        figure_manager = get_figure_manager()
        stats = figure_manager.get_figure_stats(figure_id)
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/figure_images/<filename>')
def serve_figure_image(filename):
    """Serve figure images."""
    try:
        return send_from_directory(FIGURE_IMAGES_DIR, filename)
    except Exception as e:
        logging.error(f"Error serving figure image {filename}: {str(e)}")
        return jsonify({'error': 'Image not found'}), 404

if __name__ == '__main__':
    app.run(debug=DEBUG_MODE, host='0.0.0.0', port=ADMIN_PORT)
