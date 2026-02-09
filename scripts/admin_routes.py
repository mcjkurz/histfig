"""
Admin Routes - FastAPI Router
Handles admin interface for managing historical figures and their documents.
"""

import os
import json
import logging
import secrets

logger = logging.getLogger('histfig')
import asyncio
import unicodedata
from typing import Optional, List
from pathlib import Path
import time
import re
import glob
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from figure_manager import get_figure_manager
from document_processor import DocumentProcessor
from validators import validate_figure_data, sanitize_figure_id, sanitize_figure_name
from config import ALLOWED_EXTENSIONS, ALLOWED_IMAGE_EXTENSIONS, FIGURE_IMAGES_DIR, ADMIN_PASSWORD, TEMP_UPLOAD_DIR, OVERLAP_PERCENT


def secure_filename(filename: str) -> str:
    """
    Sanitize a filename to be safe for filesystem use.
    Replaces werkzeug.utils.secure_filename for FastAPI compatibility.
    """
    # Normalize unicode characters
    filename = unicodedata.normalize('NFKD', filename)
    
    # Replace path separators with underscores
    for sep in (os.sep, os.altsep):
        if sep:
            filename = filename.replace(sep, '_')
    
    # Keep only safe characters: alphanumeric, dash, underscore, dot, and CJK characters
    # This regex keeps ASCII alphanumeric, common CJK ranges, and safe punctuation
    filename = re.sub(r'[^\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff.\-]', '_', filename, flags=re.UNICODE)
    
    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')
    
    # Collapse multiple underscores
    filename = re.sub(r'_+', '_', filename)
    
    # Ensure filename is not empty
    if not filename:
        filename = 'unnamed'
    
    return filename


# Create router with /admin prefix (added in main.py)
admin_router = APIRouter(tags=["admin"])

# Ensure directories exist
os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)
os.makedirs(FIGURE_IMAGES_DIR, exist_ok=True)


# Helper functions
def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_image_file(filename: str) -> bool:
    """Check if image file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def generate_csrf_token(request: Request) -> str:
    """Generate a CSRF token and store it in session."""
    session = request.session
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']


def validate_csrf_token(request: Request, token: str) -> bool:
    """Validate CSRF token from request."""
    session = request.session
    return token and token == session.get('csrf_token')


async def get_csrf_token_from_request(request: Request) -> str:
    """Extract CSRF token from form data or headers."""
    # Try to get from headers first (for AJAX requests)
    token = request.headers.get('X-CSRF-Token')
    if token:
        return token
    
    # Try to get from form data
    try:
        form_data = await request.form()
        token = form_data.get('csrf_token', '')
    except Exception:
        token = ''
    
    return token


async def require_csrf(request: Request):
    """Validate CSRF token for the request. Raises HTTPException if invalid."""
    token = await get_csrf_token_from_request(request)
    if not validate_csrf_token(request, token):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")


async def check_login(request: Request) -> bool:
    """Check if user is logged in."""
    return request.session.get('admin_logged_in', False)


async def require_login(request: Request):
    """Dependency that requires login for admin routes."""
    if not await check_login(request):
        raise HTTPException(status_code=401, detail="Login required")


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# Routes

@admin_router.get("/login", response_class=HTMLResponse, name="admin.login")
async def login_page(request: Request):
    """Login page for admin panel."""
    templates = request.app.state.templates
    return templates.TemplateResponse("admin/login.html", {"request": request})


@admin_router.post("/login", name="admin.login_post")
async def login(request: Request):
    """Handle login form submission."""
    form_data = await request.form()
    password = form_data.get('password', '')
    
    if password == ADMIN_PASSWORD:
        request.session['admin_logged_in'] = True
        return RedirectResponse(url="/admin/", status_code=303)
    else:
        templates = request.app.state.templates
        return templates.TemplateResponse(
            "admin/login.html", 
            {"request": request, "error": "Invalid password. Please try again."}
        )


@admin_router.get("/logout", name="admin.logout")
async def logout(request: Request):
    """Logout from admin panel."""
    request.session.pop('admin_logged_in', None)
    return RedirectResponse(url="/admin/login", status_code=303)


@admin_router.get("/", response_class=HTMLResponse, name="admin.index")
async def index(request: Request):
    """Main dashboard showing all figures."""
    if not await check_login(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    try:
        figure_manager = get_figure_manager()
        figures = await figure_manager.get_figure_list_async()
        templates = request.app.state.templates
        return templates.TemplateResponse("admin/dashboard.html", {"request": request, "figures": figures})
    except Exception as e:
        templates = request.app.state.templates
        return templates.TemplateResponse(
            "admin/dashboard.html", 
            {"request": request, "figures": [], "error": f"Error loading figures: {str(e)}"}
        )


@admin_router.get("/figure/new", response_class=HTMLResponse, name="admin.new_figure")
async def new_figure(request: Request):
    """Form to create a new figure."""
    if not await check_login(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    templates = request.app.state.templates
    return templates.TemplateResponse("admin/new_figure.html", {"request": request})


@admin_router.post("/figure/create", name="admin.create_figure")
async def create_figure(
    request: Request,
    figure_id: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    personality_prompt: str = Form(""),
    birth_year: str = Form(""),
    death_year: str = Form(""),
    image: Optional[UploadFile] = File(None)
):
    """Create a new historical figure."""
    if not await check_login(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    # Validate CSRF token
    await require_csrf(request)
    
    try:
        form_data = {
            'figure_id': figure_id.strip(),
            'name': name.strip(),
            'description': description.strip(),
            'personality_prompt': personality_prompt.strip(),
            'birth_year': birth_year.strip(),
            'death_year': death_year.strip()
        }
        
        validation_errors = validate_figure_data(form_data, is_update=False)
        if validation_errors:
            templates = request.app.state.templates
            return templates.TemplateResponse(
                "admin/new_figure.html",
                {"request": request, "error": "; ".join(validation_errors.values())}
            )
        
        figure_id_clean = sanitize_figure_id(form_data['figure_id'])
        name_clean = sanitize_figure_name(form_data['name'])
        description_clean = form_data['description'][:400]
        personality_clean = form_data['personality_prompt'][:400]
        
        metadata = {}
        if form_data['birth_year']:
            metadata['birth_year'] = int(form_data['birth_year'])
        if form_data['death_year']:
            metadata['death_year'] = int(form_data['death_year'])
        
        image_filename = None
        if image and image.filename and allowed_image_file(image.filename):
            try:
                file_extension = Path(image.filename).suffix.lower()
                image_filename = f"{figure_id_clean}{file_extension}"
                image_path = os.path.join(FIGURE_IMAGES_DIR, image_filename)
                content = await image.read()
                with open(image_path, 'wb') as f:
                    f.write(content)
                logger.info(f"Saved image for figure {figure_id_clean}: {image_path}")
            except Exception as e:
                logger.error(f"Error saving image: {str(e)}")
        
        if image_filename:
            metadata['image'] = image_filename
        
        figure_manager = get_figure_manager()
        success = await figure_manager.create_figure_async(
            figure_id=figure_id_clean,
            name=name_clean,
            description=description_clean,
            personality_prompt=personality_clean,
            metadata=metadata
        )
        
        if success:
            return RedirectResponse(url=f"/admin/figure/{figure_id_clean}", status_code=303)
        else:
            templates = request.app.state.templates
            return templates.TemplateResponse(
                "admin/new_figure.html",
                {"request": request, "error": f"Failed to create figure: {figure_id_clean}"}
            )
    
    except Exception as e:
        templates = request.app.state.templates
        return templates.TemplateResponse(
            "admin/new_figure.html",
            {"request": request, "error": f"Error creating figure: {str(e)}"}
        )


@admin_router.get("/figure/{figure_id}", response_class=HTMLResponse, name="admin.figure_detail")
async def figure_detail(request: Request, figure_id: str):
    """Show detailed information about a figure."""
    if not await check_login(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    try:
        figure_manager = get_figure_manager()
        metadata = await figure_manager.get_figure_metadata_async(figure_id)
        if not metadata:
            return RedirectResponse(url="/admin/", status_code=303)
        
        stats = await figure_manager.get_figure_stats_async(figure_id)
        csrf_token = generate_csrf_token(request)
        templates = request.app.state.templates
        return templates.TemplateResponse(
            "admin/figure_detail.html",
            {"request": request, "figure": metadata, "stats": stats, "csrf_token": csrf_token}
        )
    except Exception as e:
        logger.error(f"Error loading figure detail {figure_id}: {e}")
        return RedirectResponse(url="/admin/", status_code=303)


@admin_router.get("/figure/{figure_id}/edit", response_class=HTMLResponse, name="admin.edit_figure")
async def edit_figure(request: Request, figure_id: str):
    """Form to edit a figure."""
    if not await check_login(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    try:
        figure_manager = get_figure_manager()
        metadata = await figure_manager.get_figure_metadata_async(figure_id)
        if not metadata:
            return RedirectResponse(url="/admin/", status_code=303)
        
        stats = await figure_manager.get_figure_stats_async(figure_id)
        csrf_token = generate_csrf_token(request)
        templates = request.app.state.templates
        return templates.TemplateResponse(
            "admin/edit_figure.html",
            {"request": request, "figure": metadata, "stats": stats, "csrf_token": csrf_token}
        )
    except Exception as e:
        logger.error(f"Error loading edit form for figure {figure_id}: {e}")
        return RedirectResponse(url="/admin/", status_code=303)


@admin_router.post("/figure/{figure_id}/update", name="admin.update_figure")
async def update_figure(
    request: Request,
    figure_id: str,
    name: str = Form(""),
    description: str = Form(""),
    personality_prompt: str = Form(""),
    birth_year: str = Form(""),
    death_year: str = Form(""),
    image: Optional[UploadFile] = File(None)
):
    """Update a figure's metadata."""
    if not await check_login(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    # Validate CSRF token
    await require_csrf(request)
    
    try:
        figure_manager = get_figure_manager()
        
        current_metadata = await figure_manager.get_figure_metadata_async(figure_id)
        if not current_metadata:
            return RedirectResponse(url="/admin/", status_code=303)
        
        form_data = {
            'name': name.strip(),
            'description': description.strip(),
            'personality_prompt': personality_prompt.strip(),
            'birth_year': birth_year.strip(),
            'death_year': death_year.strip()
        }
        
        validation_errors = validate_figure_data(form_data, is_update=True)
        if validation_errors:
            return RedirectResponse(url=f"/admin/figure/{figure_id}/edit", status_code=303)
        
        updates = {}
        
        name_clean = sanitize_figure_name(form_data['name']) if form_data['name'] else current_metadata.get('name')
        description_clean = form_data['description'][:400]
        personality_clean = form_data['personality_prompt'][:400]
        
        if name_clean and name_clean != current_metadata.get('name'):
            updates['name'] = name_clean
        if description_clean != current_metadata.get('description', ''):
            updates['description'] = description_clean
        if personality_clean != current_metadata.get('personality_prompt', ''):
            updates['personality_prompt'] = personality_clean
        
        metadata = current_metadata.get('metadata', {})
        
        if form_data['birth_year']:
            metadata['birth_year'] = int(form_data['birth_year'])
        elif 'birth_year' in metadata:
            del metadata['birth_year']
        
        if form_data['death_year']:
            metadata['death_year'] = int(form_data['death_year'])
        elif 'death_year' in metadata:
            del metadata['death_year']
        
        if image and image.filename and allowed_image_file(image.filename):
            try:
                old_image = metadata.get('image')
                if old_image:
                    old_image_path = os.path.join(FIGURE_IMAGES_DIR, old_image)
                    if os.path.exists(old_image_path):
                        os.remove(old_image_path)
                
                file_extension = Path(image.filename).suffix.lower()
                image_filename = f"{figure_id}{file_extension}"
                image_path = os.path.join(FIGURE_IMAGES_DIR, image_filename)
                content = await image.read()
                with open(image_path, 'wb') as f:
                    f.write(content)
                
                metadata['image'] = image_filename
            except Exception as e:
                logger.error(f"Error updating image: {str(e)}")
        
        updates['metadata'] = metadata
        
        await figure_manager.update_figure_metadata_async(figure_id, updates)
        
        return RedirectResponse(url=f"/admin/figure/{figure_id}", status_code=303)
    
    except Exception as e:
        logger.error(f"Error updating figure {figure_id}: {e}")
        return RedirectResponse(url=f"/admin/figure/{figure_id}", status_code=303)


@admin_router.get("/figure/{figure_id}/upload", response_class=HTMLResponse, name="admin.upload_documents_form")
async def upload_documents_form(request: Request, figure_id: str):
    """Redirect to edit page which includes upload functionality."""
    return RedirectResponse(url=f"/admin/figure/{figure_id}/edit#upload-section", status_code=303)


@admin_router.post("/figure/{figure_id}/upload", name="admin.upload_documents")
async def upload_documents(
    request: Request,
    figure_id: str,
    files: List[UploadFile] = File(...),
    max_chunk_chars: int = Form(1000),
    overlap_percent: int = Form(OVERLAP_PERCENT)
):
    """Upload documents to a figure."""
    if not await check_login(request):
        raise HTTPException(status_code=401, detail="Login required")
    
    # Validate CSRF token
    await require_csrf(request)
    
    try:
        figure_manager = get_figure_manager()
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        figure_metadata = await figure_manager.get_figure_metadata_async(figure_id)
        if not figure_metadata:
            if is_ajax:
                return JSONResponse(status_code=404, content={'error': f'Figure {figure_id} not found'})
            return RedirectResponse(url="/admin/", status_code=303)
        
        # Validate chunking settings
        max_chunk_chars = max(500, min(3000, max_chunk_chars))
        overlap_percent = max(0, min(50, overlap_percent))
        
        document_processor = DocumentProcessor(
            max_chunk_chars=max_chunk_chars,
            overlap_percent=overlap_percent
        )
        
        valid_files = [f for f in files if f.filename]
        if not valid_files:
            if is_ajax:
                return JSONResponse(status_code=400, content={'error': 'No files selected'})
            return RedirectResponse(url=f"/admin/figure/{figure_id}/edit", status_code=303)
        
        successful_uploads = 0
        total_files = len(valid_files)
        all_results = []
        
        for file in valid_files:
            file_result = {
                'filename': file.filename,
                'status': 'processing',
                'chunks': [],
                'total_chunks': 0,
                'error': None
            }
            
            if allowed_file(file.filename):
                try:
                    file_content = await file.read()
                    original_filename = file.filename
                    
                    safe_filename = secure_filename(original_filename)
                    if not safe_filename or safe_filename.startswith('.'):
                        file_ext = Path(original_filename).suffix.lower()
                        safe_filename = f"upload_{int(time.time() * 1000)}{file_ext}"
                    
                    file_extension = Path(original_filename).suffix.lower()
                    if file_extension == '.pdf':
                        file_type = 'pdf'
                    elif file_extension in ['.txt', '.text']:
                        file_type = 'txt'
                    elif file_extension == '.docx':
                        file_type = 'docx'
                    else:
                        file_result['status'] = 'error'
                        file_result['error'] = 'Unsupported file type'
                        all_results.append(file_result)
                        continue
                    
                    chunks = await asyncio.to_thread(
                        document_processor.process_file, file_content, safe_filename, file_type
                    )
                    file_result['total_chunks'] = len(chunks)
                    
                    chunk_count = 0
                    for chunk_index, chunk in enumerate(chunks):
                        chunk_metadata = chunk['metadata'].copy()
                        chunk_metadata['original_filename'] = original_filename
                        
                        doc_id = await figure_manager.add_document_to_figure_async(
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
                    
                    if chunk_count > 0:
                        file_result['status'] = 'success'
                        file_result['message'] = f'{chunk_count} chunks added'
                        successful_uploads += 1
                    else:
                        file_result['status'] = 'error'
                        file_result['error'] = 'Failed to process file'
                
                except Exception as e:
                    file_result['status'] = 'error'
                    file_result['error'] = str(e)
            else:
                file_result['status'] = 'error'
                file_result['error'] = 'File type not allowed'
            
            all_results.append(file_result)
        
        if successful_uploads > 0:
            await figure_manager.sync_document_count_async(figure_id)
            await figure_manager.invalidate_bm25_cache_async(figure_id)
        
        if is_ajax:
            return JSONResponse(content={
                'success': successful_uploads > 0,
                'successful_uploads': successful_uploads,
                'total_files': total_files,
                'results': all_results
            })
        
        return RedirectResponse(url=f"/admin/figure/{figure_id}", status_code=303)
    
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JSONResponse(status_code=500, content={'error': str(e)})
        return RedirectResponse(url=f"/admin/figure/{figure_id}/edit", status_code=303)


@admin_router.post("/figure/{figure_id}/upload-stream")
async def upload_documents_stream(
    request: Request,
    figure_id: str,
    files: List[UploadFile] = File(...),
    max_chunk_chars: int = Form(1000),
    overlap_percent: int = Form(OVERLAP_PERCENT)
):
    """Upload documents with streaming progress updates."""
    if not await check_login(request):
        raise HTTPException(status_code=401, detail="Login required")
    
    # Validate CSRF token
    await require_csrf(request)
    
    # Read files before generator
    files_data = []
    for file in files:
        if file.filename:
            safe_filename = secure_filename(file.filename)
            if not safe_filename or safe_filename.startswith('.'):
                file_ext = Path(file.filename).suffix.lower()
                safe_filename = f"upload_{int(time.time() * 1000)}{file_ext}"
            
            files_data.append({
                'filename': safe_filename,
                'content': await file.read(),
                'original_filename': file.filename
            })
    
    # Validate chunking settings
    max_chunk_chars = max(500, min(3000, max_chunk_chars))
    overlap_percent = max(0, min(50, overlap_percent))
    
    async def generate():
        try:
            figure_manager = get_figure_manager()
            
            figure_metadata = await figure_manager.get_figure_metadata_async(figure_id)
            if not figure_metadata:
                yield f"data: {json.dumps({'error': 'Figure not found'})}\n\n"
                return
            
            document_processor = DocumentProcessor(
                max_chunk_chars=max_chunk_chars,
                overlap_percent=overlap_percent
            )
            
            if not files_data:
                yield f"data: {json.dumps({'error': 'No files selected'})}\n\n"
                return
            
            total_files = len(files_data)
            successful_uploads = 0
            
            for file_index, file_data in enumerate(files_data):
                filename = file_data['filename']
                original_filename = file_data['original_filename']
                file_content = file_data['content']
                
                yield f"data: {json.dumps({'event': 'file_start', 'file_index': file_index, 'filename': filename})}\n\n"
                
                if not allowed_file(original_filename):
                    yield f"data: {json.dumps({'event': 'file_error', 'file_index': file_index, 'error': 'File type not allowed'})}\n\n"
                    continue
                
                try:
                    file_extension = Path(original_filename).suffix.lower()
                    if file_extension == '.pdf':
                        file_type = 'pdf'
                    elif file_extension in ['.txt', '.text']:
                        file_type = 'txt'
                    elif file_extension == '.docx':
                        file_type = 'docx'
                    else:
                        yield f"data: {json.dumps({'event': 'file_error', 'file_index': file_index, 'error': 'Unsupported file type'})}\n\n"
                        continue
                    
                    chunks = await asyncio.to_thread(
                        document_processor.process_file, file_content, filename, file_type
                    )
                    total_chunks = len(chunks)
                    
                    yield f"data: {json.dumps({'event': 'chunks_count', 'file_index': file_index, 'total_chunks': total_chunks})}\n\n"
                    
                    chunk_count = 0
                    for chunk_index, chunk in enumerate(chunks):
                        chunk_metadata = chunk['metadata'].copy()
                        chunk_metadata['original_filename'] = original_filename
                        
                        doc_id = await figure_manager.add_document_to_figure_async(
                            figure_id=figure_id,
                            text=chunk['text'],
                            metadata=chunk_metadata
                        )
                        if doc_id:
                            chunk_count += 1
                        
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
            
            if successful_uploads > 0:
                await figure_manager.sync_document_count_async(figure_id)
                await figure_manager.invalidate_bm25_cache_async(figure_id)
            
            yield f"data: {json.dumps({'event': 'upload_complete', 'successful_uploads': successful_uploads, 'total_files': total_files})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type='text/event-stream')


@admin_router.post("/figure/{figure_id}/clean", name="admin.clean_figure_documents")
async def clean_figure_documents(request: Request, figure_id: str):
    """Remove all documents from a figure without deleting the figure itself."""
    if not await check_login(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    # Validate CSRF token
    await require_csrf(request)
    
    try:
        figure_manager = get_figure_manager()
        metadata = await figure_manager.get_figure_metadata_async(figure_id)
        
        if not metadata:
            return RedirectResponse(url="/admin/", status_code=303)
        
        await figure_manager.clear_figure_documents_async(figure_id)
        
        return RedirectResponse(url=f"/admin/figure/{figure_id}", status_code=303)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning documents for figure {figure_id}: {e}")
        return RedirectResponse(url=f"/admin/figure/{figure_id}", status_code=303)


@admin_router.post("/figure/{figure_id}/delete", name="admin.delete_figure")
async def delete_figure(request: Request, figure_id: str):
    """Delete a figure and all its data."""
    if not await check_login(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    # Validate CSRF token
    await require_csrf(request)
    
    try:
        figure_manager = get_figure_manager()
        metadata = await figure_manager.get_figure_metadata_async(figure_id)
        
        if not metadata:
            return RedirectResponse(url="/admin/", status_code=303)
        
        await figure_manager.delete_figure_async(figure_id)
        
        return RedirectResponse(url="/admin/", status_code=303)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting figure {figure_id}: {e}")
        return RedirectResponse(url="/admin/", status_code=303)


@admin_router.get("/api/figure/{figure_id}/stats")
async def api_figure_stats(figure_id: str):
    """API endpoint to get figure statistics."""
    try:
        figure_manager = get_figure_manager()
        stats = await figure_manager.get_figure_stats_async(figure_id)
        return stats
    except Exception as e:
        logger.error(f"Error getting stats for figure {figure_id}: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


# ============== LOGS MANAGEMENT ==============

def get_logs_dir(request: Request) -> str:
    """Get the logs directory path."""
    return getattr(request.app.state, 'LOGS_DIR', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs'))


def get_log_files(request: Request) -> List[dict]:
    """Get list of available log files sorted by modification time (newest first)."""
    logs_dir = get_logs_dir(request)
    if not os.path.exists(logs_dir):
        return []
    
    log_files = []
    for filepath in glob.glob(os.path.join(logs_dir, 'server_*.log*')):
        stat = os.stat(filepath)
        filename = os.path.basename(filepath)
        
        match = re.match(r'server_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.log', filename)
        if match:
            date_str = match.group(1)
            try:
                created = datetime.strptime(date_str, '%Y-%m-%d_%H-%M-%S')
            except ValueError:
                created = datetime.fromtimestamp(stat.st_mtime)
        else:
            created = datetime.fromtimestamp(stat.st_mtime)
        
        log_files.append({
            'filename': filename,
            'filepath': filepath,
            'size': stat.st_size,
            'size_human': format_file_size(stat.st_size),
            'modified': datetime.fromtimestamp(stat.st_mtime),
            'created': created,
            'is_current': False
        })
    
    log_files.sort(key=lambda x: x['created'], reverse=True)
    return log_files


@admin_router.get("/logs", response_class=HTMLResponse, name="admin.logs")
async def logs(request: Request):
    """Display log files viewer."""
    if not await check_login(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    log_files = get_log_files(request)
    csrf_token = generate_csrf_token(request)
    templates = request.app.state.templates
    return templates.TemplateResponse("admin/logs.html", {"request": request, "log_files": log_files, "csrf_token": csrf_token})


@admin_router.get("/api/logs")
async def api_logs_list(request: Request):
    """API endpoint to get list of log files."""
    if not await check_login(request):
        raise HTTPException(status_code=401, detail="Login required")
    
    log_files = get_log_files(request)
    for f in log_files:
        f['modified'] = f['modified'].isoformat()
        f['created'] = f['created'].isoformat()
        del f['filepath']
    return log_files


@admin_router.get("/api/logs/{filename}")
async def api_log_content(request: Request, filename: str, lines: Optional[int] = None, search: str = "", level: str = ""):
    """API endpoint to get content of a specific log file."""
    if not await check_login(request):
        raise HTTPException(status_code=401, detail="Login required")
    
    safe_filename = os.path.basename(filename)
    if not safe_filename.startswith('server_') or '.log' not in safe_filename:
        raise HTTPException(status_code=400, detail="Invalid log file name")
    
    logs_dir = get_logs_dir(request)
    filepath = os.path.join(logs_dir, safe_filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Log file not found")
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.readlines()
        
        if level:
            level_upper = level.upper()
            content = [line for line in content if f'| {level_upper}' in line or level_upper in line[:50]]
        
        if search:
            search_lower = search.lower()
            content = [line for line in content if search_lower in line.lower()]
        
        if lines and lines > 0:
            content = content[-lines:]
        
        return {
            'filename': safe_filename,
            'content': ''.join(content),
            'total_lines': len(content),
            'is_current': False
        }
    except Exception as e:
        logger.error(f"Error reading log file {filename}: {str(e)}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@admin_router.get("/api/logs/{filename}/download")
async def download_log(request: Request, filename: str):
    """Download a log file."""
    if not await check_login(request):
        raise HTTPException(status_code=401, detail="Login required")
    
    safe_filename = os.path.basename(filename)
    if not safe_filename.startswith('server_') or '.log' not in safe_filename:
        raise HTTPException(status_code=400, detail="Invalid log file name")
    
    logs_dir = get_logs_dir(request)
    filepath = os.path.join(logs_dir, safe_filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Log file not found")
    
    return FileResponse(filepath, filename=safe_filename)


@admin_router.post("/api/logs/{filename}/delete")
async def delete_log(request: Request, filename: str):
    """Delete a log file."""
    if not await check_login(request):
        raise HTTPException(status_code=401, detail="Login required")
    
    # Validate CSRF token
    await require_csrf(request)
    
    safe_filename = os.path.basename(filename)
    if not safe_filename.startswith('server_') or '.log' not in safe_filename:
        raise HTTPException(status_code=400, detail="Invalid log file name")
    
    logs_dir = get_logs_dir(request)
    filepath = os.path.join(logs_dir, safe_filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Log file not found")
    
    try:
        os.remove(filepath)
        logger.info(f"Deleted log file: {safe_filename}")
        return {'success': True, 'message': f'Deleted {safe_filename}'}
    except Exception as e:
        logger.error(f"Error deleting log file {filename}: {str(e)}")
        return JSONResponse(status_code=500, content={'error': str(e)})


# ============== SYSTEM PAGE ==============

@admin_router.get("/system", response_class=HTMLResponse, name="admin.system")
async def system(request: Request):
    """Display system status and debug tools."""
    if not await check_login(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    csrf_token = generate_csrf_token(request)
    templates = request.app.state.templates
    return templates.TemplateResponse("admin/system.html", {"request": request, "csrf_token": csrf_token})


# ============== DEBUG ENDPOINTS ==============

from chat_routes import session_data as chat_session_data, session_lock as chat_session_lock, cleanup_expired_sessions, SESSION_TIMEOUT_SECONDS


@admin_router.get("/api/debug/sessions")
async def debug_sessions(request: Request):
    """Debug endpoint to check active sessions count."""
    if not await check_login(request):
        raise HTTPException(status_code=401, detail="Login required")
    
    try:
        now = datetime.now()
        async with chat_session_lock:
            active_count = len(chat_session_data)
            sessions_info = []
            for sid, data in chat_session_data.items():
                last_activity = data.get('last_activity')
                inactive_secs = (now - last_activity).total_seconds() if last_activity else 0
                sessions_info.append({
                    'session_id': sid[:8] + '...',
                    'figure': data.get('current_figure'),
                    'messages': len(data.get('conversation_history', [])),
                    'inactive_minutes': round(inactive_secs / 60, 1)
                })
        
        return {
            'active_sessions': active_count,
            'timeout_hours': SESSION_TIMEOUT_SECONDS / 3600,
            'sessions': sessions_info
        }
    except Exception as e:
        logger.error(f"Error in debug sessions: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@admin_router.post("/api/debug/sessions/cleanup")
async def cleanup_sessions_endpoint(request: Request):
    """Manually trigger session cleanup."""
    if not await check_login(request):
        raise HTTPException(status_code=401, detail="Login required")
    
    # Validate CSRF token
    await require_csrf(request)
    
    try:
        cleaned = await cleanup_expired_sessions()
        async with chat_session_lock:
            remaining = len(chat_session_data)
        return {'cleaned': cleaned, 'remaining': remaining}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in session cleanup: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@admin_router.post("/api/debug/rebuild-bm25")
async def rebuild_bm25(request: Request):
    """Rebuild BM25 indexes for all figures."""
    if not await check_login(request):
        raise HTTPException(status_code=401, detail="Login required")
    
    await require_csrf(request)
    
    try:
        figure_manager = get_figure_manager()
        figures = await figure_manager.get_figure_list_async()
        
        results = []
        for fig in figures:
            fig_id = fig.get('figure_id')
            try:
                await figure_manager.invalidate_bm25_cache_async(fig_id)
                success = await asyncio.to_thread(figure_manager._build_bm25_from_chromadb, fig_id)
                results.append({
                    'figure_id': fig_id,
                    'name': fig.get('name'),
                    'success': success
                })
            except Exception as e:
                results.append({
                    'figure_id': fig_id,
                    'name': fig.get('name'),
                    'success': False,
                    'error': str(e)
                })
        
        rebuilt = sum(1 for r in results if r['success'])
        return {
            'rebuilt': rebuilt,
            'total': len(results),
            'results': results
        }
    except Exception as e:
        logger.error(f"Error rebuilding BM25 indexes: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@admin_router.get("/api/debug/rag")
async def debug_rag(request: Request):
    """Debug endpoint for figure-specific RAG system status."""
    if not await check_login(request):
        raise HTTPException(status_code=401, detail="Login required")
    
    try:
        debug_info = {
            'figure_manager_initialized': False,
            'errors': []
        }
        
        try:
            figure_manager = get_figure_manager()
            debug_info['figure_manager_initialized'] = True
            
            figures = await figure_manager.get_figure_list_async()
            debug_info['figures'] = []
            for fig in figures:
                fig_id = fig.get('figure_id')
                stats = await figure_manager.get_figure_stats_async(fig_id)
                debug_info['figures'].append({
                    'figure_id': fig_id,
                    'name': fig.get('name'),
                    'document_count': stats.get('document_count', 0)
                })
                
        except Exception as e:
            debug_info['errors'].append(f"Figure manager error: {str(e)}")
        
        return debug_info
    except Exception as e:
        logger.error(f"Error in debug RAG: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})
