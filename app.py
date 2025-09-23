from flask import Flask, render_template, request, jsonify, Response, make_response, send_from_directory
import requests
import json
import logging
import os
import signal
import sys
import markdown
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
from config import OLLAMA_URL, DEFAULT_MODEL, MAX_CONTENT_LENGTH, MAX_CONTEXT_MESSAGES, CHAT_PORT, DEBUG_MODE, FIGURE_IMAGES_DIR

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['MAX_FORM_MEMORY_SIZE'] = None
logging.basicConfig(level=logging.WARNING)

conversation_history = []
current_figure = None

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

def add_to_conversation_history(role, content):
    """Add a message to conversation history"""
    global conversation_history
    
    # Clean thinking content from assistant messages
    if role == "assistant":
        content = clean_thinking_content(content)
    
    # Only add if content is not empty
    if content.strip():
        conversation_history.append({"role": role, "content": content})
        
        # Keep only recent messages
        if len(conversation_history) > MAX_CONTEXT_MESSAGES * 2:  # 2 messages per exchange
            conversation_history = conversation_history[-MAX_CONTEXT_MESSAGES * 2:]

def build_conversation_context():
    """Build conversation context string"""
    if not conversation_history:
        return ""
    
    context_parts = []
    for msg in conversation_history:
        if msg["role"] == "user":
            context_parts.append(f"User: {msg['content']}")
        else:
            context_parts.append(f"Assistant: {msg['content']}")
    
    return "\n".join(context_parts)

@app.route('/')
def index():
    """Serve the main chat interface - mobile optimized version"""
    # Use the new mobile-optimized template
    return render_template('index_mobile.html')

@app.route('/api/models')
def get_models():
    """Get list of available Ollama models"""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags")
        if response.status_code == 200:
            models = response.json().get('models', [])
            return jsonify([model['name'] for model in models])
        else:
            return jsonify([DEFAULT_MODEL])
    except Exception as e:
        logging.error(f"Error fetching models: {e}")
        return jsonify([DEFAULT_MODEL])

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat requests and stream responses from Ollama with RAG"""
    try:
        data = request.json
        message = data.get('message', '')
        model = data.get('model', DEFAULT_MODEL)
        use_rag = data.get('use_rag', True)  # Enable RAG by default
        k = data.get('k', 5)  # Number of documents to retrieve
        thinking_intensity = data.get('thinking_intensity', 'normal')  # Thinking intensity level
        temperature = data.get('temperature', 1.0)  # Temperature for response generation
        
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        
        # Build conversation context BEFORE adding current message
        conversation_context = build_conversation_context()
        
        # Add user message to conversation history AFTER building context
        add_to_conversation_history("user", message)
        
        # Enhance prompt with RAG if enabled
        enhanced_prompt = message
        search_results = None
        figure_context = ""
        
        if use_rag:
            try:
                global current_figure
                
                if current_figure:
                    # Use figure-specific RAG
                    figure_manager = get_figure_manager()
                    figure_metadata = figure_manager.get_figure_metadata(current_figure)
                    
                    if figure_metadata:
                        # Search in figure's documents
                        search_results = figure_manager.search_figure_documents(current_figure, message, n_results=k)
                        
                        if search_results:
                            # Build context from figure's documents
                            context_parts = []
                            for result in search_results:
                                doc_id = result.get('document_id', 'UNKNOWN')
                                filename = result['metadata'].get('filename', 'Unknown')
                                context_parts.append(f"[{filename}]:\n{result['text']}")
                            
                            rag_context = "\n\n".join(context_parts)
                            
                            # Get personality prompt if available
                            personality_prompt = figure_metadata.get('personality_prompt', '')
                            figure_name = figure_metadata.get('name', current_figure)
                            
                            # Create figure-specific prompt
                            base_instruction = f"You are responding as {figure_name}." if not personality_prompt else personality_prompt
                            
                            # Get thinking instruction based on intensity
                            thinking_instruction, response_start = get_thinking_instructions(thinking_intensity)
                            
                            enhanced_prompt = f"""{base_instruction}

IMPORTANT: Please respond in the same language that the user is using. If the user writes in English, respond in English. If the user writes in Chinese, respond in Chinese, etc.

Based on the following context from your writings and documents, please answer the user's current question in character:

Your Documents:
{rag_context}

{f'Conversation history:' + chr(10) + conversation_context + chr(10) if conversation_context else ''}User's Current Question: {message}{thinking_instruction}

{response_start}Answer as {figure_name} would, drawing from the provided documents:"""
                        else:
                            # No relevant documents found for figure
                            figure_name = figure_metadata.get('name', current_figure)
                            personality_prompt = figure_metadata.get('personality_prompt', '')
                            base_instruction = f"You are responding as {figure_name}." if not personality_prompt else personality_prompt
                            
                            # Get thinking instruction based on intensity
                            thinking_instruction, response_start = get_thinking_instructions(thinking_intensity)
                            
                            enhanced_prompt = f"""{base_instruction}

IMPORTANT: Please respond in the same language that the user is using. If the user writes in English, respond in English. If the user writes in Chinese, respond in Chinese, etc.

{f'Conversation history:' + chr(10) + conversation_context + chr(10) + chr(10) if conversation_context else ''}User's Current Question: {message}{thinking_instruction}

{response_start}Answer as {figure_name} would (no specific documents available for this query):"""
                else:
                    # No figure selected - no RAG available
                    # Get thinking instruction based on intensity
                    thinking_instruction, response_start = get_thinking_instructions(thinking_intensity)
                    
                    if conversation_context:
                        enhanced_prompt = f"""You are a helpful AI assistant.

IMPORTANT: Please respond in the same language that the user is using. If the user writes in English, respond in English. If the user writes in Chinese, respond in Chinese, etc.

Here is the conversation history:

{conversation_context}

User's Current Question: {message}{thinking_instruction}

{response_start}Answer:"""
                    else:
                        enhanced_prompt = f"""You are a helpful AI assistant.

IMPORTANT: Please respond in the same language that the user is using. If the user writes in English, respond in English. If the user writes in Chinese, respond in Chinese, etc.

User's Question: {message}{thinking_instruction}

{response_start}Answer:"""
            except Exception as e:
                logging.error(f"Error in RAG enhancement: {e}")
                # Use conversation context only
                # Get thinking instruction based on intensity
                thinking_instruction, response_start = get_thinking_instructions(thinking_intensity)
                
                if conversation_context:
                    enhanced_prompt = f"""You are a helpful AI assistant.

IMPORTANT: Please respond in the same language that the user is using. If the user writes in English, respond in English. If the user writes in Chinese, respond in Chinese, etc.

Here is the conversation history:

{conversation_context}

User's Current Question: {message}{thinking_instruction}

{response_start}Answer:"""
                else:
                    enhanced_prompt = f"""You are a helpful AI assistant.

IMPORTANT: Please respond in the same language that the user is using. If the user writes in English, respond in English. If the user writes in Chinese, respond in Chinese, etc.

User's Question: {message}{thinking_instruction}

{response_start}Answer:"""
        else:
            # RAG disabled - use conversation context only
            # Get thinking instruction based on intensity
            thinking_instruction, response_start = get_thinking_instructions(thinking_intensity)
            
            if conversation_context:
                enhanced_prompt = f"""You are a helpful AI assistant.

IMPORTANT: Please respond in the same language that the user is using. If the user writes in English, respond in English. If the user writes in Chinese, respond in Chinese, etc.

Here is the conversation history:

{conversation_context}

User's Current Question: {message}{thinking_instruction}

{response_start}Answer:"""
            else:
                enhanced_prompt = f"""You are a helpful AI assistant.

IMPORTANT: Please respond in the same language that the user is using. If the user writes in English, respond in English. If the user writes in Chinese, respond in Chinese, etc.

User's Question: {message}{thinking_instruction}

{response_start}Answer:"""
        
        # Prepare request for Ollama
        ollama_request = {
            "model": model,
            "prompt": enhanced_prompt,
            "stream": True,
            "options": {
                "temperature": temperature
            }
        }
        
        def generate():
            try:
                response = requests.post(
                    f"{OLLAMA_URL}/api/generate",
                    json=ollama_request,
                    stream=True
                )
                
                if response.status_code != 200:
                    yield f"data: {json.dumps({'error': 'Ollama server error'})}\n\n"
                    return
                
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
                
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk_data = json.loads(line.decode('utf-8'))
                            if 'response' in chunk_data:
                                content = chunk_data['response']
                                full_response += content
                                yield f"data: {json.dumps({'content': content})}\n\n"
                            if chunk_data.get('done', False):
                                # Add assistant response to conversation history
                                add_to_conversation_history("assistant", full_response)
                                yield f"data: {json.dumps({'done': True})}\n\n"
                                break
                        except json.JSONDecodeError:
                            continue
                            
            except Exception as e:
                logging.error(f"Error in chat stream: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return Response(generate(), mimetype='text/event-stream')
        
    except Exception as e:
        logging.error(f"Error in chat endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """Check if Ollama is running"""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            return jsonify({'status': 'healthy', 'ollama': 'connected'})
        else:
            return jsonify({'status': 'unhealthy', 'ollama': 'error'}), 503
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'ollama': 'disconnected', 'error': str(e)}), 503

@app.route('/api/rag/stats')
def rag_stats():
    """Get RAG database statistics - now only shows figure-specific stats"""
    try:
        global current_figure
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
        global current_figure
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
        debug_info = {
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
        global current_figure, conversation_history
        
        data = request.json
        figure_id = data.get('figure_id')
        
        if figure_id:
            figure_manager = get_figure_manager()
            metadata = figure_manager.get_figure_metadata(figure_id)
            if not metadata:
                return jsonify({'error': 'Figure not found'}), 404
            
            current_figure = figure_id
            # Clear conversation history when switching figures
            conversation_history = []
            
            return jsonify({
                'success': True,
                'current_figure': metadata,  # Return full metadata instead of just ID
                'figure_name': metadata.get('name', figure_id)
            })
        else:
            # Deselect figure (use general RAG)
            current_figure = None
            conversation_history = []
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
    """Get currently selected figure"""
    try:
        global current_figure
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
        return send_from_directory(FIGURE_IMAGES_DIR, filename)
    except Exception as e:
        logging.error(f"Error serving figure image {filename}: {str(e)}")
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
