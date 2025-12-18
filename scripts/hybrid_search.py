"""
Hybrid search system combining ChromaDB vector search with BM25 keyword search.
Uses Reciprocal Rank Fusion (RRF) to combine results from both methods.
"""

import os
import logging
import pickle
from typing import List, Dict, Any, Optional, Tuple
from rank_bm25 import BM25Okapi
from text_processor import text_processor
from vector_db import VectorDatabase
import numpy as np

class HybridSearchDatabase(VectorDatabase):
    """Extended VectorDatabase with hybrid search capabilities."""
    
    def __init__(self, db_path: str = "./chroma_db", model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize hybrid search database.
        
        Args:
            db_path: Path to store ChromaDB and BM25 data
            model_name: Sentence transformer model for embeddings
        """
        # Initialize parent class first
        try:
            super().__init__(db_path, model_name)
            logging.info("Parent VectorDatabase initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize parent VectorDatabase: {e}")
            raise e
        
        # BM25 storage paths
        self.bm25_index_path = os.path.join(db_path, "bm25_index.pkl")
        self.bm25_documents_path = os.path.join(db_path, "bm25_documents.pkl")
        self.bm25_metadata_path = os.path.join(db_path, "bm25_metadata.pkl")
        
        # Initialize BM25 components
        self.bm25_index = None
        self.bm25_documents = []  # List of processed token lists
        self.bm25_metadata = []   # List of metadata for each document
        self.chunk_id_to_bm25_idx = {}  # Map chunk_id to BM25 index
        
        # Load existing BM25 data if available
        self._load_bm25_data()
        
        logging.info("Hybrid search database initialized")
    
    def _load_bm25_data(self):
        """Load BM25 index and documents from disk."""
        try:
            if (os.path.exists(self.bm25_index_path) and 
                os.path.exists(self.bm25_documents_path) and
                os.path.exists(self.bm25_metadata_path)):
                
                with open(self.bm25_index_path, 'rb') as f:
                    self.bm25_index = pickle.load(f)
                
                with open(self.bm25_documents_path, 'rb') as f:
                    self.bm25_documents = pickle.load(f)
                
                with open(self.bm25_metadata_path, 'rb') as f:
                    self.bm25_metadata = pickle.load(f)
                
                # Rebuild chunk_id mapping
                self.chunk_id_to_bm25_idx = {}
                for idx, metadata in enumerate(self.bm25_metadata):
                    chunk_id = metadata.get("absolute_chunk_id")
                    if chunk_id is not None:
                        self.chunk_id_to_bm25_idx[chunk_id] = idx
                
                logging.info(f"Loaded BM25 index with {len(self.bm25_documents)} documents")
            else:
                logging.info("No existing BM25 data found, starting fresh")
        except Exception as e:
            logging.error(f"Error loading BM25 data: {e}")
            self.bm25_index = None
            self.bm25_documents = []
            self.bm25_metadata = []
            self.chunk_id_to_bm25_idx = {}
    
    def _save_bm25_data(self):
        """Save BM25 index and documents to disk."""
        try:
            os.makedirs(self.db_path, exist_ok=True)
            
            with open(self.bm25_index_path, 'wb') as f:
                pickle.dump(self.bm25_index, f)
            
            with open(self.bm25_documents_path, 'wb') as f:
                pickle.dump(self.bm25_documents, f)
            
            with open(self.bm25_metadata_path, 'wb') as f:
                pickle.dump(self.bm25_metadata, f)
            
            logging.debug("BM25 data saved to disk")
        except Exception as e:
            logging.error(f"Error saving BM25 data: {e}")
    
    def _rebuild_bm25_index(self):
        """Rebuild BM25 index from current documents."""
        if self.bm25_documents:
            self.bm25_index = BM25Okapi(self.bm25_documents)
            logging.info(f"Rebuilt BM25 index with {len(self.bm25_documents)} documents")
        else:
            self.bm25_index = None
    
    def add_document(self, text: str, metadata: Dict[str, Any]) -> int:
        """
        Add a document to both vector and BM25 indexes.
        
        Args:
            text: Document text content
            metadata: Document metadata
            
        Returns:
            Absolute chunk ID
        """
        # Add to vector database (parent class)
        chunk_id = super().add_document(text, metadata)
        
        # Process text for BM25
        processed_tokens = text_processor.process_text(text)
        
        if processed_tokens:  # Only add if we have tokens
            # Add to BM25 data structures
            bm25_idx = len(self.bm25_documents)
            self.bm25_documents.append(processed_tokens)
            
            # Store metadata with chunk_id
            bm25_metadata = {**metadata, "absolute_chunk_id": chunk_id}
            self.bm25_metadata.append(bm25_metadata)
            
            # Update mapping
            self.chunk_id_to_bm25_idx[chunk_id] = bm25_idx
            
            # Rebuild BM25 index
            self._rebuild_bm25_index()
            
            # Save to disk
            self._save_bm25_data()
            
            logging.debug(f"Added document to BM25 index: chunk_id={chunk_id}, tokens={len(processed_tokens)}")
        else:
            logging.warning(f"No tokens extracted for chunk_id={chunk_id}, skipping BM25 indexing")
        
        return chunk_id
    
    def _calculate_term_scores(self, query_tokens: List[str], doc_tokens: List[str], doc_idx: int) -> Dict[str, float]:
        """
        Calculate BM25 contribution score for each query term in a document.
        
        Args:
            query_tokens: Processed query tokens
            doc_tokens: Processed document tokens
            doc_idx: Document index in BM25 corpus
            
        Returns:
            Dictionary mapping terms to their BM25 contribution scores
        """
        term_scores = {}
        
        if not self.bm25_index:
            return term_scores
        
        # Get document frequencies and IDF values
        doc_len = len(doc_tokens)
        avgdl = self.bm25_index.avgdl
        
        # BM25 parameters
        k1 = self.bm25_index.k1
        b = self.bm25_index.b
        
        # Calculate score contribution for each query term
        for term in query_tokens:
            if term in doc_tokens:
                # Get term frequency in document
                tf = doc_tokens.count(term)
                
                # Get IDF value from BM25 index
                if hasattr(self.bm25_index, 'idf') and term in self.bm25_index.idf:
                    idf = self.bm25_index.idf[term]
                else:
                    # Default IDF if not found
                    idf = 0
                
                # BM25 formula for this term
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * doc_len / avgdl)
                term_score = idf * (numerator / denominator)
                
                term_scores[term] = term_score
        
        return term_scores
    
    def search_bm25(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search using BM25 keyword matching.
        
        Args:
            query: Search query
            n_results: Number of results to return
            
        Returns:
            List of search results with BM25 scores and top matching words
        """
        if not self.bm25_index or not self.bm25_documents:
            logging.warning("BM25 index is empty or not initialized")
            return []
        
        # Process query
        query_tokens = text_processor.process_query(query)
        
        if not query_tokens:
            logging.warning("No tokens extracted from query")
            return []
        
        # Get BM25 scores
        scores = self.bm25_index.get_scores(query_tokens)
        
        # Get top results
        top_indices = np.argsort(scores)[::-1][:n_results]
        
        # Normalize BM25 scores to similarity range [0, 1]
        max_score = max(scores) if len(scores) > 0 else 1.0
        min_score = min(s for s in scores if s > 0) if any(s > 0 for s in scores) else 0.0
        score_range = max_score - min_score if max_score > min_score else 1.0
        
        results = []
        for idx in top_indices:
            if idx < len(self.bm25_metadata) and scores[idx] > 0:
                metadata = self.bm25_metadata[idx]
                
                # Get original text from ChromaDB using chunk_id
                chunk_id = metadata.get("absolute_chunk_id")
                text = ""
                
                try:
                    # Query ChromaDB for the original text
                    chroma_results = self.collection.get(
                        ids=[str(chunk_id)],
                        include=["documents"]
                    )
                    if chroma_results["documents"]:
                        text = chroma_results["documents"][0]
                except Exception as e:
                    logging.warning(f"Could not retrieve text for chunk_id {chunk_id}: {e}")
                
                # Normalize BM25 score to similarity [0, 1]
                normalized_similarity = (scores[idx] - min_score) / score_range if score_range > 0 else 0.5
                
                # Calculate per-term BM25 scores and rank by importance
                doc_tokens = self.bm25_documents[idx]
                term_scores = self._calculate_term_scores(query_tokens, doc_tokens, idx)
                
                # Sort terms by their BM25 contribution (highest first)
                sorted_terms = sorted(term_scores.items(), key=lambda x: x[1], reverse=True)
                
                # Filter out stopwords and bigrams containing stopwords
                filtered_terms = []
                for term, score in sorted_terms:
                    # Check if term is a bigram (contains underscore)
                    if '_' in term:
                        # Filter bigrams where any component is a stopword
                        components = term.split('_')
                        if any(comp.lower() in text_processor.stopwords for comp in components):
                            continue
                        display_term = term.replace('_', ' ')
                    else:
                        # Skip unigram stopwords
                        if term.lower() in text_processor.stopwords:
                            continue
                        display_term = term
                    filtered_terms.append(display_term)
                
                top_matching_words = filtered_terms[:5] if filtered_terms else []
                
                results.append({
                    "text": text,
                    "metadata": metadata,
                    "bm25_score": float(scores[idx]),
                    "similarity": float(normalized_similarity),
                    "chunk_id": chunk_id,
                    "top_matching_words": top_matching_words
                })
        
        return results
    
    def search_vector(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search using vector similarity (wrapper around parent method).
        
        Args:
            query: Search query
            n_results: Number of results to return
            
        Returns:
            List of search results with similarity scores
        """
        return self.search_similar(query, n_results)
    
    def reciprocal_rank_fusion(self, vector_results: List[Dict[str, Any]], 
                              bm25_results: List[Dict[str, Any]], 
                              k: int = 60) -> List[Dict[str, Any]]:
        """
        Combine vector and BM25 results using Reciprocal Rank Fusion.
        Preserves cosine similarity and BM25 matching words for each result.
        
        Args:
            vector_results: Results from vector search (with cosine similarity)
            bm25_results: Results from BM25 search (with top matching words)
            k: RRF parameter (typically 60)
            
        Returns:
            Fused and re-ranked results with both metrics
        """
        # Create mappings from chunk_id to rank and result
        vector_ranks = {}
        vector_results_map = {}
        for rank, result in enumerate(vector_results):
            chunk_id = result.get("chunk_id")
            if chunk_id is not None:
                vector_ranks[chunk_id] = rank + 1  # 1-based ranking
                vector_results_map[chunk_id] = result
        
        bm25_ranks = {}
        bm25_results_map = {}
        for rank, result in enumerate(bm25_results):
            chunk_id = result.get("chunk_id")
            if chunk_id is not None:
                bm25_ranks[chunk_id] = rank + 1  # 1-based ranking
                bm25_results_map[chunk_id] = result
        
        # Calculate RRF scores
        all_chunk_ids = set(vector_ranks.keys()) | set(bm25_ranks.keys())
        rrf_scores = {}
        
        for chunk_id in all_chunk_ids:
            rrf_score = 0
            
            # Add vector contribution
            if chunk_id in vector_ranks:
                rrf_score += 1 / (k + vector_ranks[chunk_id])
            
            # Add BM25 contribution
            if chunk_id in bm25_ranks:
                rrf_score += 1 / (k + bm25_ranks[chunk_id])
            
            rrf_scores[chunk_id] = rrf_score
        
        # Sort by RRF score and create final results
        sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        
        fused_results = []
        for chunk_id in sorted_chunk_ids:
            # Start with vector result if available, otherwise BM25 result
            if chunk_id in vector_results_map:
                result = vector_results_map[chunk_id].copy()
                # Store the original cosine similarity from vector search
                result["cosine_similarity"] = result.get("similarity", 0)
            else:
                result = bm25_results_map[chunk_id].copy()
                # No vector match, cosine similarity is 0
                result["cosine_similarity"] = 0
            
            # Add BM25 information if available
            if chunk_id in bm25_results_map:
                bm25_result = bm25_results_map[chunk_id]
                result["bm25_score"] = bm25_result.get("bm25_score", 0)
                result["top_matching_words"] = bm25_result.get("top_matching_words", [])
            else:
                result["bm25_score"] = 0
                result["top_matching_words"] = []
            
            # Add RRF score and ranking information
            result["rrf_score"] = rrf_scores[chunk_id]
            result["vector_rank"] = vector_ranks.get(chunk_id, None)
            result["bm25_rank"] = bm25_ranks.get(chunk_id, None)
            
            # Keep the unified similarity field for backward compatibility
            # Use cosine similarity as the primary metric
            result["similarity"] = result["cosine_similarity"]
            
            fused_results.append(result)
        
        return fused_results
    
    def hybrid_search(self, query: str, n_results: int = 5, 
                     vector_weight: float = 0.5, bm25_weight: float = 0.5,
                     min_cosine_similarity: float = 0.05) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining vector and BM25 results.
        Only returns results with meaningful cosine similarity.
        
        Args:
            query: Search query
            n_results: Number of final results to return
            vector_weight: Weight for vector search (not used in RRF, kept for compatibility)
            bm25_weight: Weight for BM25 search (not used in RRF, kept for compatibility)
            min_cosine_similarity: Minimum cosine similarity threshold (default 0.05)
            
        Returns:
            Hybrid search results ranked by RRF with both cosine and BM25 metrics
        """
        # Get more results from each method to improve fusion
        search_multiplier = 3
        extended_n_results = min(n_results * search_multiplier, 30)
        
        # Perform vector search first
        vector_results = self.search_vector(query, extended_n_results)
        
        # Filter vector results to only those with meaningful cosine similarity
        filtered_vector_results = [
            r for r in vector_results 
            if r.get("similarity", 0) >= min_cosine_similarity
        ]
        
        logging.info(f"Vector search: {len(vector_results)} results, "
                    f"{len(filtered_vector_results)} after filtering (min similarity: {min_cosine_similarity})")
        
        # If no vector results pass the filter, return empty results
        if not filtered_vector_results:
            logging.warning("No results with sufficient cosine similarity found")
            return []
        
        # Get BM25 results, but only for documents that have meaningful vector similarity
        # This prevents pure keyword matches with no semantic relevance
        bm25_results = self.search_bm25(query, extended_n_results)
        
        logging.info(f"Hybrid search: vector={len(filtered_vector_results)}, bm25={len(bm25_results)} results")
        
        # Fuse results using RRF
        fused_results = self.reciprocal_rank_fusion(filtered_vector_results, bm25_results)
        
        # Final filter: only return results with meaningful cosine similarity
        final_results = [
            r for r in fused_results 
            if r.get("cosine_similarity", 0) >= min_cosine_similarity
        ]
        
        # Return top n_results
        return final_results[:n_results]
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about both vector and BM25 collections."""
        vector_stats = super().get_collection_stats()
        
        bm25_stats = {
            "bm25_documents": len(self.bm25_documents),
            "bm25_index_exists": self.bm25_index is not None
        }
        
        return {**vector_stats, **bm25_stats}

# Global instance
hybrid_db = None

def get_hybrid_db() -> HybridSearchDatabase:
    """Get or create global hybrid search database instance."""
    global hybrid_db
    if hybrid_db is None:
        from config import CHROMA_DB_PATH, EMBEDDING_MODEL
        try:
            hybrid_db = HybridSearchDatabase(db_path=CHROMA_DB_PATH, model_name=EMBEDDING_MODEL)
        except Exception as e:
            logging.error(f"Failed to initialize hybrid search database: {e}")
            raise e
    return hybrid_db
