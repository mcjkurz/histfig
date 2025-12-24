"""
Chat Routes Blueprint
Handles chat interface and conversation functionality.
"""

from flask import Blueprint, render_template, request, jsonify, Response, make_response, send_from_directory, session, current_app
import requests
import json
import logging
import os
import markdown
import secrets
import uuid
import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from figure_manager import get_figure_manager
from config import DEFAULT_MODEL, MAX_CONTEXT_MESSAGES, FIGURE_IMAGES_DIR, LLM_PROVIDER, LLM_API_KEY, LLM_API_URL, RAG_ENABLED, QUERY_AUGMENTATION_ENABLED, QUERY_AUGMENTATION_MODEL
from model_provider import get_model_provider, LLMProvider
from query_augmentation import augment_query
from prompts import (
    FIGURE_SYSTEM_PROMPT, DEFAULT_FIGURE_INSTRUCTION,
    USER_MESSAGE_WITH_RAG, USER_MESSAGE_NO_RAG, GENERIC_ASSISTANT_PROMPT
)

# Create blueprint
chat_bp = Blueprint('chat', __name__, template_folder='../templates', static_folder='../static')

# Store conversation history per session
session_data = {}

def register_unicode_fonts():
    """Register Unicode-capable fonts for PDF generation"""
    try:
        import platform
        system = platform.system()
        
        if system == "Darwin":  # macOS
            font_paths = [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/Hiragino Sans GB.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
                "/System/Library/Fonts/Arial Unicode MS.ttf",
            ]
        elif system == "Linux":
            font_paths = [
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            ]
        else:  # Windows
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simsun.ttc",
                "C:/Windows/Fonts/arial.ttf",
            ]
        
        for font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont('UnicodeFont', font_path))
                    return 'UnicodeFont'
            except Exception:
                continue
        
        return 'Helvetica'
        
    except Exception as e:
        logging.warning(f"Could not register Unicode fonts: {e}")
        return 'Helvetica'

def clean_thinking_content(text):
    """Remove thinking tags and content from text"""
    import re
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return cleaned.strip()

def get_thinking_instructions(intensity):
    """Get thinking instruction and response start based on intensity level"""
    if intensity == 'none':
        instruction = "\n\nPlease respond directly to the user's message. You are not allowed to analyze the query or provide any other information, please respond directly."
        response_start = "<think></think>\n\n"
    elif intensity == 'low':
        instruction = "\n\nPlease think briefly (3-4 sentences only, not more than 6 sentences) before answering."
        response_start = ""
    elif intensity == 'high':
        instruction = "\n\nPlease think deeply and thoroughly about this question. Consider multiple perspectives and implications before answering."
        response_start = ""
    else:
        instruction = "\n\nThink through your answer before responding, but do not spend too much time on it."
        response_start = ""
    
    return instruction, response_start

def get_session_id():
    """Get or create a session ID for the current user"""
    if 'session_id' not in session:
        session['session_id'] = secrets.token_hex(16)
        session.permanent = True
    return session['session_id']

def get_session_data():
    """Get session data for the current user"""
    session_id = get_session_id()
    if session_id not in session_data:
        conversation_id = str(uuid.uuid4())
        session_data[session_id] = {
            'conversation_history': [],
            'current_figure': None,
            'conversation_id': conversation_id,
            'conversation_start_time': datetime.datetime.now().isoformat()
        }
    return session_data[session_id]

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
    """Add a message to conversation history for current session"""
    user_session = get_session_data()
    conversation_history = user_session['conversation_history']
    
    if role == "assistant":
        content = clean_thinking_content(content)
    
    if content.strip():
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

@chat_bp.route('/')
def index():
    """Serve the main chat interface"""
    return render_template('index.html')

@chat_bp.route('/favicon.ico')
def favicon():
    """Serve favicon from static folder"""
    return send_from_directory(current_app.static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@chat_bp.route('/api/models')
def get_models():
    """Get list of available models from current provider"""
    try:
        provider = get_model_provider()
        models = provider.get_available_models()
        if models:
            return jsonify(models)
        else:
            return jsonify([DEFAULT_MODEL])
    except Exception as e:
        logging.error(f"Error fetching models: {e}")
        return jsonify([DEFAULT_MODEL])

@chat_bp.route('/api/external-api-key-status')
def get_external_api_key_status():
    """Check if LLM API key is pre-configured"""
    try:
        has_key = bool(LLM_API_KEY and LLM_API_KEY.strip())
        masked_key = ""
        if has_key:
            key = LLM_API_KEY.strip()
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
        'query_augmentation_model': QUERY_AUGMENTATION_MODEL
    })

@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat requests and stream responses using messages format"""
    try:
        data = request.json
        message = data.get('message', '')
        model = data.get('model', DEFAULT_MODEL)
        use_rag = data.get('use_rag', True)
        k = data.get('k', 5)
        thinking_intensity = data.get('thinking_intensity', 'normal')
        temperature = data.get('temperature', 1.0)
        external_config = data.get('external_config', None)
        use_query_augmentation = data.get('query_augmentation', True)
        
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        
        conversation_messages = build_conversation_messages()
        add_to_conversation_history("user", message)
        
        messages = []
        search_results = None
        system_content = ""
        user_content = message
        augmented_query = None
        
        # Get figure name early for query augmentation
        figure_name = None
        if use_rag:
            user_session = get_session_data()
            current_figure = user_session.get('current_figure')
            if current_figure:
                figure_manager = get_figure_manager()
                figure_metadata = figure_manager.get_figure_metadata(current_figure)
                if figure_metadata:
                    figure_name = figure_metadata.get('name', current_figure)
        
        # Apply query augmentation if enabled in config AND by user
        if QUERY_AUGMENTATION_ENABLED and use_query_augmentation and use_rag and k > 0:
            try:
                augmented_query = augment_query(message, figure_name=figure_name or "a historical figure")
                if augmented_query and augmented_query != message:
                    logging.info(f"Query augmented: '{message}' -> '{augmented_query}'")
            except Exception as e:
                logging.warning(f"Query augmentation failed: {e}")
                augmented_query = None
        
        thinking_instruction, response_start = get_thinking_instructions(thinking_intensity)
        
        if use_rag:
            try:
                user_session = get_session_data()
                current_figure = user_session['current_figure']
                
                if current_figure:
                    figure_manager = get_figure_manager()
                    figure_metadata = figure_manager.get_figure_metadata(current_figure)
                    
                    if figure_metadata:
                        # Use augmented query for search if available
                        search_query = augmented_query if augmented_query else message
                        search_results = figure_manager.search_figure_documents(current_figure, search_query, n_results=k)
                        personality_prompt = figure_metadata.get('personality_prompt', '')
                        figure_name = figure_metadata.get('name', current_figure)
                        
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
        user_session = get_session_data()
        current_figure = user_session.get('current_figure')
        
        def generate():
            try:
                if external_config:
                    # Use user-provided config, fall back to server config
                    api_key = external_config.get('api_key', '').strip()
                    if not api_key and LLM_API_KEY:
                        api_key = LLM_API_KEY.strip()
                    
                    base_url = external_config.get('base_url', LLM_API_URL)
                    
                    provider = LLMProvider(
                        base_url=base_url,
                        api_key=api_key,
                        model=external_config.get('model', 'GPT-5-mini')
                    )
                    model_to_use = external_config.get('model', 'GPT-5-mini')
                else:
                    provider = get_model_provider()
                    model_to_use = model
                
                stream = provider.chat_stream(messages, model_to_use, temperature)
                
                # Send augmented query if available
                if augmented_query and augmented_query != message:
                    yield f"data: {json.dumps({'augmented_query': augmented_query})}\n\n"
                
                if use_rag and search_results:
                    sources_data = []
                    for result in search_results:
                        if current_figure:
                            doc_id = result.get('document_id', 'UNKNOWN')
                            sources_data.append({
                                'document_id': doc_id,
                                'filename': result['metadata']['filename'],
                                'text': result['text'][:200] + '...' if len(result['text']) > 200 else result['text'],
                                'full_text': result['text'],
                                'similarity': result.get('similarity', 0),
                                'cosine_similarity': result.get('cosine_similarity', result.get('similarity', 0)),
                                'bm25_score': result.get('bm25_score', 0),
                                'rrf_score': result.get('rrf_score', 0),
                                'top_matching_words': result.get('top_matching_words', []),
                                'chunk_index': result['metadata'].get('chunk_index', 0),
                                'figure_id': current_figure
                            })
                        else:
                            doc_id = result.get('chunk_id', 'UNKNOWN')
                            sources_data.append({
                                'chunk_id': doc_id,
                                'doc_id': f"DOC{doc_id}",
                                'filename': result['metadata']['filename'],
                                'text': result['text'][:200] + '...' if len(result['text']) > 200 else result['text'],
                                'full_text': result['text'],
                                'similarity': result.get('similarity', 0),
                                'cosine_similarity': result.get('cosine_similarity', result.get('similarity', 0)),
                                'bm25_score': result.get('bm25_score', 0),
                                'rrf_score': result.get('rrf_score', 0),
                                'top_matching_words': result.get('top_matching_words', []),
                                'chunk_index': result['metadata'].get('chunk_index', 0)
                            })
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
                        if session_id in session_data:
                            user_session = session_data[session_id]
                            conversation_history = user_session['conversation_history']
                            
                            cleaned_content = clean_thinking_content(full_response)
                            
                            if cleaned_content.strip():
                                assistant_msg = {"role": "assistant", "content": cleaned_content}
                                
                                if use_rag and search_results:
                                    retrieved_docs = []
                                    for result in search_results:
                                        if current_figure:
                                            doc_id = result.get('document_id', 'UNKNOWN')
                                            retrieved_docs.append({
                                                'document_id': doc_id,
                                                'filename': result['metadata']['filename'],
                                                'text': result['text'][:200] + '...' if len(result['text']) > 200 else result['text'],
                                                'full_text': result['text'],
                                                'similarity': result.get('similarity', 0),
                                                'cosine_similarity': result.get('cosine_similarity', result.get('similarity', 0)),
                                                'bm25_score': result.get('bm25_score', 0),
                                                'rrf_score': result.get('rrf_score', 0),
                                                'top_matching_words': result.get('top_matching_words', []),
                                                'chunk_index': result['metadata'].get('chunk_index', 0),
                                                'figure_id': current_figure
                                            })
                                        else:
                                            doc_id = result.get('chunk_id', 'UNKNOWN')
                                            retrieved_docs.append({
                                                'chunk_id': doc_id,
                                                'doc_id': f"DOC{doc_id}",
                                                'filename': result['metadata']['filename'],
                                                'text': result['text'][:200] + '...' if len(result['text']) > 200 else result['text'],
                                                'full_text': result['text'],
                                                'similarity': result.get('similarity', 0),
                                                'cosine_similarity': result.get('cosine_similarity', result.get('similarity', 0)),
                                                'bm25_score': result.get('bm25_score', 0),
                                                'rrf_score': result.get('rrf_score', 0),
                                                'top_matching_words': result.get('top_matching_words', []),
                                                'chunk_index': result['metadata'].get('chunk_index', 0)
                                            })
                                    assistant_msg["retrieved_documents"] = retrieved_docs
                                
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
    """Check if the model provider is accessible"""
    try:
        provider = get_model_provider()
        provider_name = LLM_PROVIDER
        
        models = provider.get_available_models()
        
        if models:
            return jsonify({
                'status': 'healthy', 
                'provider': provider_name,
                'connected': True,
                'models_available': len(models)
            })
        else:
            return jsonify({
                'status': 'unhealthy', 
                'provider': provider_name,
                'connected': False,
                'error': 'No models available'
            }), 503
    except Exception as e:
        return jsonify({
            'status': 'unhealthy', 
            'provider': LLM_PROVIDER,
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

@chat_bp.route('/api/rag/reset', methods=['POST'])
def reset_rag():
    """Reset figure-specific RAG collections"""
    try:
        user_session = get_session_data()
        current_figure = user_session['current_figure']
        if current_figure:
            figure_manager = get_figure_manager()
            stats = figure_manager.get_figure_stats(current_figure)
            return jsonify({'message': 'Figure RAG reset successfully', 'stats': stats})
        else:
            return jsonify({'message': 'No figure selected, nothing to reset'}), 404
    except Exception as e:
        logging.error(f"Error resetting figure RAG: {e}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/api/debug/rag')
def debug_rag():
    """Debug endpoint for figure-specific RAG system status"""
    try:
        user_session = get_session_data()
        current_figure = user_session['current_figure']
        debug_info = {
            'session_id': get_session_id(),
            'current_figure': current_figure,
            'figure_manager_initialized': False,
            'errors': []
        }
        
        try:
            figure_manager = get_figure_manager()
            debug_info['figure_manager_initialized'] = True
            
            if current_figure:
                figure_stats = figure_manager.get_figure_stats(current_figure)
                debug_info['figure_stats'] = figure_stats
            else:
                debug_info['message'] = 'No figure selected - RAG not available'
                
        except Exception as e:
            debug_info['errors'].append(f"Figure manager error: {str(e)}")
        
        return jsonify(debug_info)
    except Exception as e:
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
    """Select a figure for the current chat session"""
    try:
        user_session = get_session_data()
        
        data = request.json
        figure_id = data.get('figure_id')
        
        if figure_id:
            figure_manager = get_figure_manager()
            metadata = figure_manager.get_figure_metadata(figure_id)
            if not metadata:
                return jsonify({'error': 'Figure not found'}), 404
            
            user_session['current_figure'] = figure_id
            user_session['conversation_history'] = []
            
            return jsonify({
                'success': True,
                'current_figure': metadata,
                'figure_name': metadata.get('name', figure_id)
            })
        else:
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
def serve_figure_image(filename):
    """Serve figure images."""
    try:
        figure_images_path = os.path.abspath(FIGURE_IMAGES_DIR)
        logging.info(f"Serving figure image {filename} from {figure_images_path}")
        return send_from_directory(figure_images_path, filename)
    except Exception as e:
        logging.error(f"Error serving figure image {filename}: {str(e)}")
        logging.error(f"Attempted path: {os.path.abspath(FIGURE_IMAGES_DIR)}")
        return jsonify({'error': 'Image not found'}), 404

@chat_bp.route('/api/export/pdf', methods=['POST'])
def export_conversation_pdf():
    """Export conversation as PDF"""
    try:
        data = request.json
        title = data.get('title', 'Chat Conversation')
        date = data.get('date', '')
        messages = data.get('messages', [])
        figure = data.get('figure', 'General Chat')
        figure_name = data.get('figure_name', figure)
        figure_data = data.get('figure_data', None)
        document_count = data.get('document_count', '0')
        model = data.get('model', 'Unknown')
        temperature = data.get('temperature', '1.0')
        thinking_enabled = data.get('thinking_enabled', False)
        rag_enabled = data.get('rag_enabled', True)
        retrieved_documents = data.get('retrieved_documents', [])
        
        unicode_font = register_unicode_fonts()
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter,
                              rightMargin=72, leftMargin=72,
                              topMargin=72, bottomMargin=18)
        
        story = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=18,
            fontName=unicode_font,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=20,
            alignment=TA_CENTER
        )
        
        settings_style = ParagraphStyle(
            'Settings',
            parent=styles['Normal'],
            fontSize=10,
            fontName=unicode_font,
            textColor=colors.HexColor('#7f8c8d'),
            spaceAfter=20,
            alignment=TA_LEFT
        )
        
        message_style = ParagraphStyle(
            'Message',
            parent=styles['Normal'],
            fontSize=11,
            fontName=unicode_font,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=12,
            spaceBefore=6,
            leftIndent=0,
            rightIndent=0,
            alignment=TA_LEFT,
            leading=14
        )
        
        story.append(Paragraph(title, title_style))
        
        if figure_data and figure != 'General Chat':
            figure_desc_style = ParagraphStyle(
                'FigureDescription',
                parent=styles['Normal'],
                fontSize=11,
                fontName=unicode_font,
                textColor=colors.HexColor('#2c3e50'),
                spaceAfter=20,
                spaceBefore=10,
                alignment=TA_LEFT,
                leading=14,
                leftIndent=20,
                rightIndent=20
            )
            
            figure_header_style = ParagraphStyle(
                'FigureHeader',
                parent=styles['Heading2'],
                fontSize=14,
                fontName=unicode_font,
                textColor=colors.HexColor('#2c3e50'),
                spaceAfter=10,
                spaceBefore=5,
                alignment=TA_CENTER
            )
            
            figure_text = ""
            if figure_data.get('name'):
                figure_text += f"<b>{figure_data['name']}</b>"
                
                birth_year = figure_data.get('birth_year')
                death_year = figure_data.get('death_year')
                if birth_year or death_year:
                    birth_display = birth_year if birth_year else '?'
                    death_display = death_year if death_year else '?'
                    figure_text += f" ({birth_display} - {death_display})"
                
                figure_text += "<br/><br/>"
            
            if figure_data.get('description'):
                description = figure_data['description'].replace('&', '&amp;')
                description = description.replace('<', '&lt;')
                description = description.replace('>', '&gt;')
                description = description.replace('\n', '<br/>')
                figure_text += f"<b>Description:</b><br/>{description}<br/><br/>"
            
            if figure_data.get('personality_prompt'):
                personality = figure_data['personality_prompt'].replace('&', '&amp;')
                personality = personality.replace('<', '&lt;')
                personality = personality.replace('>', '&gt;')
                personality = personality.replace('\n', '<br/>')
                figure_text += f"<b>Personality:</b><br/>{personality}"
            
            if figure_text.strip():
                story.append(Paragraph("Historical Figure Information", figure_header_style))
                story.append(Paragraph(figure_text, figure_desc_style))
                story.append(Spacer(1, 0.3*inch))
        
        settings_text = f"<b>Chat Settings:</b><br/>"
        settings_text += f"Date: {date}<br/>"
        settings_text += f"Figure: {figure_name}<br/>"
        settings_text += f"Documents: {document_count}<br/>"
        settings_text += f"Model: {model}<br/>"
        settings_text += f"Temperature: {temperature}<br/>"
        settings_text += f"Thinking Mode: {'Enabled' if thinking_enabled else 'Disabled'}<br/>"
        settings_text += f"RAG Mode: {'Enabled' if rag_enabled else 'Disabled'}"
        story.append(Paragraph(settings_text, settings_style))
        story.append(Spacer(1, 0.3*inch))
        
        story.append(Paragraph("<b>Conversation:</b>", message_style))
        story.append(Spacer(1, 0.1*inch))
        
        doc_header_style = ParagraphStyle(
            'DocHeader',
            parent=styles['Normal'],
            fontSize=11,
            fontName=unicode_font,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=5,
            spaceBefore=8
        )
        
        doc_content_style = ParagraphStyle(
            'DocContent',
            parent=styles['Normal'],
            fontSize=9,
            fontName=unicode_font,
            textColor=colors.HexColor('#34495e'),
            spaceAfter=8,
            leftIndent=12,
            rightIndent=12,
            leading=11
        )
        
        doc_meta_style = ParagraphStyle(
            'DocMeta',
            parent=styles['Normal'],
            fontSize=8,
            fontName=unicode_font,
            textColor=colors.HexColor('#7f8c8d'),
            spaceAfter=10,
            leftIndent=12
        )
        
        doc_section_header_style = ParagraphStyle(
            'DocSectionHeader',
            parent=styles['Normal'],
            fontSize=10,
            fontName=unicode_font,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=5,
            spaceBefore=5
        )
        
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            msg_retrieved_documents = msg.get('retrieved_documents', [])
            
            content = content.replace('&', '&amp;')
            content = content.replace('<', '&lt;')
            content = content.replace('>', '&gt;')
            content = content.replace('\n', '<br/>')
            
            if role == 'user':
                story.append(Paragraph(f"<b>User:</b> {content}", message_style))
            else:
                display_name = figure_name.split(' (')[0] if ' (' in figure_name else figure_name
                story.append(Paragraph(f"<b>{display_name}:</b> {content}", message_style))
                
                if msg_retrieved_documents and len(msg_retrieved_documents) > 0:
                    story.append(Spacer(1, 0.05*inch))
                    
                    story.append(Paragraph(f"<b>Retrieved Documents ({len(msg_retrieved_documents)}):</b>", doc_section_header_style))
                    story.append(Spacer(1, 0.05*inch))
                    
                    sorted_docs = sorted(msg_retrieved_documents, key=lambda d: (
                        d.get('filename', ''),
                        d.get('chunk_id') or d.get('document_id') or d.get('doc_id', '')
                    ))
                    
                    for idx, doc_data in enumerate(sorted_docs, 1):
                        filename = doc_data.get('filename', 'Unknown')
                        chunk_id = doc_data.get('chunk_id') or doc_data.get('document_id') or doc_data.get('doc_id', 'unknown')
                        text = doc_data.get('full_text') or doc_data.get('text', '')
                        similarity = doc_data.get('similarity', 0)
                        cosine_similarity = doc_data.get('cosine_similarity', similarity)
                        bm25_score = doc_data.get('bm25_score', 0)
                        rrf_score = doc_data.get('rrf_score', 0)
                        top_matching_words = doc_data.get('top_matching_words', [])
                        
                        header_text = f"Document {idx}: {filename} (Chunk {chunk_id})"
                        story.append(Paragraph(header_text, doc_header_style))
                        
                        meta_parts = []
                        if cosine_similarity > 0:
                            meta_parts.append(f"Cosine Similarity: {cosine_similarity:.2%}")
                        if bm25_score > 0:
                            meta_parts.append(f"BM25 Score: {bm25_score:.2f}")
                        if rrf_score > 0:
                            meta_parts.append(f"RRF Score: {rrf_score:.4f}")
                        if top_matching_words:
                            keywords_str = ', '.join(top_matching_words[:5])
                            meta_parts.append(f"Keywords: {keywords_str}")
                        
                        meta_text = ' | '.join(meta_parts) if meta_parts else f"Relevance Score: {similarity:.2%}"
                        if doc_data.get('timestamp'):
                            meta_text += f" | Retrieved: {doc_data['timestamp']}"
                        story.append(Paragraph(meta_text, doc_meta_style))
                        
                        doc_content = text.replace('&', '&amp;')
                        doc_content = doc_content.replace('<', '&lt;')
                        doc_content = doc_content.replace('>', '&gt;')
                        doc_content = doc_content.replace('\n', '<br/>')
                        
                        story.append(Paragraph(doc_content, doc_content_style))
                        
                        if idx < len(sorted_docs):
                            story.append(Spacer(1, 0.05*inch))
                            from reportlab.platypus import HRFlowable
                            story.append(HRFlowable(width="80%", thickness=0.5, 
                                                   color=colors.HexColor('#e0e0e0'),
                                                   spaceAfter=3, spaceBefore=3))
            
            story.append(Spacer(1, 0.1*inch))
        
        doc.build(story)
        
        pdf = buffer.getvalue()
        buffer.close()
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=chat_conversation.pdf'
        
        return response
        
    except Exception as e:
        logging.error(f"Error generating PDF: {e}")
        return jsonify({'error': str(e)}), 500

