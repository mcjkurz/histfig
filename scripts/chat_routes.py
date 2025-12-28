"""
Chat Routes Blueprint
Handles chat interface and conversation functionality.
"""

import re
import json
import logging
import os
import markdown
import secrets
import uuid
import datetime
import threading
from flask import Blueprint, render_template, request, jsonify, Response, make_response, send_from_directory, session, current_app
from figure_manager import get_figure_manager
from config import DEFAULT_LOCAL_MODEL, DEFAULT_EXTERNAL_MODEL, MAX_CONTEXT_MESSAGES, FIGURE_IMAGES_DIR, EXTERNAL_API_KEY, EXTERNAL_API_URL, LOCAL_API_URL, RAG_ENABLED, QUERY_AUGMENTATION_ENABLED, QUERY_AUGMENTATION_MODEL, LOCAL_MODELS, EXTERNAL_MODELS, DOCS_TO_RETRIEVE
from search_utils import format_search_result_for_response
from model_provider import LLMProvider
from query_augmentation import augment_query
from pdf_export import generate_conversation_pdf
from prompts import (
    FIGURE_SYSTEM_PROMPT, DEFAULT_FIGURE_INSTRUCTION,
    USER_MESSAGE_WITH_RAG, USER_MESSAGE_NO_RAG, GENERIC_ASSISTANT_PROMPT,
    get_thinking_instructions
)

# Create blueprint
chat_bp = Blueprint('chat', __name__, template_folder='../templates', static_folder='../static')

# Store conversation history per session (thread-safe with lock)
session_data = {}
session_lock = threading.Lock()

# Session cleanup configuration
SESSION_TIMEOUT_SECONDS = 24 * 60 * 60  # 24 hours
CLEANUP_INTERVAL_SECONDS = 60 * 60  # Run cleanup every hour
_cleanup_thread = None


def clean_thinking_content(text):
    """Remove thinking tags and content from text"""
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return cleaned.strip()


def get_session_id():
    """Get session ID from request header (each page load gets unique ID)"""
    session_id = request.headers.get('X-Session-ID')
    if not session_id:
        # Fallback for requests without header (e.g., direct browser access)
        if 'session_id' not in session:
            session['session_id'] = secrets.token_hex(16)
            session.permanent = True
        return session['session_id']
    return session_id


def _get_or_create_session(session_id):
    """Get or create session data. Caller must hold session_lock."""
    now = datetime.datetime.now()
    if session_id not in session_data:
        session_data[session_id] = {
            'conversation_history': [],
            'current_figure': None,
            'conversation_id': str(uuid.uuid4()),
            'conversation_start_time': now.isoformat(),
            'last_activity': now
        }
    else:
        # Update last activity time
        session_data[session_id]['last_activity'] = now
    return session_data[session_id]


def get_session_data():
    """Get session data for current user. Updates last activity time."""
    session_id = get_session_id()
    with session_lock:
        return _get_or_create_session(session_id)


def cleanup_expired_sessions():
    """Remove sessions that have been inactive for more than 24 hours"""
    now = datetime.datetime.now()
    expired_sessions = []
    
    with session_lock:
        for sid, data in session_data.items():
            last_activity = data.get('last_activity')
            if last_activity:
                inactive_seconds = (now - last_activity).total_seconds()
                if inactive_seconds > SESSION_TIMEOUT_SECONDS:
                    expired_sessions.append(sid)
        
        for sid in expired_sessions:
            del session_data[sid]
    
    if expired_sessions:
        logging.info(f"Cleaned up {len(expired_sessions)} expired session(s)")
    
    return len(expired_sessions)


def _session_cleanup_loop():
    """Background thread that periodically cleans up expired sessions"""
    import time
    while True:
        time.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            cleanup_expired_sessions()
        except Exception as e:
            logging.error(f"Error in session cleanup: {e}")


def start_session_cleanup_thread():
    """Start the background session cleanup thread (if not already running)"""
    global _cleanup_thread
    if _cleanup_thread is None or not _cleanup_thread.is_alive():
        _cleanup_thread = threading.Thread(target=_session_cleanup_loop, daemon=True)
        _cleanup_thread.start()
        logging.info("Session cleanup thread started (24h timeout, hourly cleanup)")


# Start cleanup thread when module loads
start_session_cleanup_thread()


def save_conversation_to_json(user_session, session_id):
    """Save conversation to JSON file automatically"""
    try:
        conversation_id = user_session['conversation_id']
        conversation_start_time = user_session['conversation_start_time']
        conversation_history = user_session['conversation_history']
        
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        conversations_dir = os.path.join(project_root, 'conversations')
        os.makedirs(conversations_dir, exist_ok=True)
        
        start_time = datetime.datetime.fromisoformat(conversation_start_time)
        date_str = start_time.strftime('%Y-%m-%d_%H-%M-%S')
        filename = f'conversation_{date_str}_{conversation_id[:8]}.json'
        filepath = os.path.join(conversations_dir, filename)
        
        conversation_data = {
            'conversation_id': conversation_id,
            'start_time': conversation_start_time,
            'last_updated': datetime.datetime.now().isoformat(),
            'current_figure': user_session.get('current_figure'),
            'messages': conversation_history,
            'session_id': session_id
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(conversation_data, f, indent=2, ensure_ascii=False)
            
    except Exception as e:
        logging.error(f"Error auto-saving conversation: {e}")


def add_to_conversation_history(role, content, retrieved_documents=None):
    """Add a message to conversation history for current session (thread-safe)"""
    if role == "assistant":
        content = clean_thinking_content(content)
    
    if not content.strip():
        return
    
    session_id = get_session_id()
    with session_lock:
        user_session = _get_or_create_session(session_id)
        conversation_history = user_session['conversation_history']
        
        message = {"role": role, "content": content}
        
        if role == "assistant" and retrieved_documents:
            message["retrieved_documents"] = retrieved_documents
        
        conversation_history.append(message)
        
        if len(conversation_history) > MAX_CONTEXT_MESSAGES * 2:
            user_session['conversation_history'] = conversation_history[-MAX_CONTEXT_MESSAGES * 2:]
        
        save_conversation_to_json(user_session, get_session_id())


def build_conversation_messages():
    """Build conversation messages list for current session"""
    user_session = get_session_data()
    conversation_history = user_session['conversation_history']
    
    messages = []
    for msg in conversation_history:
        content = clean_thinking_content(msg['content']) if msg['role'] == 'assistant' else msg['content']
        if content.strip():
            messages.append({
                "role": msg["role"],
                "content": content
            })
    
    return messages


def truncate_messages_preserve_system(messages, system_message=None):
    """Truncate messages while preserving the system message"""
    if not messages:
        return messages if not system_message else [system_message]
    
    if system_message:
        max_conversation_messages = (MAX_CONTEXT_MESSAGES * 2) - 1
        conversation_messages = [msg for msg in messages if msg.get('role') != 'system']
        
        if len(conversation_messages) > max_conversation_messages:
            conversation_messages = conversation_messages[-max_conversation_messages:]
        
        return [system_message] + conversation_messages
    else:
        if len(messages) > MAX_CONTEXT_MESSAGES * 2:
            return messages[-MAX_CONTEXT_MESSAGES * 2:]
        return messages


# Routes

@chat_bp.route('/')
def index():
    """Serve the main chat interface"""
    return render_template('index.html')


@chat_bp.route('/favicon.ico')
def favicon():
    """Serve favicon from static folder"""
    return send_from_directory(current_app.static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')


@chat_bp.route('/api/models-by-source')
def get_models_by_source():
    """Get model lists for both local and external sources"""
    try:
        local_models = []
        if LOCAL_MODELS:
            local_models = LOCAL_MODELS
        else:
            try:
                provider = LLMProvider(base_url=LOCAL_API_URL, api_key=None)
                models = provider.get_available_models()
                local_models = models if models else []
            except Exception as e:
                logging.warning(f"Could not fetch local models: {e}")
                local_models = [DEFAULT_LOCAL_MODEL] if DEFAULT_LOCAL_MODEL else []
        
        external_models = EXTERNAL_MODELS if EXTERNAL_MODELS else None
        
        return jsonify({
            'local': local_models,
            'external': external_models
        })
    except Exception as e:
        logging.error(f"Error fetching models by source: {e}")
        return jsonify({'local': [], 'external': None})


@chat_bp.route('/api/external-api-key-status')
def get_external_api_key_status():
    """Check if LLM API key is pre-configured"""
    try:
        has_key = bool(EXTERNAL_API_KEY and EXTERNAL_API_KEY.strip())
        masked_key = ""
        if has_key:
            key = EXTERNAL_API_KEY.strip()
            if len(key) > 6:
                masked_key = key[:3] + '*' * (len(key) - 6) + key[-3:]
            else:
                masked_key = '*' * len(key)
        
        return jsonify({
            'has_key': has_key,
            'masked_key': masked_key
        })
    except Exception as e:
        logging.error(f"Error checking LLM API key status: {e}")
        return jsonify({'has_key': False, 'masked_key': ''})


@chat_bp.route('/api/feature-flags')
def get_feature_flags():
    """Get feature flags from server config"""
    return jsonify({
        'rag_enabled': RAG_ENABLED,
        'query_augmentation_enabled': QUERY_AUGMENTATION_ENABLED,
        'query_augmentation_model': QUERY_AUGMENTATION_MODEL,
        'docs_to_retrieve': DOCS_TO_RETRIEVE
    })


@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat requests and stream responses using messages format"""
    try:
        data = request.json
        message = data.get('message', '')
        model = data.get('model', '')
        use_rag = data.get('use_rag', True)
        k = data.get('k', 5)
        thinking_intensity = data.get('thinking_intensity', 'normal')
        temperature = data.get('temperature', 1.0)
        external_config = data.get('external_config', None)
        use_query_augmentation = data.get('query_augmentation', True)
        
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        
        if not model:
            return jsonify({'error': 'No model specified. Please select a model.'}), 400
        
        conversation_messages = build_conversation_messages()
        add_to_conversation_history("user", message)
        
        messages = []
        search_results = None
        system_content = ""
        user_content = message
        augmented_query = None
        
        # Get session and figure data once (avoid duplicate queries)
        user_session = get_session_data()
        current_figure = user_session.get('current_figure')
        figure_manager = get_figure_manager() if current_figure else None
        figure_metadata = figure_manager.get_figure_metadata(current_figure) if figure_manager and current_figure else None
        figure_name = figure_metadata.get('name', current_figure) if figure_metadata else None
        
        # Apply query augmentation if enabled in config AND by user
        if QUERY_AUGMENTATION_ENABLED and use_query_augmentation and use_rag and k > 0:
            try:
                augmented_query = augment_query(message, figure_name=figure_name or "a historical figure")
            except Exception as e:
                logging.warning(f"Query augmentation failed: {e}")
                augmented_query = None
        
        thinking_instruction, response_start = get_thinking_instructions(thinking_intensity)
        
        if use_rag:
            try:
                if current_figure and figure_metadata:
                    search_query = augmented_query if augmented_query else message
                    search_results = figure_manager.search_figure_documents(current_figure, search_query, n_results=k)
                    personality_prompt = figure_metadata.get('personality_prompt', '')
                    
                    base_instruction = DEFAULT_FIGURE_INSTRUCTION.format(figure_name=figure_name) if not personality_prompt else personality_prompt
                    system_content = FIGURE_SYSTEM_PROMPT.format(
                        base_instruction=base_instruction,
                        figure_name=figure_name
                    )
                    
                    if search_results:
                        context_parts = []
                        for result in search_results:
                            filename = result['metadata'].get('filename', 'Unknown')
                            context_parts.append(f"[{filename}]:\n{result['text']}")
                        
                        rag_context = "\n\n".join(context_parts)
                        
                        user_content = USER_MESSAGE_WITH_RAG.format(
                            rag_context=rag_context,
                            message=message,
                            thinking_instruction=thinking_instruction,
                            response_start=response_start
                        )
                    else:
                        user_content = USER_MESSAGE_NO_RAG.format(
                            message=message,
                            thinking_instruction=thinking_instruction,
                            response_start=response_start
                        )
                else:
                    system_content = GENERIC_ASSISTANT_PROMPT
                    user_content = USER_MESSAGE_NO_RAG.format(
                        message=message,
                        thinking_instruction=thinking_instruction,
                        response_start=response_start
                    )
                    
            except Exception as e:
                logging.error(f"Error in RAG enhancement: {e}")
                system_content = GENERIC_ASSISTANT_PROMPT
                user_content = USER_MESSAGE_NO_RAG.format(
                    message=message,
                    thinking_instruction=thinking_instruction,
                    response_start=response_start
                )
        else:
            system_content = GENERIC_ASSISTANT_PROMPT
            user_content = USER_MESSAGE_NO_RAG.format(
                message=message,
                thinking_instruction=thinking_instruction,
                response_start=response_start
            )
        
        system_message = {"role": "system", "content": system_content} if system_content else None
        all_conversation_messages = conversation_messages + [{"role": "user", "content": user_content}]
        messages = truncate_messages_preserve_system(all_conversation_messages, system_message)
        
        session_id = get_session_id()
        
        def generate():
            try:
                if external_config:
                    api_key = external_config.get('api_key', '').strip()
                    if not api_key and EXTERNAL_API_KEY:
                        api_key = EXTERNAL_API_KEY.strip()
                    
                    base_url = external_config.get('base_url', EXTERNAL_API_URL)
                    model_to_use = external_config.get('model') or DEFAULT_EXTERNAL_MODEL
                    
                    provider = LLMProvider(
                        base_url=base_url,
                        api_key=api_key,
                        model=model_to_use
                    )
                else:
                    model_to_use = model or DEFAULT_LOCAL_MODEL
                    provider = LLMProvider(
                        base_url=LOCAL_API_URL,
                        api_key=None,
                        model=model_to_use
                    )
                
                stream = provider.chat_stream(messages, model_to_use, temperature)
                
                if augmented_query and augmented_query != message:
                    yield f"data: {json.dumps({'augmented_query': augmented_query})}\n\n"
                
                if use_rag and search_results:
                    sources_data = [format_search_result_for_response(r, current_figure) for r in search_results]
                    yield f"data: {json.dumps({'sources': sources_data})}\n\n"
                
                full_response = ""
                
                for chunk in stream:
                    if 'error' in chunk:
                        yield f"data: {json.dumps({'error': chunk['error']})}\n\n"
                        break
                    
                    if 'content' in chunk:
                        content = chunk['content']
                        full_response += content
                        yield f"data: {json.dumps({'content': content})}\n\n"
                    
                    if chunk.get('done', False):
                        # Save assistant response to conversation history (thread-safe)
                        with session_lock:
                            if session_id in session_data:
                                user_session = session_data[session_id]
                                conversation_history = user_session['conversation_history']
                                
                                cleaned_content = clean_thinking_content(full_response)
                                
                                if cleaned_content.strip():
                                    assistant_msg = {"role": "assistant", "content": cleaned_content}
                                    
                                    if use_rag and search_results:
                                        assistant_msg["retrieved_documents"] = [
                                            format_search_result_for_response(r, current_figure) for r in search_results
                                        ]
                                    
                                    conversation_history.append(assistant_msg)
                                    
                                    if len(conversation_history) > MAX_CONTEXT_MESSAGES * 2:
                                        user_session['conversation_history'] = conversation_history[-MAX_CONTEXT_MESSAGES * 2:]
                                    
                                    save_conversation_to_json(user_session, session_id)
                        
                        yield f"data: {json.dumps({'done': True})}\n\n"
                        break
                            
            except Exception as e:
                logging.error(f"Error in chat stream: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return Response(generate(), mimetype='text/event-stream')
        
    except Exception as e:
        logging.error(f"Error in chat endpoint: {e}")
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/api/health')
def health_check():
    """Check if both local and external model providers are accessible"""
    try:
        external_provider = LLMProvider(base_url=EXTERNAL_API_URL, api_key=EXTERNAL_API_KEY)
        external_models = external_provider.get_available_models()
        
        local_provider = LLMProvider(base_url=LOCAL_API_URL, api_key=None)
        local_models = local_provider.get_available_models()
        
        return jsonify({
            'status': 'healthy' if (external_models or local_models) else 'unhealthy',
            'external_api_url': EXTERNAL_API_URL,
            'external_connected': bool(external_models),
            'external_models_available': len(external_models) if external_models else 0,
            'local_api_url': LOCAL_API_URL,
            'local_connected': bool(local_models),
            'local_models_available': len(local_models) if local_models else 0
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy', 
            'api_url': EXTERNAL_API_URL,
            'connected': False,
            'error': str(e)
        }), 503


@chat_bp.route('/api/rag/stats')
def rag_stats():
    """Get RAG database statistics"""
    try:
        user_session = get_session_data()
        current_figure = user_session['current_figure']
        if current_figure:
            figure_manager = get_figure_manager()
            stats = figure_manager.get_figure_stats(current_figure)
            return jsonify(stats)
        else:
            return jsonify({'total_documents': 0, 'message': 'No figure selected'}), 404
    except Exception as e:
        logging.error(f"Error getting RAG stats: {e}")
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/api/figures')
def get_figures():
    """Get list of available historical figures"""
    try:
        figure_manager = get_figure_manager()
        figures = figure_manager.get_figure_list()
        return jsonify(figures)
    except Exception as e:
        logging.error(f"Error getting figures: {e}")
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/api/figure/<figure_id>')
def get_figure_details(figure_id):
    """Get details for a specific figure"""
    try:
        figure_manager = get_figure_manager()
        metadata = figure_manager.get_figure_metadata(figure_id)
        if not metadata:
            return jsonify({'error': 'Figure not found'}), 404
        
        stats = figure_manager.get_figure_stats(figure_id)
        return jsonify({**metadata, **stats})
    except Exception as e:
        logging.error(f"Error getting figure details: {e}")
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/api/figure/select', methods=['POST'])
def select_figure():
    """Select a figure for the current chat session (thread-safe)"""
    try:
        data = request.json
        figure_id = data.get('figure_id')
        session_id = get_session_id()
        
        if figure_id:
            # Validate figure exists (outside lock - read-only)
            figure_manager = get_figure_manager()
            metadata = figure_manager.get_figure_metadata(figure_id)
            if not metadata:
                return jsonify({'error': 'Figure not found'}), 404
            
            # Update session (inside lock)
            with session_lock:
                user_session = _get_or_create_session(session_id)
                user_session['current_figure'] = figure_id
                user_session['conversation_history'] = []
            
            return jsonify({
                'success': True,
                'current_figure': metadata,
                'figure_name': metadata.get('name', figure_id)
            })
        else:
            with session_lock:
                user_session = _get_or_create_session(session_id)
                user_session['current_figure'] = None
                user_session['conversation_history'] = []
            
            return jsonify({
                'success': True,
                'current_figure': None,
                'figure_name': None
            })
    except Exception as e:
        logging.error(f"Error selecting figure: {e}")
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/api/figure/current')
def get_current_figure():
    """Get currently selected figure for current session"""
    try:
        user_session = get_session_data()
        current_figure = user_session['current_figure']
        if current_figure:
            figure_manager = get_figure_manager()
            metadata = figure_manager.get_figure_metadata(current_figure)
            if metadata:
                return jsonify(metadata)
        
        return jsonify({'figure_id': None, 'figure_name': None})
    except Exception as e:
        logging.error(f"Error getting current figure: {e}")
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/api/markdown', methods=['POST'])
def convert_markdown():
    """Convert markdown text to HTML"""
    try:
        data = request.json
        text = data.get('text', '')
        
        if not text.strip():
            return jsonify({'html': ''})
        
        html_content = markdown.markdown(text, output_format='html5')
        
        if html_content.startswith('<p>') and html_content.endswith('</p>'):
            html_content = html_content[3:-4]
        
        return jsonify({'html': html_content})
    except Exception as e:
        logging.error(f"Error converting markdown: {e}")
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/figure_images/<filename>')
def figure_image(filename):
    """Serve figure images."""
    from image_utils import serve_figure_image
    return serve_figure_image(filename)


@chat_bp.route('/api/export/pdf', methods=['POST'])
def export_conversation_pdf():
    """Export conversation as PDF"""
    try:
        data = request.json
        pdf_bytes = generate_conversation_pdf(data)
        
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=chat_conversation.pdf'
        
        return response
        
    except Exception as e:
        logging.error(f"Error generating PDF: {e}")
        return jsonify({'error': str(e)}), 500
