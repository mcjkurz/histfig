"""
Model Provider - Unified OpenAI-compatible API client
Works with local Ollama (/v1 endpoint) or any OpenAI-compatible external API.
"""

import requests
import json
import logging
from typing import List, Dict, Generator, Optional
from config import LLM_API_URL, LLM_API_KEY, LLM_PROVIDER


class LLMProvider:
    """Unified OpenAI-compatible LLM provider"""
    
    def __init__(self, base_url: str = None, api_key: str = None, model: str = None):
        self.base_url = (base_url or LLM_API_URL).rstrip('/')
        self.api_key = api_key or LLM_API_KEY
        self.default_model = model
        
    def chat_stream(self, messages: List[Dict], model: str, temperature: float) -> Generator:
        """Stream chat responses using OpenAI-compatible API"""
        model_to_use = model or self.default_model
        if not model_to_use:
            yield {"error": "Model name not specified. Please provide a model name."}
            return
        
        # Build headers
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": model_to_use,
                    "messages": messages,
                    "stream": True,
                    "temperature": temperature
                },
                stream=True
            )
            
            if response.status_code != 200:
                error_msg = self._parse_error(response)
                yield {"error": error_msg}
                return
                
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]
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
                            
        except requests.exceptions.ConnectionError as e:
            logging.error(f"Connection error: {e}")
            yield {"error": f"Cannot connect to LLM API at {self.base_url}. Check the URL and your connection."}
        except requests.exceptions.Timeout as e:
            logging.error(f"Timeout error: {e}")
            yield {"error": "LLM API request timed out. Please try again."}
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error: {e}")
            yield {"error": f"LLM API request failed: {str(e)}"}
        except Exception as e:
            logging.error(f"Unexpected error in LLM stream: {e}")
            yield {"error": f"Unexpected error: {str(e)}"}
    
    def _parse_error(self, response) -> str:
        """Parse error response into user-friendly message"""
        status = response.status_code
        
        # Try to get error details from JSON
        try:
            error_data = response.json()
            if 'error' in error_data:
                error_detail = error_data['error']
                if isinstance(error_detail, dict):
                    return error_detail.get('message', str(error_detail))
                return str(error_detail)
        except Exception:
            pass
        
        # Standard HTTP error messages
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
    
    def get_available_models(self) -> List[str]:
        """Fetch available models from the API"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        try:
            response = requests.get(f"{self.base_url}/models", headers=headers)
            if response.status_code == 200:
                data = response.json()
                models = data.get('data', [])
                return [m.get('id', m.get('name', '')) for m in models if m]
        except Exception as e:
            logging.error(f"Error fetching models: {e}")
        
        return [self.default_model] if self.default_model else []


def get_model_provider(provider_name: Optional[str] = None) -> LLMProvider:
    """Factory function to get the LLM provider"""
    # Provider name is now just for logging/info, we always use unified LLMProvider
    provider = provider_name or LLM_PROVIDER
    logging.debug(f"Creating LLM provider (mode: {provider})")
    return LLMProvider()


# Backwards compatibility alias
ExternalProvider = LLMProvider
