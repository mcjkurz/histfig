"""
Query Augmentation Module
Enriches user queries with additional details to improve search results.
Uses async httpx for non-blocking HTTP requests.
"""

import logging
import httpx
from typing import Optional
from config import (
    QUERY_AUGMENTATION_ENABLED,
    QUERY_AUGMENTATION_MODEL,
    QUERY_AUGMENTATION_API_URL,
    QUERY_AUGMENTATION_API_KEY
)


async def augment_query(query: str, figure_name: str = "a historical figure", api_key: Optional[str] = None) -> str:
    """
    Augment a user query by adding more context and details.
    
    Args:
        query: Original user query
        figure_name: Name of the historical figure being addressed
        api_key: Optional API key (uses config if not provided)
        
    Returns:
        Augmented query or original query if augmentation is disabled/fails
    """
    if not QUERY_AUGMENTATION_ENABLED:
        logging.debug("Query augmentation is disabled in config")
        return query
    
    key = api_key or QUERY_AUGMENTATION_API_KEY
    if not key or not key.strip():
        logging.warning("No API key available for query augmentation, using original query")
        return query
    
    try:
        augmentation_prompt = f"""Given the following user query addressed to {figure_name}, expand it by adding relevant details, context, and related concepts that would help in document search. Important: Do not shorten or summarize the original query. Your response should include all the original content plus additional relevant information. If the query is already detailed, do not augment it further; just return the original query. Keep it concise and focused on the core topic. The augmented query must not exceed 250 words. Make sure to respond in the same language as the user's query.

User query: {query}

Augmented query:"""

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{QUERY_AUGMENTATION_API_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": QUERY_AUGMENTATION_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": augmentation_prompt
                        }
                    ],
                    "stream": False,
                    "temperature": 0.3,
                    "max_tokens": 400
                }
            )
        
        if response.status_code != 200:
            logging.warning(f"Query augmentation API error: {response.status_code}")
            return query
        
        result = response.json()
        if 'choices' in result and len(result['choices']) > 0:
            augmented = result['choices'][0]['message']['content'].strip()
            
            if augmented and len(augmented) >= len(query) and len(augmented) < 2000:
                logging.info(f"Query augmented: '{query}' -> '{augmented}'")
                return augmented
            elif augmented and len(augmented) < len(query):
                logging.warning(f"Augmented query is shorter than original ({len(augmented)} < {len(query)}), using original")
                return query
            else:
                logging.warning("Augmented query validation failed, using original")
                return query
        else:
            logging.warning("No valid response from augmentation API")
            return query
            
    except httpx.TimeoutException:
        logging.warning("Query augmentation request timed out, using original query")
        return query
    except httpx.RequestError as e:
        logging.warning(f"Query augmentation request failed: {e}, using original query")
        return query
    except Exception as e:
        logging.error(f"Unexpected error during query augmentation: {e}")
        return query
