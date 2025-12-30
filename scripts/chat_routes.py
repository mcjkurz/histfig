"""
Chat Routes - FastAPI Router
Handles chat interface and conversation functionality with async support.
"""

import re
import json
import logging
import os
import markdown
import secrets
import uuid
import datetime
import asyncio
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse, Response, RedirectResponse
from figure_manager import get_figure_manager
from config import (
    DEFAULT_LOCAL_MODEL, DEFAULT_EXTERNAL_MODEL, MAX_CONTEXT_MESSAGES,
    FIGURE_IMAGES_DIR, EXTERNAL_API_KEY, EXTERNAL_API_URL, LOCAL_API_URL,
    RAG_ENABLED, QUERY_AUGMENTATION_ENABLED, QUERY_AUGMENTATION_MODEL,
    LOCAL_MODELS, EXTERNAL_MODELS, DOCS_TO_RETRIEVE
)
from search_utils import format_search_result_for_response
from model_provider import LLMProvider
from query_augmentation import augment_query
from pdf_export import generate_conversation_pdf
from prompts import (
    FIGURE_SYSTEM_PROMPT, DEFAULT_FIGURE_INSTRUCTION,
    USER_MESSAGE_WITH_RAG, USER_MESSAGE_NO_RAG, GENERIC_ASSISTANT_PROMPT,
    get_thinking_instructions
)

# Create FastAPI router
chat_router = APIRouter(tags=["chat"])

# Store conversation history per session (async-safe with asyncio.Lock)
session_data: Dict[str, Dict[str, Any]] = {}
session_lock = asyncio.Lock()

# Session cleanup configuration
SESSION_TIMEOUT_SECONDS = 24 * 60 * 60  # 24 hours
CLEANUP_INTERVAL_SECONDS = 60 * 60  # Run cleanup every hour
_cleanup_task: Optional[asyncio.Task] = None

# Rate limiting configuration
RATE_LIMIT_MAX_REQUESTS = 3  # Maximum requests allowed
RATE_LIMIT_WINDOW_SECONDS = 20  # Time window in seconds
rate_limit_data: Dict[str, List[float]] = {}  # session_id -> list of timestamps
rate_limit_lock = asyncio.Lock()


async def check_rate_limit(session_id: str) -> tuple[bool, str]:
    """
    Check if the session has exceeded rate limit.
    Returns (is_allowed, message) tuple.
    """
    now = datetime.datetime.now().timestamp()
    
    async with rate_limit_lock:
        if session_id not in rate_limit_data:
            rate_limit_data[session_id] = []
        
        # Remove timestamps outside the window
        timestamps = rate_limit_data[session_id]
        cutoff = now - RATE_LIMIT_WINDOW_SECONDS
        rate_limit_data[session_id] = [ts for ts in timestamps if ts > cutoff]
        
        # Check if limit exceeded
        if len(rate_limit_data[session_id]) >= RATE_LIMIT_MAX_REQUESTS:
            oldest = min(rate_limit_data[session_id])
            wait_time = int(oldest + RATE_LIMIT_WINDOW_SECONDS - now) + 1
            return False, f"Rate limit exceeded. Please wait {wait_time} seconds before sending another message."
        
        # Record this request
        rate_limit_data[session_id].append(now)
        return True, ""


async def cleanup_rate_limit_data():
    """Clean up old rate limit data for inactive sessions."""
    now = datetime.datetime.now().timestamp()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS * 10  # Keep data for 10x the window
    
    async with rate_limit_lock:
        sessions_to_remove = []
        for session_id, timestamps in rate_limit_data.items():
            if not timestamps or max(timestamps) < cutoff:
                sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            del rate_limit_data[session_id]
        
        if sessions_to_remove:
            logging.debug(f"Cleaned up rate limit data for {len(sessions_to_remove)} sessions")


# Pydantic models for request validation
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    model: str = Field(..., min_length=1, description="Model to use")
    use_rag: bool = Field(default=True, description="Whether to use RAG")
    k: int = Field(default=5, ge=0, le=50, description="Number of documents to retrieve")
    thinking_intensity: str = Field(default="normal", description="Thinking intensity")
    temperature: float = Field(default=1.0, ge=0.0, le=2.0, description="Temperature")
    external_config: Optional[Dict[str, Any]] = Field(default=None, description="External API config")
    query_augmentation: bool = Field(default=True, description="Whether to use query augmentation")


class SelectFigureRequest(BaseModel):
    figure_id: Optional[str] = Field(default=None, description="Figure ID to select")


class MarkdownRequest(BaseModel):
    text: str = Field(default="", description="Markdown text to convert")


class PDFExportRequest(BaseModel):
    title: str = Field(default="Chat Conversation")
    date: str = Field(default="")
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    figure: str = Field(default="General Chat")
    figure_name: str = Field(default="")
    figure_data: Optional[Dict[str, Any]] = Field(default=None)
    document_count: str = Field(default="0")
    model: str = Field(default="Unknown")
    temperature: str = Field(default="1.0")
    thinking_enabled: bool = Field(default=False)
    rag_enabled: bool = Field(default=True)


def clean_thinking_content(text):
    """Remove thinking tags and content from text"""
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return cleaned.strip()


def get_session_id(request: Request) -> str:
    """Get session ID from request header or session"""
    session_id = request.headers.get('X-Session-ID')
    if not session_id:
        session = request.session
        if 'session_id' not in session:
            session['session_id'] = secrets.token_hex(16)
        return session['session_id']
    return session_id


async def _get_or_create_session(session_id: str) -> Dict[str, Any]:
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
        session_data[session_id]['last_activity'] = now
    return session_data[session_id]


async def get_session_data(request: Request) -> Dict[str, Any]:
    """Get session data for current user. Updates last activity time."""
    session_id = get_session_id(request)
    async with session_lock:
        return await _get_or_create_session(session_id)


async def cleanup_expired_sessions():
    """Remove sessions that have been inactive for more than 24 hours"""
    now = datetime.datetime.now()
    expired_sessions = []
    
    async with session_lock:
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


async def _session_cleanup_loop():
    """Background task that periodically cleans up expired sessions and rate limit data"""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            await cleanup_expired_sessions()
            await cleanup_rate_limit_data()
        except Exception as e:
            logging.error(f"Error in session cleanup: {e}")


async def start_session_cleanup_task():
    """Start the background session cleanup task (if not already running)"""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_session_cleanup_loop())
        logging.info("Session cleanup task started (24h timeout, hourly cleanup)")


def save_conversation_to_json(user_session: Dict, session_id: str):
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


async def add_to_conversation_history(request: Request, role: str, content: str, retrieved_documents=None):
    """Add a message to conversation history for current session (async-safe)"""
    if role == "assistant":
        content = clean_thinking_content(content)
    
    if not content.strip():
        return
    
    session_id = get_session_id(request)
    async with session_lock:
        user_session = await _get_or_create_session(session_id)
        conversation_history = user_session['conversation_history']
        
        message = {"role": role, "content": content}
        
        if role == "assistant" and retrieved_documents:
            message["retrieved_documents"] = retrieved_documents
        
        conversation_history.append(message)
        
        if len(conversation_history) > MAX_CONTEXT_MESSAGES * 2:
            user_session['conversation_history'] = conversation_history[-MAX_CONTEXT_MESSAGES * 2:]
        
        save_conversation_to_json(user_session, session_id)


async def build_conversation_messages(request: Request) -> List[Dict[str, str]]:
    """Build conversation messages list for current session"""
    user_session = await get_session_data(request)
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


def truncate_messages_preserve_system(messages: List[Dict], system_message: Optional[Dict] = None) -> List[Dict]:
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

@chat_router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main chat interface"""
    templates = request.app.state.templates
    return templates.TemplateResponse("index.html", {"request": request})


@chat_router.get("/favicon.ico")
async def favicon():
    """Serve favicon from static folder"""
    from pathlib import Path
    static_path = Path(__file__).parent.parent / "static" / "favicon.ico"
    return FileResponse(str(static_path), media_type='image/vnd.microsoft.icon')


@chat_router.get("/api/models-by-source")
async def get_models_by_source():
    """Get model lists for both local and external sources"""
    try:
        local_models = []
        if LOCAL_MODELS:
            local_models = LOCAL_MODELS
        else:
            try:
                provider = LLMProvider(base_url=LOCAL_API_URL, api_key=None)
                models = await provider.get_available_models()
                local_models = models if models else []
            except Exception as e:
                logging.warning(f"Could not fetch local models: {e}")
                local_models = [DEFAULT_LOCAL_MODEL] if DEFAULT_LOCAL_MODEL else []
        
        external_models = EXTERNAL_MODELS if EXTERNAL_MODELS else None
        
        return {"local": local_models, "external": external_models}
    except Exception as e:
        logging.error(f"Error fetching models by source: {e}")
        return {"local": [], "external": None}


@chat_router.get("/api/external-api-key-status")
async def get_external_api_key_status():
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
        
        return {"has_key": has_key, "masked_key": masked_key}
    except Exception as e:
        logging.error(f"Error checking LLM API key status: {e}")
        return {"has_key": False, "masked_key": ""}


@chat_router.get("/api/feature-flags")
async def get_feature_flags():
    """Get feature flags from server config"""
    return {
        "rag_enabled": RAG_ENABLED,
        "query_augmentation_enabled": QUERY_AUGMENTATION_ENABLED,
        "query_augmentation_model": QUERY_AUGMENTATION_MODEL,
        "docs_to_retrieve": DOCS_TO_RETRIEVE
    }


@chat_router.post("/api/chat")
async def chat(request: Request, chat_request: ChatRequest):
    """Handle chat requests and stream responses using messages format"""
    # Check rate limit first
    session_id = get_session_id(request)
    is_allowed, rate_limit_msg = await check_rate_limit(session_id)
    if not is_allowed:
        raise HTTPException(status_code=429, detail=rate_limit_msg)
    
    try:
        message = chat_request.message
        model = chat_request.model
        use_rag = chat_request.use_rag
        k = chat_request.k
        thinking_intensity = chat_request.thinking_intensity
        temperature = chat_request.temperature
        external_config = chat_request.external_config
        use_query_augmentation = chat_request.query_augmentation
        
        conversation_messages = await build_conversation_messages(request)
        await add_to_conversation_history(request, "user", message)
        
        messages = []
        search_results = None
        system_content = ""
        user_content = message
        augmented_query = None
        
        user_session = await get_session_data(request)
        current_figure = user_session.get('current_figure')
        figure_manager = get_figure_manager() if current_figure else None
        figure_metadata = await asyncio.to_thread(
            figure_manager.get_figure_metadata, current_figure
        ) if figure_manager and current_figure else None
        figure_name = figure_metadata.get('name', current_figure) if figure_metadata else None
        
        if QUERY_AUGMENTATION_ENABLED and use_query_augmentation and use_rag and k > 0:
            try:
                augmented_query = await augment_query(message, figure_name=figure_name or "a historical figure")
            except Exception as e:
                logging.warning(f"Query augmentation failed: {e}")
                augmented_query = None
        
        thinking_instruction, response_start = get_thinking_instructions(thinking_intensity)
        
        if use_rag:
            try:
                if current_figure and figure_metadata:
                    search_query = augmented_query if augmented_query else message
                    search_results = await figure_manager.search_figure_documents_async(
                        current_figure, search_query, n_results=k
                    )
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
        
        session_id = get_session_id(request)
        
        async def generate():
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
                
                if augmented_query and augmented_query != message:
                    yield f"data: {json.dumps({'augmented_query': augmented_query})}\n\n"
                
                if use_rag and search_results:
                    sources_data = [format_search_result_for_response(r, current_figure) for r in search_results]
                    yield f"data: {json.dumps({'sources': sources_data})}\n\n"
                
                full_response = ""
                
                async for chunk in provider.chat_stream(messages, model_to_use, temperature):
                    if 'error' in chunk:
                        yield f"data: {json.dumps({'error': chunk['error']})}\n\n"
                        break
                    
                    if 'content' in chunk:
                        content = chunk['content']
                        full_response += content
                        yield f"data: {json.dumps({'content': content})}\n\n"
                    
                    if chunk.get('done', False):
                        async with session_lock:
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
        
        return StreamingResponse(generate(), media_type='text/event-stream')
        
    except Exception as e:
        logging.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.get("/api/health")
async def health_check():
    """Check if both local and external model providers are accessible"""
    try:
        external_provider = LLMProvider(base_url=EXTERNAL_API_URL, api_key=EXTERNAL_API_KEY)
        external_models = await external_provider.get_available_models()
        
        local_provider = LLMProvider(base_url=LOCAL_API_URL, api_key=None)
        local_models = await local_provider.get_available_models()
        
        return {
            'status': 'healthy' if (external_models or local_models) else 'unhealthy',
            'external_api_url': EXTERNAL_API_URL,
            'external_connected': bool(external_models),
            'external_models_available': len(external_models) if external_models else 0,
            'local_api_url': LOCAL_API_URL,
            'local_connected': bool(local_models),
            'local_models_available': len(local_models) if local_models else 0
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                'status': 'unhealthy', 
                'api_url': EXTERNAL_API_URL,
                'connected': False,
                'error': str(e)
            }
        )


@chat_router.get("/api/rag/stats")
async def rag_stats(request: Request):
    """Get RAG database statistics"""
    try:
        user_session = await get_session_data(request)
        current_figure = user_session['current_figure']
        if current_figure:
            figure_manager = get_figure_manager()
            stats = await figure_manager.get_figure_stats_async(current_figure)
            return stats
        else:
            raise HTTPException(status_code=404, detail="No figure selected")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting RAG stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.get("/api/figures")
async def get_figures():
    """Get list of available historical figures"""
    try:
        figure_manager = get_figure_manager()
        figures = await figure_manager.get_figure_list_async()
        return figures
    except Exception as e:
        logging.error(f"Error getting figures: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.get("/api/figure/{figure_id}")
async def get_figure_details(figure_id: str):
    """Get details for a specific figure"""
    try:
        figure_manager = get_figure_manager()
        metadata = await figure_manager.get_figure_metadata_async(figure_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="Figure not found")
        
        stats = await figure_manager.get_figure_stats_async(figure_id)
        return {**metadata, **stats}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting figure details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.post("/api/figure/select")
async def select_figure(request: Request, data: SelectFigureRequest):
    """Select a figure for the current chat session (async-safe)"""
    try:
        figure_id = data.figure_id
        session_id = get_session_id(request)
        
        if figure_id:
            figure_manager = get_figure_manager()
            metadata = await figure_manager.get_figure_metadata_async(figure_id)
            if not metadata:
                raise HTTPException(status_code=404, detail="Figure not found")
            
            async with session_lock:
                user_session = await _get_or_create_session(session_id)
                user_session['current_figure'] = figure_id
                user_session['conversation_history'] = []
            
            return {
                'success': True,
                'current_figure': metadata,
                'figure_name': metadata.get('name', figure_id)
            }
        else:
            async with session_lock:
                user_session = await _get_or_create_session(session_id)
                user_session['current_figure'] = None
                user_session['conversation_history'] = []
            
            return {
                'success': True,
                'current_figure': None,
                'figure_name': None
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error selecting figure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.get("/api/figure/current")
async def get_current_figure(request: Request):
    """Get currently selected figure for current session"""
    try:
        user_session = await get_session_data(request)
        current_figure = user_session['current_figure']
        if current_figure:
            figure_manager = get_figure_manager()
            metadata = await figure_manager.get_figure_metadata_async(current_figure)
            if metadata:
                return metadata
        
        return {'figure_id': None, 'figure_name': None}
    except Exception as e:
        logging.error(f"Error getting current figure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.post("/api/markdown")
async def convert_markdown(data: MarkdownRequest):
    """Convert markdown text to HTML"""
    try:
        text = data.text
        
        if not text.strip():
            return {'html': ''}
        
        html_content = markdown.markdown(text, output_format='html5')
        
        if html_content.startswith('<p>') and html_content.endswith('</p>'):
            html_content = html_content[3:-4]
        
        return {'html': html_content}
    except Exception as e:
        logging.error(f"Error converting markdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.get("/figure_images/{filename}", name="chat.figure_image")
async def figure_image(filename: str):
    """Serve figure images."""
    from image_utils import serve_figure_image
    return await serve_figure_image(filename)


@chat_router.post("/api/export/pdf")
async def export_conversation_pdf(data: PDFExportRequest):
    """Export conversation as PDF"""
    try:
        pdf_bytes = await asyncio.to_thread(generate_conversation_pdf, data.model_dump())
        
        return Response(
            content=pdf_bytes,
            media_type='application/pdf',
            headers={'Content-Disposition': 'attachment; filename=chat_conversation.pdf'}
        )
        
    except Exception as e:
        logging.error(f"Error generating PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))
