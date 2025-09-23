from flask import Flask, render_template, request, jsonify, Response, make_response
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
from figure_manager import get_figure_manager
from config import OLLAMA_URL, DEFAULT_MODEL, MAX_CONTENT_LENGTH, MAX_CONTEXT_MESSAGES, CHAT_PORT, DEBUG_MODE

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['MAX_FORM_MEMORY_SIZE'] = None
logging.basicConfig(level=logging.WARNING)

conversation_history = []
current_figure = None

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

{f'Conversation history:' + chr(10) + conversation_context + chr(10) + chr(10) if conversation_context else ''}User's Current Question: {message}{thinking_instruction}

{response_start}Answer as {figure_name} would (no specific documents available for this query):"""
                else:
                    # No figure selected - no RAG available
                    # Get thinking instruction based on intensity
                    thinking_instruction, response_start = get_thinking_instructions(thinking_intensity)
                    
                    if conversation_context:
                        enhanced_prompt = f"""You are a helpful AI assistant. Here is the conversation history:

{conversation_context}

User's Current Question: {message}{thinking_instruction}

{response_start}Answer:"""
                    else:
                        enhanced_prompt = f"""You are a helpful AI assistant.

User's Question: {message}{thinking_instruction}

{response_start}Answer:"""
            except Exception as e:
                logging.error(f"Error in RAG enhancement: {e}")
                # Use conversation context only
                # Get thinking instruction based on intensity
                thinking_instruction, response_start = get_thinking_instructions(thinking_intensity)
                
                if conversation_context:
                    enhanced_prompt = f"""You are a helpful AI assistant. Here is the conversation history:

{conversation_context}

User's Current Question: {message}{thinking_instruction}

{response_start}Answer:"""
                else:
                    enhanced_prompt = f"""You are a helpful AI assistant.

User's Question: {message}{thinking_instruction}

{response_start}Answer:"""
        else:
            # RAG disabled - use conversation context only
            # Get thinking instruction based on intensity
            thinking_instruction, response_start = get_thinking_instructions(thinking_intensity)
            
            if conversation_context:
                enhanced_prompt = f"""You are a helpful AI assistant. Here is the conversation history:

{conversation_context}

User's Current Question: {message}{thinking_instruction}

{response_start}Answer:"""
            else:
                enhanced_prompt = f"""You are a helpful AI assistant.

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
                'current_figure': current_figure,
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
                return jsonify({
                    'figure_id': current_figure,
                    'figure_name': metadata.get('name', current_figure),
                    'description': metadata.get('description', ''),
                    'personality_prompt': metadata.get('personality_prompt', '')
                })
        
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
        model = data.get('model', 'Unknown')
        temperature = data.get('temperature', '1.0')
        thinking_enabled = data.get('thinking_enabled', False)
        rag_enabled = data.get('rag_enabled', True)
        
        # Create PDF in memory
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter,
                              rightMargin=72, leftMargin=72,
                              topMargin=72, bottomMargin=18)
        
        # Container for the 'Flowable' objects
        story = []
        
        # Define styles
        styles = getSampleStyleSheet()
        
        # Simple title style
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=18,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=20,
            alignment=TA_CENTER
        )
        
        # Settings style
        settings_style = ParagraphStyle(
            'Settings',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#7f8c8d'),
            spaceAfter=20,
            alignment=TA_LEFT
        )
        
        # Simple message style
        message_style = ParagraphStyle(
            'Message',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=12,
            alignment=TA_LEFT
        )
        
        # Add title
        story.append(Paragraph(title, title_style))
        
        # Add settings section
        settings_text = f"<b>Chat Settings:</b><br/>"
        settings_text += f"Date: {date}<br/>"
        settings_text += f"Figure: {figure_name}<br/>"
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
            
            # Escape HTML special characters
            content = content.replace('&', '&amp;')
            content = content.replace('<', '&lt;')
            content = content.replace('>', '&gt;')
            content = content.replace('\n', '<br/>')
            
            # Use figure name for assistant messages
            if role == 'user':
                story.append(Paragraph(f"<b>User:</b> {content}", message_style))
            else:
                # Extract just the figure name without document count
                display_name = figure_name.split(' (')[0] if ' (' in figure_name else figure_name
                story.append(Paragraph(f"<b>{display_name}:</b> {content}", message_style))
            
            story.append(Spacer(1, 0.05*inch))
        
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
