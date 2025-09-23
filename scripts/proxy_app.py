#!/usr/bin/env python3
"""
Reverse Proxy Application
Routes requests between the main chat app and admin app based on URL paths.
- / → Main chat app (port 5003)
- /admin/ → Admin app (port 5004)
"""

from flask import Flask, request, Response
import requests
import logging
import signal
import sys
import os
from config import MAX_CONTENT_LENGTH, PROXY_PORT, CHAT_PORT, ADMIN_PORT, DEBUG_MODE

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['MAX_FORM_MEMORY_SIZE'] = None
logging.basicConfig(level=logging.INFO)

CHAT_APP_URL = f"http://localhost:{CHAT_PORT}"
ADMIN_APP_URL = f"http://localhost:{ADMIN_PORT}"

def proxy_request(target_url, path=""):
    """Proxy a request to the target service"""
    try:
        # Build the full target URL
        url = f"{target_url}{path}"
        
        headers = {key: value for (key, value) in request.headers 
                   if key.lower() not in ['host', 'content-length']}
        
        if request.method in ['POST', 'PUT', 'PATCH']:
            raw_data = request.get_data()
            
            if request.content_type and 'multipart/form-data' in request.content_type:
                headers['Content-Type'] = request.content_type
                logging.debug(f"Proxying multipart upload to {url}")
                logging.debug(f"Content-Type: {request.content_type}")
                logging.debug(f"Data size: {len(raw_data)} bytes")
                resp = requests.request(
                    method=request.method,
                    url=url,
                    headers=headers,
                    data=raw_data,
                    params=request.args,
                    allow_redirects=False,
                    stream=True
                )
            else:
                # For JSON or other data
                resp = requests.request(
                    method=request.method,
                    url=url,
                    headers=headers,
                    data=raw_data,
                    params=request.args,
                    allow_redirects=False,
                    stream=True
                )
        else:
            # For GET, DELETE, etc.
            resp = requests.request(
                method=request.method,
                url=url,
                headers=headers,
                params=request.args,
                allow_redirects=False,
                stream=True
            )
        
        # Check if this is a streaming response (like text/event-stream)
        content_type = resp.headers.get('content-type', '')
        if 'text/event-stream' in content_type:
            # For streaming responses, stream the content directly
            excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
            response_headers = [(name, value) for (name, value) in resp.headers.items()
                               if name.lower() not in excluded_headers]
            
            def generate():
                try:
                    for chunk in resp.iter_content(chunk_size=1024, decode_unicode=False):
                        if chunk:
                            yield chunk
                except Exception as e:
                    logging.error(f"Streaming error: {e}")
                finally:
                    resp.close()
            
            return Response(generate(), resp.status_code, response_headers)
        else:
            # For non-streaming responses, use the original method
            excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
            response_headers = [(name, value) for (name, value) in resp.headers.items()
                               if name.lower() not in excluded_headers]
            
            response = Response(resp.content, resp.status_code, response_headers)
            return response
        
    except requests.exceptions.ConnectionError:
        logging.error(f"Failed to connect to {target_url}")
        return Response("Service unavailable", 503)
    except Exception as e:
        logging.error(f"Proxy error: {e}")
        return Response("Internal server error", 500)

@app.route('/admin', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@app.route('/admin/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@app.route('/admin/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def admin_proxy(path):
    """Route admin requests to the admin app"""
    # Remove /admin prefix and forward to admin app
    if path:
        admin_path = f"/{path}"
    else:
        admin_path = "/"
    
    return proxy_request(ADMIN_APP_URL, admin_path)

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def chat_proxy(path):
    """Route all other requests to the chat app"""
    # Don't proxy admin paths that already went through admin_proxy
    if path.startswith('admin'):
        return Response("Not found", 404)
    
    if path:
        chat_path = f"/{path}"
    else:
        chat_path = "/"
    
    return proxy_request(CHAT_APP_URL, chat_path)

@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        # Check both services
        chat_resp = requests.get(f"{CHAT_APP_URL}/api/health", timeout=2)
        admin_resp = requests.get(f"{ADMIN_APP_URL}/", timeout=2)
        
        chat_healthy = chat_resp.status_code == 200
        admin_healthy = admin_resp.status_code == 200
        
        if chat_healthy and admin_healthy:
            return {"status": "healthy", "chat": "ok", "admin": "ok"}
        else:
            return {"status": "degraded", 
                   "chat": "ok" if chat_healthy else "error",
                   "admin": "ok" if admin_healthy else "error"}, 503
            
    except Exception as e:
        logging.error(f"Health check error: {e}")
        return {"status": "unhealthy", "error": str(e)}, 503

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    logging.info("Shutting down proxy application...")
    sys.exit(0)

if __name__ == '__main__':
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logging.info(f"Starting reverse proxy on port {PROXY_PORT}")
        logging.info(f"Chat app: {CHAT_APP_URL}")
        logging.info(f"Admin app: {ADMIN_APP_URL}")
        app.run(debug=DEBUG_MODE, host='0.0.0.0', port=PROXY_PORT)
    except KeyboardInterrupt:
        logging.info("Proxy application stopped by user")
    except Exception as e:
        logging.error(f"Proxy application error: {e}")
    finally:
        logging.info("Proxy application shutdown complete")
