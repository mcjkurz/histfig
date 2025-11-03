"""
Document upload application for RAG system.
Provides web interface for uploading and managing documents in the vector database.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import os
import logging
import signal
import sys
import secrets
from werkzeug.utils import secure_filename
from hybrid_search import get_hybrid_db
from document_processor import document_processor

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['MAX_FORM_MEMORY_SIZE'] = None  # No limit on form memory size

# Configure logging
logging.basicConfig(level=logging.INFO)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'txt', 'pdf'}

def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Main upload interface."""
    try:
        hybrid_db = get_hybrid_db()
        stats = hybrid_db.get_collection_stats()
        return render_template('upload.html', stats=stats)
    except Exception as e:
        logging.error(f"Error loading upload page: {e}")
        return render_template('upload.html', stats={'total_documents': 0, 'error': str(e)})

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and processing."""
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Only PDF and TXT files are allowed'}), 400
        
        # Read file content
        filename = secure_filename(file.filename)
        file_content = file.read()
        
        if len(file_content) == 0:
            return jsonify({'error': 'File is empty'}), 400
        
        # Determine file type
        file_type = filename.rsplit('.', 1)[1].lower()
        
        # Process the document
        try:
            chunks = document_processor.process_file(file_content, filename, file_type)
        except Exception as e:
            return jsonify({'error': f'Failed to process document: {str(e)}'}), 400
        
        # Add chunks to hybrid database
        hybrid_db = get_hybrid_db()
        added_chunks = 0
        
        for chunk in chunks:
            try:
                hybrid_db.add_document(chunk['text'], chunk['metadata'])
                added_chunks += 1
            except Exception as e:
                logging.error(f"Error adding chunk to database: {e}")
                continue
        
        if added_chunks == 0:
            return jsonify({'error': 'Failed to add any document chunks to database'}), 500
        
        return jsonify({
            'message': f'Successfully uploaded {filename}',
            'chunks_added': added_chunks,
            'total_chunks': len(chunks)
        })
        
    except Exception as e:
        logging.error(f"Error in upload: {e}")
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/api/stats')
def get_stats():
    """Get database statistics."""
    try:
        hybrid_db = get_hybrid_db()
        stats = hybrid_db.get_collection_stats()
        return jsonify(stats)
    except Exception as e:
        logging.error(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/search', methods=['POST'])
def search_documents():
    """Search documents in the vector database."""
    try:
        data = request.json
        query = data.get('query', '')
        n_results = data.get('n_results', 5)
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        hybrid_db = get_hybrid_db()
        results = hybrid_db.hybrid_search(query, n_results)
        
        return jsonify({
            'query': query,
            'results': results,
            'total_found': len(results)
        })
        
    except Exception as e:
        logging.error(f"Error in search: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/documents')
def list_documents():
    """Get list of uploaded documents."""
    try:
        hybrid_db = get_hybrid_db()
        
        # Get all documents (this is a simple approach; for large datasets, implement pagination)
        all_results = hybrid_db.collection.get(include=["metadatas"])
        
        # Group by filename
        documents = {}
        if all_results["metadatas"]:
            for metadata in all_results["metadatas"]:
                filename = metadata.get("filename", "unknown")
                if filename not in documents:
                    documents[filename] = {
                        "filename": filename,
                        "file_type": metadata.get("file_type", "unknown"),
                        "chunks": 0,
                        "total_chunks": metadata.get("total_chunks", 0),
                        "file_size": metadata.get("file_size", 0)
                    }
                documents[filename]["chunks"] += 1
        
        return jsonify({
            'documents': list(documents.values()),
            'total_documents': len(documents)
        })
        
    except Exception as e:
        logging.error(f"Error listing documents: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/clear', methods=['POST'])
def clear_database():
    """Clear all documents from the database."""
    try:
        hybrid_db = get_hybrid_db()
        success = hybrid_db.clear_collection()
        
        if success:
            return jsonify({'message': 'Database cleared successfully'})
        else:
            return jsonify({'error': 'Failed to clear database'}), 500
            
    except Exception as e:
        logging.error(f"Error clearing database: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint."""
    try:
        hybrid_db = get_hybrid_db()
        stats = hybrid_db.get_collection_stats()
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'total_documents': stats['total_documents']
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    logging.info("Shutting down upload application...")
    sys.exit(0)

if __name__ == '__main__':
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Ensure the chroma_db directory exists
    os.makedirs('./chroma_db', exist_ok=True)
    
    # Check if running in production mode via environment variable
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    
    try:
        app.run(debug=debug_mode, host='0.0.0.0', port=5002)
    except KeyboardInterrupt:
        logging.info("Upload application stopped by user")
    except Exception as e:
        logging.error(f"Upload application error: {e}")
    finally:
        logging.info("Upload application shutdown complete")
