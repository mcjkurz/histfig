#!/usr/bin/env python3
"""Debug script to trace through the search process and see why keywords are missing"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from figure_manager import get_figure_manager
from text_processor import text_processor

def debug_search(figure_id="zhenghe", query="你去過東南亞、南亞、中東和東非，你覺得哪裡最有趣？"):
    """Debug the search process"""
    
    print("=" * 80)
    print("DEBUGGING SEARCH PROCESS")
    print("=" * 80)
    print(f"Figure: {figure_id}")
    print(f"Query: {query}")
    print()
    
    # Process query
    print("Step 1: Process Query")
    print("-" * 80)
    query_tokens = text_processor.process_query(query, ngram_range=(1, 2))
    print(f"Query tokens ({len(query_tokens)} total):")
    print("Unigrams:", [t for t in query_tokens if '_' not in t])
    print("Bigrams:", [t for t in query_tokens if '_' in t][:10], "...")
    print()
    
    # Check stopwords
    print("Step 2: Check Stopwords")
    print("-" * 80)
    unigram_tokens = [t for t in query_tokens if '_' not in t]
    stopword_tokens = [t for t in unigram_tokens if t in text_processor.stopwords]
    non_stopword_tokens = [t for t in unigram_tokens if t not in text_processor.stopwords]
    print(f"Stopword tokens: {stopword_tokens}")
    print(f"Non-stopword tokens: {non_stopword_tokens}")
    print()
    
    # Perform search
    print("Step 3: Perform Hybrid Search")
    print("-" * 80)
    figure_manager = get_figure_manager()
    results = figure_manager.search_figure_documents(figure_id, query, n_results=5)
    
    print(f"Total results: {len(results)}")
    print()
    
    # Analyze first result in detail
    if results:
        print("Step 4: Analyze First Result")
        print("-" * 80)
        result = results[0]
        doc_id = result.get('document_id', 'UNKNOWN')
        print(f"Document ID: {doc_id}")
        print(f"Cosine similarity: {result.get('cosine_similarity', 0):.3f}")
        print(f"BM25 score: {result.get('bm25_score', 0):.6f}")
        print(f"RRF score: {result.get('rrf_score', 0):.6f}")
        print(f"Top matching words: {result.get('top_matching_words', [])}")
        print()
        
        # Get the document tokens
        print("Step 5: Examine Document Tokens")
        print("-" * 80)
        
        # Get document from ChromaDB
        collection = figure_manager.get_figure_collection(figure_id)
        if collection:
            chroma_results = collection.get(
                ids=[doc_id],
                include=["documents", "metadatas"]
            )
            
            if chroma_results["metadatas"]:
                import json
                metadata = chroma_results["metadatas"][0]
                
                if "processed_tokens" in metadata:
                    doc_tokens_json = metadata["processed_tokens"]
                    doc_tokens = json.loads(doc_tokens_json)
                    doc_unigrams = [t for t in doc_tokens if '_' not in t]
                    doc_bigrams = [t for t in doc_tokens if '_' in t]
                    
                    print(f"Document has {len(doc_unigrams)} unigrams and {len(doc_bigrams)} bigrams")
                    print(f"First 20 unigrams: {doc_unigrams[:20]}")
                    print()
                    
                    # Find matching tokens
                    print("Step 6: Find Matching Tokens")
                    print("-" * 80)
                    matching_unigrams = [t for t in query_tokens if t in doc_tokens and '_' not in t]
                    matching_bigrams = [t for t in query_tokens if t in doc_tokens and '_' in t]
                    
                    print(f"Matching unigrams: {matching_unigrams}")
                    print(f"Matching bigrams: {matching_bigrams[:10]}")
                    print()
                    
                    # Check which would be filtered
                    print("Step 7: Check Stopword Filtering")
                    print("-" * 80)
                    filtered_matches = [t for t in matching_unigrams if t not in text_processor.stopwords]
                    stopword_matches = [t for t in matching_unigrams if t in text_processor.stopwords]
                    
                    print(f"Matches that pass filter: {filtered_matches}")
                    print(f"Matches filtered out (stopwords): {stopword_matches}")
                    print()
                else:
                    print("ERROR: No processed_tokens in document metadata!")
    else:
        print("No results found!")
    
    print("=" * 80)

if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "你去過東南亞、南亞、中東和東非，你覺得哪裡最有趣？"
    debug_search("zhenghe", query)


