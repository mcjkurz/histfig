"""
Model Provider Abstraction Layer
Handles communication with different LLM providers (Ollama, OpenAI, Anthropic)
"""

import requests
import json
import logging
from typing import List, Dict, Generator, Optional
from abc import ABC, abstractmethod
from config import OLLAMA_URL, MODEL_PROVIDER


class ModelProvider(ABC):
    """Abstract base class for model providers"""
    
    @abstractmethod
    def chat_stream(self, messages: List[Dict], model: str, temperature: float) -> Generator:
        """Stream chat responses from the model"""
        pass
    
    @abstractmethod
    def get_available_models(self) -> List[str]:
        """Get list of available models"""
        pass


class OllamaProvider(ModelProvider):
    """Ollama provider using OpenAI-compatible endpoint"""
    
    def __init__(self):
        self.base_url = OLLAMA_URL
        
    def chat_stream(self, messages: List[Dict], model: str, temperature: float) -> Generator:
        """Stream chat responses from Ollama"""
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": temperature
                    }
                },
                stream=True
            )
            
            if response.status_code != 200:
                yield {"error": f"Ollama server error: {response.status_code}"}
                return
                
            for line in response.iter_lines():
                if line:
                    try:
                        chunk_data = json.loads(line.decode('utf-8'))
                        if 'message' in chunk_data:
                            # Ollama format: {"message": {"content": "..."}}
                            content = chunk_data['message'].get('content', '')
                            if content:
                                yield {"content": content}
                        if chunk_data.get('done', False):
                            yield {"done": True}
                            break
                    except json.JSONDecodeError:
                        continue
                        
        except Exception as e:
            logging.error(f"Error in Ollama stream: {e}")
            yield {"error": str(e)}
    
    def get_available_models(self) -> List[str]:
        """Get list of available Ollama models"""
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                models = response.json().get('models', [])
                return [model['name'] for model in models]
        except Exception as e:
            logging.error(f"Error fetching Ollama models: {e}")
        return []


class ExternalProvider(ModelProvider):
    """Generic external OpenAI-compatible API provider"""
    
    def __init__(self, base_url: str, api_key: str, model: str = None):
        self.base_url = base_url.rstrip('/')  # Remove trailing slash if present
        self.api_key = api_key
        self.default_model = model
        
    def chat_stream(self, messages: List[Dict], model: str, temperature: float) -> Generator:
        """Stream chat responses from external API"""
        if not self.api_key or not self.api_key.strip():
            yield {"error": "API key not provided. Please provide a valid API key to use External API."}
            return
            
        # Use provided model or default
        model_to_use = model if model else self.default_model
        if not model_to_use:
            yield {"error": "Model name not specified. Please provide a model name."}
            return
            
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model_to_use,
                    "messages": messages,
                    "stream": True,
                    "temperature": temperature
                },
                stream=True
            )
            
            if response.status_code != 200:
                error_msg = f"External API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if 'error' in error_data:
                        error_detail = error_data['error']
                        if isinstance(error_detail, dict):
                            error_msg = error_detail.get('message', str(error_detail))
                        else:
                            error_msg = str(error_detail)
                        
                        # Check for common authentication errors
                        if response.status_code == 401:
                            error_msg = "Invalid API key. Please check your API key and try again."
                        elif response.status_code == 403:
                            error_msg = "API key access forbidden. Please check your API key permissions."
                        elif response.status_code == 429:
                            error_msg = "Rate limit exceeded. Please try again later."
                        else:
                            error_msg = f"External API error: {error_msg}"
                except Exception:
                    if response.status_code == 401:
                        error_msg = "Invalid API key. Please check your API key and try again."
                    elif response.status_code == 403:
                        error_msg = "API key access forbidden. Please check your API key permissions."
                    elif response.status_code == 429:
                        error_msg = "Rate limit exceeded. Please try again later."
                    else:
                        error_msg = f"External API error: HTTP {response.status_code}"
                
                yield {"error": error_msg}
                return
                
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]  # Remove 'data: ' prefix
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
            logging.error(f"Connection error to External API: {e}")
            yield {"error": "Cannot connect to external API. Please check the API endpoint URL and your internet connection."}
        except requests.exceptions.Timeout as e:
            logging.error(f"Timeout error with External API: {e}")
            yield {"error": "External API request timed out. Please try again."}
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error with External API: {e}")
            yield {"error": f"External API request failed: {str(e)}"}
        except Exception as e:
            logging.error(f"Error in External API stream: {e}")
            yield {"error": f"Unexpected error: {str(e)}"}
    
    def get_available_models(self) -> List[str]:
        """Return the configured model"""
        if self.default_model:
            return [self.default_model]
        return []


def get_model_provider(provider_name: Optional[str] = None) -> ModelProvider:
    """Factory function to get the appropriate model provider"""
    provider = provider_name or MODEL_PROVIDER
    
    if provider == "ollama":
        return OllamaProvider()
    else:
        # Default to Ollama
        logging.warning(f"Unknown provider {provider}, defaulting to Ollama")
        return OllamaProvider()
