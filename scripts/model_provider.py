"""
Model Provider - Unified OpenAI-compatible API client
Works with local Ollama (/v1 endpoint) or any OpenAI-compatible external API.
Uses async httpx for non-blocking HTTP requests.
"""

import httpx
import json
import logging
from typing import List, Dict, AsyncGenerator
from config import EXTERNAL_API_URL, EXTERNAL_API_KEY


class LLMProvider:
    """Unified OpenAI-compatible LLM provider with async support"""
    
    def __init__(self, base_url: str = None, api_key: str = None, model: str = None):
        self.base_url = (base_url or EXTERNAL_API_URL).rstrip('/')
        self.api_key = api_key or EXTERNAL_API_KEY
        self.default_model = model
        
    async def chat_stream(self, messages: List[Dict], model: str, temperature: float) -> AsyncGenerator:
        """Stream chat responses using OpenAI-compatible API"""
        model_to_use = model or self.default_model
        if not model_to_use:
            yield {"error": "Model name not specified. Please provide a model name."}
            return
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": model_to_use,
                        "messages": messages,
                        "stream": True,
                        "temperature": temperature
                    }
                ) as response:
                    if response.status_code != 200:
                        error_msg = await self._parse_error_async(response)
                        yield {"error": error_msg}
                        return
                    
                    async for line in response.aiter_lines():
                        if line:
                            if line.startswith('data: '):
                                data_str = line[6:]
                                if data_str == '[DONE]':
                                    yield {"done": True}
                                    break
                                try:
                                    chunk_data = json.loads(data_str)
                                    if 'choices' in chunk_data:
                                        delta = chunk_data['choices'][0].get('delta', {})
                                        content = delta.get('content', '')
                                        if content:
                                            yield {"content": content}
                                except json.JSONDecodeError:
                                    continue
                            
        except httpx.ConnectError as e:
            logging.error(f"Connection error: {e}")
            yield {"error": f"Cannot connect to LLM API at {self.base_url}. Check the URL and your connection."}
        except httpx.TimeoutException as e:
            logging.error(f"Timeout error: {e}")
            yield {"error": "LLM API request timed out. Please try again."}
        except httpx.RequestError as e:
            logging.error(f"Request error: {e}")
            yield {"error": f"LLM API request failed: {str(e)}"}
        except Exception as e:
            logging.error(f"Unexpected error in LLM stream: {e}")
            yield {"error": f"Unexpected error: {str(e)}"}
    
    async def _parse_error_async(self, response: httpx.Response) -> str:
        """Parse error response into user-friendly message"""
        status = response.status_code
        
        try:
            content = await response.aread()
            error_data = json.loads(content)
            if 'error' in error_data:
                error_detail = error_data['error']
                if isinstance(error_detail, dict):
                    return error_detail.get('message', str(error_detail))
                return str(error_detail)
        except Exception:
            pass
        
        if status == 401:
            return "Invalid API key. Please check your API key."
        elif status == 403:
            return "API key access forbidden. Check your permissions."
        elif status == 429:
            return "Rate limit exceeded. Please try again later."
        elif status == 404:
            return f"API endpoint not found at {self.base_url}. Check the URL."
        else:
            return f"LLM API error: HTTP {status}"
    
    async def get_available_models(self) -> List[str]:
        """Fetch available models from the API"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/models", headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    models = data.get('data', [])
                    return [m.get('id', m.get('name', '')) for m in models if m]
        except Exception as e:
            logging.error(f"Error fetching models: {e}")
        
        return [self.default_model] if self.default_model else []
