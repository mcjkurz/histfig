"""
PDF Export Module
Handles PDF generation for conversation exports.
"""

import os
import logging
import platform
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def register_unicode_fonts():
    """Register Unicode-capable fonts for PDF generation"""
    try:
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


def _create_pdf_styles(unicode_font):
    """Create all PDF styles used in conversation export"""
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
    
    return {
        'title': title_style,
        'settings': settings_style,
        'message': message_style,
        'figure_desc': figure_desc_style,
        'figure_header': figure_header_style,
        'doc_header': doc_header_style,
        'doc_content': doc_content_style,
        'doc_meta': doc_meta_style,
        'doc_section_header': doc_section_header_style,
    }


def _escape_html(text):
    """Escape special characters for PDF/HTML rendering"""
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('\n', '<br/>')
    return text


def generate_conversation_pdf(data):
    """
    Generate a PDF from conversation data.
    
    Args:
        data: Dictionary containing conversation data with keys:
            - title, date, messages, figure, figure_name, figure_data
            - document_count, model, temperature, thinking_enabled, rag_enabled
    
    Returns:
        bytes: PDF content as bytes
    """
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
    
    unicode_font = register_unicode_fonts()
    pdf_styles = _create_pdf_styles(unicode_font)
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                          rightMargin=72, leftMargin=72,
                          topMargin=72, bottomMargin=18)
    
    story = []
    
    # Title
    story.append(Paragraph(title, pdf_styles['title']))
    
    # Figure information section
    if figure_data and figure != 'General Chat':
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
            description = _escape_html(figure_data['description'])
            figure_text += f"<b>Description:</b><br/>{description}<br/><br/>"
        
        if figure_data.get('personality_prompt'):
            personality = _escape_html(figure_data['personality_prompt'])
            figure_text += f"<b>Personality:</b><br/>{personality}"
        
        if figure_text.strip():
            story.append(Paragraph("Historical Figure Information", pdf_styles['figure_header']))
            story.append(Paragraph(figure_text, pdf_styles['figure_desc']))
            story.append(Spacer(1, 0.3*inch))
    
    # Settings section
    settings_text = f"<b>Chat Settings:</b><br/>"
    settings_text += f"Date: {date}<br/>"
    settings_text += f"Figure: {figure_name}<br/>"
    settings_text += f"Documents: {document_count}<br/>"
    settings_text += f"Model: {model}<br/>"
    settings_text += f"Temperature: {temperature}<br/>"
    settings_text += f"Thinking Mode: {'Enabled' if thinking_enabled else 'Disabled'}<br/>"
    settings_text += f"RAG Mode: {'Enabled' if rag_enabled else 'Disabled'}"
    story.append(Paragraph(settings_text, pdf_styles['settings']))
    story.append(Spacer(1, 0.3*inch))
    
    # Conversation section
    story.append(Paragraph("<b>Conversation:</b>", pdf_styles['message']))
    story.append(Spacer(1, 0.1*inch))
    
    for msg in messages:
        role = msg.get('role', 'unknown')
        content = _escape_html(msg.get('content', ''))
        msg_retrieved_documents = msg.get('retrieved_documents', [])
        
        if role == 'user':
            story.append(Paragraph(f"<b>User:</b> {content}", pdf_styles['message']))
        else:
            display_name = figure_name.split(' (')[0] if ' (' in figure_name else figure_name
            story.append(Paragraph(f"<b>{display_name}:</b> {content}", pdf_styles['message']))
            
            # Add retrieved documents for this message
            if msg_retrieved_documents and len(msg_retrieved_documents) > 0:
                story.append(Spacer(1, 0.05*inch))
                story.append(Paragraph(
                    f"<b>Retrieved Documents ({len(msg_retrieved_documents)}):</b>",
                    pdf_styles['doc_section_header']
                ))
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
                    story.append(Paragraph(header_text, pdf_styles['doc_header']))
                    
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
                    story.append(Paragraph(meta_text, pdf_styles['doc_meta']))
                    
                    doc_content = _escape_html(text)
                    story.append(Paragraph(doc_content, pdf_styles['doc_content']))
                    
                    if idx < len(sorted_docs):
                        story.append(Spacer(1, 0.05*inch))
                        story.append(HRFlowable(
                            width="80%", thickness=0.5,
                            color=colors.HexColor('#e0e0e0'),
                            spaceAfter=3, spaceBefore=3
                        ))
        
        story.append(Spacer(1, 0.1*inch))
    
    doc.build(story)
    
    pdf = buffer.getvalue()
    buffer.close()
    
    return pdf

