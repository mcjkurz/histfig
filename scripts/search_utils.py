"""
Shared search utilities for hybrid search and result formatting.
"""

from typing import List, Dict, Any
from config import RRF_K


def reciprocal_rank_fusion(
    vector_results: List[Dict[str, Any]], 
    bm25_results: List[Dict[str, Any]], 
    k: int = None
) -> List[Dict[str, Any]]:
    """
    Combine vector and BM25 results using Reciprocal Rank Fusion.
    
    Args:
        vector_results: Results from vector/embedding search with 'document_id' and 'similarity'
        bm25_results: Results from BM25 keyword search with 'document_id' and 'bm25_score'
        k: RRF constant (default from config)
        
    Returns:
        Fused results sorted by RRF score with both metrics preserved
    """
    if k is None:
        k = RRF_K
    
    # Create mappings from document_id to rank and result
    vector_ranks = {}
    vector_results_map = {}
    for rank, result in enumerate(vector_results):
        doc_id = result.get("document_id")
        if doc_id:
            vector_ranks[doc_id] = rank + 1  # 1-based ranking
            vector_results_map[doc_id] = result
    
    bm25_ranks = {}
    bm25_results_map = {}
    for rank, result in enumerate(bm25_results):
        doc_id = result.get("document_id")
        if doc_id:
            bm25_ranks[doc_id] = rank + 1  # 1-based ranking
            bm25_results_map[doc_id] = result
    
    # Calculate RRF scores
    all_doc_ids = set(vector_ranks.keys()) | set(bm25_ranks.keys())
    rrf_scores = {}
    
    for doc_id in all_doc_ids:
        rrf_score = 0
        if doc_id in vector_ranks:
            rrf_score += 1 / (k + vector_ranks[doc_id])
        if doc_id in bm25_ranks:
            rrf_score += 1 / (k + bm25_ranks[doc_id])
        rrf_scores[doc_id] = rrf_score
    
    # Sort by RRF score and create final results
    sorted_doc_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    
    fused_results = []
    for doc_id in sorted_doc_ids:
        # Start with vector result if available, otherwise BM25 result
        if doc_id in vector_results_map:
            result = vector_results_map[doc_id].copy()
            result["cosine_similarity"] = result.get("similarity", 0)
        else:
            result = bm25_results_map[doc_id].copy()
            result["cosine_similarity"] = 0
        
        # Add BM25 information if available
        if doc_id in bm25_results_map:
            bm25_result = bm25_results_map[doc_id]
            result["bm25_score"] = bm25_result.get("bm25_score", 0)
            result["top_matching_words"] = bm25_result.get("top_matching_words", [])
        else:
            result["bm25_score"] = 0
            result["top_matching_words"] = []
        
        # Add RRF score and ranking information
        result["rrf_score"] = rrf_scores[doc_id]
        result["vector_rank"] = vector_ranks.get(doc_id, None)
        result["bm25_rank"] = bm25_ranks.get(doc_id, None)
        
        # Keep unified similarity field for backward compatibility
        result["similarity"] = result["cosine_similarity"]
        
        fused_results.append(result)
    
    return fused_results


def format_search_result_for_response(
    result: Dict[str, Any], 
    figure_id: str = None
) -> Dict[str, Any]:
    """
    Format a search result for API response.
    
    Args:
        result: Raw search result with text, metadata, and scores
        figure_id: Optional figure ID to include
        
    Returns:
        Formatted result dict for JSON response
    """
    doc_id = result.get('document_id', result.get('chunk_id', 'UNKNOWN'))
    text = result.get('text', '')
    
    formatted = {
        'filename': result['metadata'].get('filename', 'Unknown'),
        'text': text[:200] + '...' if len(text) > 200 else text,
        'full_text': text,
        'similarity': result.get('similarity', 0),
        'cosine_similarity': result.get('cosine_similarity', result.get('similarity', 0)),
        'bm25_score': result.get('bm25_score', 0),
        'rrf_score': result.get('rrf_score', 0),
        'top_matching_words': result.get('top_matching_words', []),
        'chunk_index': result['metadata'].get('chunk_index', 0),
    }
    
    if figure_id:
        formatted['document_id'] = doc_id
        formatted['figure_id'] = figure_id
    else:
        formatted['chunk_id'] = doc_id
        formatted['doc_id'] = f"DOC{doc_id}"
    
    return formatted

