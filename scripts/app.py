from flask import Flask, render_template, request, jsonify, Response, make_response, send_from_directory, session
import requests
import json
import logging
import os
import signal
import sys
import markdown
import secrets
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
from config import DEFAULT_MODEL, MAX_CONTENT_LENGTH, MAX_CONTEXT_MESSAGES, CHAT_PORT, DEBUG_MODE, FIGURE_IMAGES_DIR, MODEL_PROVIDER
from model_provider import get_model_provider, ExternalProvider

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['MAX_FORM_MEMORY_SIZE'] = None
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours
logging.basicConfig(level=logging.WARNING)

# Store conversation history per session
# We'll use a dictionary to store per-session data
session_data = {}

def register_unicode_fonts():
    """Register Unicode-capable fonts for PDF generation"""
    try:
        # Try to use system fonts that support Chinese characters
        import platform
        system = platform.system()
        
        if system == "Darwin":  # macOS
            # Try to register common macOS fonts that support Chinese
            font_paths = [
                "/System/Library/Fonts/PingFang.ttc",  # PingFang SC
                "/System/Library/Fonts/Hiragino Sans GB.ttc",  # Hiragino Sans GB
                "/System/Library/Fonts/STHeiti Light.ttc",  # STHeiti
                "/System/Library/Fonts/Arial Unicode MS.ttf",  # Arial Unicode MS
            ]
        elif system == "Linux":
            # Try common Linux fonts
            font_paths = [
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            ]
        else:  # Windows
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",  # Microsoft YaHei
                "C:/Windows/Fonts/simsun.ttc",  # SimSun
                "C:/Windows/Fonts/arial.ttf",  # Arial
            ]
        
        # Try to register the first available font
        for font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont('UnicodeFont', font_path))
                    return 'UnicodeFont'
            except Exception as e:
                continue
        
        # Fallback: use Helvetica (built-in font that handles basic Latin)
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
        instruction = "\n\nPlease think very briefly (1-2 sentences only, not more than 3 sentences) before answering."
        response_start = ""
    elif intensity == 'high':
        instruction = "\n\nPlease think deeply and thoroughly about this question. Consider multiple perspectives and implications before answering."
        response_start = ""
    else:
        instruction = "\n\nThink through your answer carefully before responding."
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
        session_data[session_id] = {
            'conversation_history': [],
            'current_figure': None
        }
    return session_data[session_id]

def add_to_conversation_history(role, content):
    """Add a message to conversation history for current session"""
    user_session = get_session_data()
    conversation_history = user_session['conversation_history']
    
    # Clean thinking content from assistant messages
    if role == "assistant":
        content = clean_thinking_content(content)
    
    # Only add if content is not empty
    if content.strip():
        conversation_history.append({"role": role, "content": content})
        
        # Keep only recent messages
        if len(conversation_history) > MAX_CONTEXT_MESSAGES * 2:  # 2 messages per exchange
            user_session['conversation_history'] = conversation_history[-MAX_CONTEXT_MESSAGES * 2:]

def build_conversation_messages():
    """Build conversation messages list for current session"""
    user_session = get_session_data()
    conversation_history = user_session['conversation_history']
    
    # Return messages in the format expected by model providers
    messages = []
    for msg in conversation_history:
        # Clean thinking content from assistant messages
        content = clean_thinking_content(msg['content']) if msg['role'] == 'assistant' else msg['content']
        if content.strip():
            messages.append({
                "role": msg["role"],
                "content": content
            })
    
    return messages

@app.route('/')
def index():
    """Serve the main chat interface - responsive version with three panels"""
    return render_template('index.html')

@app.route('/api/models')
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

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat requests and stream responses using messages format"""
    try:
        data = request.json
        message = data.get('message', '')
        model = data.get('model', DEFAULT_MODEL)
        use_rag = data.get('use_rag', True)  # Enable RAG by default
        k = data.get('k', 5)  # Number of documents to retrieve
        thinking_intensity = data.get('thinking_intensity', 'normal')  # Thinking intensity level
        temperature = data.get('temperature', 1.0)  # Temperature for response generation
        
        # External API configuration
        external_config = data.get('external_config', None)
        
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        
        # Get conversation messages BEFORE adding current message
        conversation_messages = build_conversation_messages()
        
        # Add user message to conversation history AFTER building context
        add_to_conversation_history("user", message)
        
        # Build messages list for the model
        messages = []
        search_results = None
        system_content = ""
        user_content = message
        
        # Get thinking instruction based on intensity
        thinking_instruction, response_start = get_thinking_instructions(thinking_intensity)
        
        if use_rag:
            try:
                user_session = get_session_data()
                current_figure = user_session['current_figure']
                
                if current_figure:
                    # Use figure-specific RAG
                    figure_manager = get_figure_manager()
                    figure_metadata = figure_manager.get_figure_metadata(current_figure)
                    
                    if figure_metadata:
                        # Search in figure's documents
                        search_results = figure_manager.search_figure_documents(current_figure, message, n_results=k)
                        
                        # Get personality prompt if available
                        personality_prompt = figure_metadata.get('personality_prompt', '')
                        figure_name = figure_metadata.get('name', current_figure)
                        
                        # Build system message
                        base_instruction = f"You are responding as {figure_name}." if not personality_prompt else personality_prompt
                        system_content = f"""{base_instruction}

IMPORTANT: Please respond in the same language that the user is using. If the user writes in English, you must respond in English. If the user writes in Chinese, you must respond in Chinese, etc. You must not use tables. Your response must not, under any circumstances, be longer than 1000 words.

Answer as {figure_name} would, drawing from the provided documents when relevant."""
                        
                        if search_results:
                            # Build context from figure's documents
                            context_parts = []
                            for result in search_results:
                                filename = result['metadata'].get('filename', 'Unknown')
                                context_parts.append(f"[{filename}]:\n{result['text']}")
                            
                            rag_context = "\n\n".join(context_parts)
                            
                            # Add RAG context to user message
                            user_content = f"""Based on the following context from your writings and documents:

Your Documents:
{rag_context}

User's Current Question: {message}{thinking_instruction}

{response_start}"""
                        else:
                            # No relevant documents found
                            user_content = f"{message}{thinking_instruction}\n\n{response_start}"
                else:
                    # No figure selected - use generic assistant
                    system_content = """You are a helpful AI assistant.

IMPORTANT: Please respond in the same language that the user is using. If the user writes in English, respond in English. If the user writes in Chinese, respond in Chinese, etc."""
                    user_content = f"{message}{thinking_instruction}\n\n{response_start}"
                    
            except Exception as e:
                logging.error(f"Error in RAG enhancement: {e}")
                # Fallback to generic assistant
                system_content = """You are a helpful AI assistant.

IMPORTANT: Please respond in the same language that the user is using. If the user writes in English, respond in English. If the user writes in Chinese, respond in Chinese, etc."""
                user_content = f"{message}{thinking_instruction}\n\n{response_start}"
        else:
            # RAG disabled - use generic assistant
            system_content = """You are a helpful AI assistant.

IMPORTANT: Please respond in the same language that the user is using. If the user writes in English, respond in English. If the user writes in Chinese, respond in Chinese, etc."""
            user_content = f"{message}{thinking_instruction}\n\n{response_start}"
        
        # Build final messages list
        if system_content:
            messages.append({"role": "system", "content": system_content})
        
        # Add conversation history
        messages.extend(conversation_messages)
        
        # Add current user message
        messages.append({"role": "user", "content": user_content})
        
        # Get the session data before entering the generator (while we still have request context)
        session_id = get_session_id()
        user_session = get_session_data()
        current_figure = user_session.get('current_figure')
        
        def generate():
            try:
                # Get the appropriate model provider
                if external_config:
                    # Use external provider with user-provided configuration
                    provider = ExternalProvider(
                        base_url=external_config.get('base_url', 'https://api.poe.com/v1'),
                        api_key=external_config.get('api_key', ''),
                        model=external_config.get('model', 'GPT-5-mini')
                    )
                    # Override model with external config
                    model = external_config.get('model', 'GPT-5-mini')
                else:
                    # Use default provider from configuration
                    provider = get_model_provider()
                
                # Stream responses from the provider
                stream = provider.chat_stream(messages, model, temperature)
                
                # Send sources first if RAG was used
                if use_rag and search_results:
                    sources_data = []
                    for result in search_results:
                        if current_figure:
                            # Figure-specific source format
                            doc_id = result.get('document_id', 'UNKNOWN')
                            sources_data.append({
                                'document_id': doc_id,
                                'filename': result['metadata']['filename'],
                                'text': result['text'][:200] + '...' if len(result['text']) > 200 else result['text'],
                                'full_text': result['text'],
                                'similarity': result.get('similarity', 0),
                                'chunk_index': result['metadata'].get('chunk_index', 0),
                                'figure_id': current_figure
                            })
                        else:
                            # General RAG source format (original)
                            doc_id = result.get('chunk_id', 'UNKNOWN')
                            sources_data.append({
                                'chunk_id': doc_id,  # Keep for backward compatibility
                                'doc_id': f"DOC{doc_id}",
                                'filename': result['metadata']['filename'],
                                'text': result['text'][:200] + '...' if len(result['text']) > 200 else result['text'],
                                'full_text': result['text'],
                                'similarity': result.get('similarity', 0),
                                'chunk_index': result['metadata'].get('chunk_index', 0)
                            })
                    yield f"data: {json.dumps({'sources': sources_data})}\n\n"
                
                # Collect full response for conversation history
                full_response = ""
                
                # Process chunks from the provider
                for chunk in stream:
                    if 'error' in chunk:
                        yield f"data: {json.dumps({'error': chunk['error']})}\n\n"
                        break
                    
                    if 'content' in chunk:
                        content = chunk['content']
                        full_response += content
                        yield f"data: {json.dumps({'content': content})}\n\n"
                    
                    if chunk.get('done', False):
                        # Add assistant response to conversation history
                        # Use session_id directly instead of calling get_session_data() which needs request context
                        if session_id in session_data:
                            user_session = session_data[session_id]
                            conversation_history = user_session['conversation_history']
                            
                            # Clean thinking content from assistant messages
                            cleaned_content = clean_thinking_content(full_response)
                            
                            # Only add if content is not empty
                            if cleaned_content.strip():
                                conversation_history.append({"role": "assistant", "content": cleaned_content})
                                
                                # Keep only recent messages
                                if len(conversation_history) > MAX_CONTEXT_MESSAGES * 2:
                                    user_session['conversation_history'] = conversation_history[-MAX_CONTEXT_MESSAGES * 2:]
                        
                        yield f"data: {json.dumps({'done': True})}\n\n"
                        break
                            
            except Exception as e:
                logging.error(f"Error in chat stream: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return Response(generate(), mimetype='text/event-stream')
        
    except Exception as e:
        logging.error(f"Error in chat endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """Check if the model provider is accessible"""
    try:
        provider = get_model_provider()
        provider_name = MODEL_PROVIDER
        
        # Try to get models as a health check
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
            'provider': MODEL_PROVIDER,
            'connected': False,
            'error': str(e)
        }), 503

@app.route('/api/rag/stats')
def rag_stats():
    """Get RAG database statistics - now only shows figure-specific stats"""
    try:
        user_session = get_session_data()
        current_figure = user_session['current_figure']
        if current_figure:
            figure_manager = get_figure_manager()
            stats = figure_manager.get_figure_stats(current_figure)
            return jsonify(stats)
        else:
            # No figure selected, no RAG available
            return jsonify({'total_documents': 0, 'message': 'No figure selected'}), 404
    except Exception as e:
        logging.error(f"Error getting RAG stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/rag/reset', methods=['POST'])
def reset_rag():
    """Reset figure-specific RAG collections"""
    try:
        user_session = get_session_data()
        current_figure = user_session['current_figure']
        if current_figure:
            figure_manager = get_figure_manager()
            # Could add figure-specific reset logic here if needed
            stats = figure_manager.get_figure_stats(current_figure)
            return jsonify({'message': 'Figure RAG reset successfully', 'stats': stats})
        else:
            return jsonify({'message': 'No figure selected, nothing to reset'}), 404
    except Exception as e:
        logging.error(f"Error resetting figure RAG: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/rag')
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
        
        # Test figure manager
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

@app.route('/api/figures')
def get_figures():
    """Get list of available historical figures"""
    try:
        figure_manager = get_figure_manager()
        figures = figure_manager.get_figure_list()
        return jsonify(figures)
    except Exception as e:
        logging.error(f"Error getting figures: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/figure/<figure_id>')
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

@app.route('/api/figure/select', methods=['POST'])
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
            # Clear conversation history when switching figures
            user_session['conversation_history'] = []
            
            return jsonify({
                'success': True,
                'current_figure': metadata,  # Return full metadata instead of just ID
                'figure_name': metadata.get('name', figure_id)
            })
        else:
            # Deselect figure (use general chat)
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

@app.route('/api/figure/current')
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

@app.route('/api/markdown', methods=['POST'])
def convert_markdown():
    """Convert markdown text to HTML"""
    try:
        data = request.json
        text = data.get('text', '')
        
        if not text.strip():
            return jsonify({'html': ''})
        
        # Process the text with markdown
        html_content = markdown.markdown(text, output_format='html5')
        
        # Remove outer <p> tags if they exist to keep content inline
        if html_content.startswith('<p>') and html_content.endswith('</p>'):
            html_content = html_content[3:-4]  # Remove <p> and </p>
        
        return jsonify({'html': html_content})
    except Exception as e:
        logging.error(f"Error converting markdown: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/figure_images/<filename>')
def serve_figure_image(filename):
    """Serve figure images."""
    try:
        # Use absolute path for FIGURE_IMAGES_DIR
        import os
        figure_images_path = os.path.abspath(FIGURE_IMAGES_DIR)
        logging.info(f"Serving figure image {filename} from {figure_images_path}")
        return send_from_directory(figure_images_path, filename)
    except Exception as e:
        logging.error(f"Error serving figure image {filename}: {str(e)}")
        logging.error(f"Attempted path: {os.path.abspath(FIGURE_IMAGES_DIR)}")
        return jsonify({'error': 'Image not found'}), 404

@app.route('/api/export/pdf', methods=['POST'])
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
        
        # Register Unicode fonts for Chinese character support
        unicode_font = register_unicode_fonts()
        
        # Create PDF in memory
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter,
                              rightMargin=72, leftMargin=72,
                              topMargin=72, bottomMargin=18)
        
        # Container for the 'Flowable' objects
        story = []
        
        # Define styles
        styles = getSampleStyleSheet()
        
        # Simple title style with Unicode font
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=18,
            fontName=unicode_font,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=20,
            alignment=TA_CENTER
        )
        
        # Settings style with Unicode font
        settings_style = ParagraphStyle(
            'Settings',
            parent=styles['Normal'],
            fontSize=10,
            fontName=unicode_font,
            textColor=colors.HexColor('#7f8c8d'),
            spaceAfter=20,
            alignment=TA_LEFT
        )
        
        # Simple message style with Unicode font
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
            leading=14  # Line height for better readability
        )
        
        # Add title
        story.append(Paragraph(title, title_style))
        
        # Add figure description section if available
        if figure_data and figure != 'General Chat':
            # Figure description style
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
            
            # Figure header style
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
            
            # Build figure description text
            figure_text = ""
            if figure_data.get('name'):
                figure_text += f"<b>{figure_data['name']}</b>"
                
                # Add years if available
                birth_year = figure_data.get('birth_year')
                death_year = figure_data.get('death_year')
                if birth_year or death_year:
                    birth_display = birth_year if birth_year else '?'
                    death_display = death_year if death_year else '?'
                    figure_text += f" ({birth_display} - {death_display})"
                
                figure_text += "<br/><br/>"
            
            # Add nationality and occupation
            if figure_data.get('nationality'):
                figure_text += f"<b>Nationality:</b> {figure_data['nationality']}<br/>"
            if figure_data.get('occupation'):
                figure_text += f"<b>Occupation:</b> {figure_data['occupation']}<br/>"
            
            if figure_data.get('nationality') or figure_data.get('occupation'):
                figure_text += "<br/>"
            
            # Add description
            if figure_data.get('description'):
                # Escape HTML in description
                description = figure_data['description'].replace('&', '&amp;')
                description = description.replace('<', '&lt;')
                description = description.replace('>', '&gt;')
                description = description.replace('\n', '<br/>')
                figure_text += f"<b>Description:</b><br/>{description}<br/><br/>"
            
            # Add personality prompt
            if figure_data.get('personality_prompt'):
                # Escape HTML in personality prompt
                personality = figure_data['personality_prompt'].replace('&', '&amp;')
                personality = personality.replace('<', '&lt;')
                personality = personality.replace('>', '&gt;')
                personality = personality.replace('\n', '<br/>')
                figure_text += f"<b>Personality:</b><br/>{personality}"
            
            if figure_text.strip():
                story.append(Paragraph("Historical Figure Information", figure_header_style))
                story.append(Paragraph(figure_text, figure_desc_style))
                story.append(Spacer(1, 0.3*inch))
        
        # Add settings section
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
        
        # Add separator line
        story.append(Paragraph("<b>Conversation:</b>", message_style))
        story.append(Spacer(1, 0.1*inch))
        
        # Add messages with simple format
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            # Escape HTML special characters and fix encoding issues
            content = content.replace('&', '&amp;')
            content = content.replace('<', '&lt;')
            content = content.replace('>', '&gt;')
            
            # Only replace specific problematic characters, preserve Unicode content
            # Don't replace characters that might be legitimate Unicode text (like Chinese)
            
            # Convert newlines to HTML line breaks
            content = content.replace('\n', '<br/>')
            
            # Use figure name for assistant messages
            if role == 'user':
                story.append(Paragraph(f"<b>User:</b> {content}", message_style))
            else:
                # Extract just the figure name without document count
                display_name = figure_name.split(' (')[0] if ' (' in figure_name else figure_name
                story.append(Paragraph(f"<b>{display_name}:</b> {content}", message_style))
            
            story.append(Spacer(1, 0.05*inch))
        
        # Add retrieved documents appendix if available
        if retrieved_documents and len(retrieved_documents) > 0:
            # Add page break before appendix
            from reportlab.platypus import PageBreak
            story.append(PageBreak())
            
            # Appendix title with Unicode font
            appendix_title_style = ParagraphStyle(
                'AppendixTitle',
                parent=styles['Title'],
                fontSize=16,
                fontName=unicode_font,
                textColor=colors.HexColor('#2c3e50'),
                spaceAfter=20,
                alignment=TA_CENTER
            )
            story.append(Paragraph("Appendix: Retrieved Documents", appendix_title_style))
            story.append(Spacer(1, 0.2*inch))
            
            # Document header style with Unicode font
            doc_header_style = ParagraphStyle(
                'DocHeader',
                parent=styles['Normal'],
                fontSize=12,
                fontName=unicode_font,
                textColor=colors.HexColor('#2c3e50'),
                spaceAfter=8,
                spaceBefore=12
            )
            
            # Document content style with Unicode font
            doc_content_style = ParagraphStyle(
                'DocContent',
                parent=styles['Normal'],
                fontSize=10,
                fontName=unicode_font,
                textColor=colors.HexColor('#34495e'),
                spaceAfter=10,
                leftIndent=12,
                rightIndent=12,
                leading=13
            )
            
            # Document metadata style with Unicode font
            doc_meta_style = ParagraphStyle(
                'DocMeta',
                parent=styles['Normal'],
                fontSize=9,
                fontName=unicode_font,
                textColor=colors.HexColor('#7f8c8d'),
                spaceAfter=15,
                leftIndent=12
            )
            
            # Sort documents by filename and chunk ID for better organization
            sorted_docs = sorted(retrieved_documents, key=lambda d: (
                d.get('filename', ''),
                d.get('chunk_id') or d.get('document_id') or d.get('doc_id', '')
            ))
            
            # Add each document
            for idx, doc_data in enumerate(sorted_docs, 1):
                filename = doc_data.get('filename', 'Unknown')
                chunk_id = doc_data.get('chunk_id') or doc_data.get('document_id') or doc_data.get('doc_id', 'unknown')
                text = doc_data.get('full_text') or doc_data.get('text', '')
                similarity = doc_data.get('similarity', 0)
                
                # Document header
                header_text = f"Document {idx}: {filename} (Chunk {chunk_id})"
                story.append(Paragraph(header_text, doc_header_style))
                
                # Document metadata
                meta_text = f"Relevance Score: {similarity:.2%}"
                if doc_data.get('timestamp'):
                    meta_text += f" | Retrieved: {doc_data['timestamp']}"
                story.append(Paragraph(meta_text, doc_meta_style))
                
                # Document content - escape and format
                content = text.replace('&', '&amp;')
                content = content.replace('<', '&lt;')
                content = content.replace('>', '&gt;')
                
                # Preserve Unicode content including Chinese characters
                # Don't replace characters that might be legitimate Unicode text
                
                # Preserve line breaks
                content = content.replace('\n', '<br/>')
                
                # Add content
                story.append(Paragraph(content, doc_content_style))
                
                # Add separator between documents
                if idx < len(sorted_docs):
                    story.append(Spacer(1, 0.1*inch))
                    # Add a subtle line separator
                    from reportlab.platypus import HRFlowable
                    story.append(HRFlowable(width="80%", thickness=0.5, 
                                           color=colors.HexColor('#e0e0e0'),
                                           spaceAfter=10, spaceBefore=10))
        
        # Build PDF
        doc.build(story)
        
        # Get PDF value
        pdf = buffer.getvalue()
        buffer.close()
        
        # Create response
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=chat_conversation.pdf'
        
        return response
        
    except Exception as e:
        logging.error(f"Error generating PDF: {e}")
        return jsonify({'error': str(e)}), 500

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    logging.info("Shutting down chat application...")
    sys.exit(0)

if __name__ == '__main__':
    # Session data will be managed per user
    # No need for global variables
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        app.run(debug=DEBUG_MODE, host='0.0.0.0', port=CHAT_PORT)
    except KeyboardInterrupt:
        logging.info("Chat application stopped by user")
    except Exception as e:
        logging.error(f"Chat application error: {e}")
    finally:
        logging.info("Chat application shutdown complete")
