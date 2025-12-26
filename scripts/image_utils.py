"""
Shared utilities for serving figure images.
"""

import os
import logging
from flask import send_from_directory, jsonify
from config import FIGURE_IMAGES_DIR


def serve_figure_image(filename: str):
    """
    Serve a figure image file.
    
    Args:
        filename: Name of the image file to serve
        
    Returns:
        Flask response with image or 404 error
    """
    try:
        figure_images_path = os.path.abspath(FIGURE_IMAGES_DIR)
        return send_from_directory(figure_images_path, filename)
    except Exception as e:
        logging.error(f"Error serving figure image {filename}: {str(e)}")
        return jsonify({'error': 'Image not found'}), 404

