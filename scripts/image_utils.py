"""
Shared utilities for serving figure images.
Updated for FastAPI.
"""

import os
import logging
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger('histfig')
from config import FIGURE_IMAGES_DIR


async def serve_figure_image(filename: str):
    """
    Serve a figure image file.
    
    Args:
        filename: Name of the image file to serve
        
    Returns:
        FastAPI FileResponse with image or 404 error
    """
    try:
        figure_images_path = os.path.realpath(FIGURE_IMAGES_DIR)
        file_path = os.path.realpath(os.path.join(figure_images_path, filename))
        
        # Prevent path traversal attacks
        if not file_path.startswith(figure_images_path + os.sep) and file_path != figure_images_path:
            logger.warning(f"Path traversal attempt blocked: {filename}")
            return JSONResponse(status_code=400, content={'error': 'Invalid filename'})
        
        if not os.path.exists(file_path):
            return JSONResponse(status_code=404, content={'error': 'Image not found'})
        
        return FileResponse(file_path)
    except Exception as e:
        logger.error(f"Error serving figure image {filename}: {str(e)}")
        return JSONResponse(status_code=404, content={'error': 'Image not found'})
