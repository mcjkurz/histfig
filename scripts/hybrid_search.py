"""
Hybrid search system combining ChromaDB vector search with BM25 keyword search.
Uses Reciprocal Rank Fusion (RRF) to combine results from both methods.
"""

import os
import logging
import pickle
import json
from typing import List, Dict, Any, Optional, Tuple
from rank_bm25 import BM25Okapi
from text_processor import text_processor
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import torch
import numpy as np


class HybridSearchDatabase:
    """Hybrid search database combining ChromaDB vector search with BM25 keyword search."""
    
    def __init__(self, db_path: str = "./chroma_db", model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize hybrid search database.
        
        Args:
            db_path: Path to store ChromaDB and BM25 data
            model_name: Sentence transformer model for embeddings
        """
        self.db_path = db_path
        self.model_name = model_name
        self.chunk_counter_file = os.path.join(db_path, "chunk_counter.json")
        
        # Detect best available device
        if model_name == "all-MiniLM-L6-v2":
            self.device = "cpu"
            logging.info("Using CPU for embeddings (test mode)")
        elif torch.backends.mps.is_available():
            self.device = "mps"
            logging.info("Using Apple Silicon GPU (MPS) for embeddings")
        elif torch.cuda.is_available():
            self.device = "cuda"
            logging.info("Using CUDA GPU for embeddings")
        else:
            self.device = "cpu"
            logging.info("Using CPU for embeddings")
        
        # Initialize sentence transformer
        self.encoder = self._initialize_sentence_transformer(model_name)
        logging.info(f"Initialized SentenceTransformer '{model_name}' on device: {self.device}")
        
        # Initialize ChromaDB
        self._initialize_database()
        
        # BM25 storage paths
        self.bm25_index_path = os.path.join(db_path, "bm25_index.pkl")
        self.bm25_documents_path = os.path.join(db_path, "bm25_documents.pkl")
        self.bm25_metadata_path = os.path.join(db_path, "bm25_metadata.pkl")
        
        # Initialize BM25 components
        self.bm25_index = None
        self.bm25_documents = []
        self.bm25_metadata = []
        self.chunk_id_to_bm25_idx = {}
        
        # Load existing BM25 data if available
        self._load_bm25_data()
        
        logging.info("Hybrid search database initialized")
    
    def _initialize_sentence_transformer(self, model_name: str) -> SentenceTransformer:
        """Initialize SentenceTransformer with device handling and model-specific configurations."""
        model_kwargs = {}
        tokenizer_kwargs = {}
        
        if "qwen" in model_name.lower():
            model_kwargs = {
                "attn_implementation": "flash_attention_2", 
                "device_map": "auto"
            }
            tokenizer_kwargs = {"padding_side": "left"}
            logging.info(f"Detected Qwen model, using optimized settings")
        
        try:
            if model_kwargs or tokenizer_kwargs:
                self.encoder = SentenceTransformer(
                    model_name, 
                    device=self.device,
                    model_kwargs=model_kwargs,
                    tokenizer_kwargs=tokenizer_kwargs
                )
            else:
                self.encoder = SentenceTransformer(model_name, device=self.device)
            return self.encoder
        except Exception as e:
            logging.warning(f"Failed to initialize SentenceTransformer with device={self.device}: {e}")
            try:
                if model_kwargs or tokenizer_kwargs:
                    self.encoder = SentenceTransformer(
                        model_name,
                        model_kwargs=model_kwargs,
                        tokenizer_kwargs=tokenizer_kwargs
                    )
                else:
                    self.encoder = SentenceTransformer(model_name)
                self.encoder = self.encoder.to(self.device)
                logging.info(f"Successfully moved SentenceTransformer to {self.device}")
                return self.encoder
            except Exception as e2:
                logging.warning(f"Failed to move to {self.device}, falling back to CPU: {e2}")
                self.device = "cpu"
                if model_kwargs or tokenizer_kwargs:
                    self.encoder = SentenceTransformer(
                        model_name,
                        model_kwargs=model_kwargs,
                        tokenizer_kwargs=tokenizer_kwargs
                    )
                else:
                    self.encoder = SentenceTransformer(model_name)
                logging.info("Using CPU for embeddings (fallback)")
                return self.encoder
    
    def _initialize_database(self):
        """Initialize ChromaDB client and collection."""
        self.client = chromadb.PersistentClient(
            path=self.db_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"}
        )
        
        self._initialize_chunk_counter()
        
        logging.info(f"Vector database initialized with {self.collection.count()} documents")
    
    def _encode_text(self, text: str):
        """Encode document text."""
        with torch.no_grad():
            return self.encoder.encode(text)
    
    def _encode_query(self, query: str):
        """Encode query text with model-specific handling."""
        with torch.no_grad():
            if "qwen" in self.model_name.lower():
                try:
                    return self.encoder.encode(query, prompt_name="query")
                except:
                    return self.encoder.encode(query)
            return self.encoder.encode(query)
    
    def _initialize_chunk_counter(self):
        """Initialize or load the chunk counter."""
        os.makedirs(self.db_path, exist_ok=True)
        
        if os.path.exists(self.chunk_counter_file):
            try:
                with open(self.chunk_counter_file, 'r') as f:
                    data = json.load(f)
                    self.next_chunk_id = data.get('next_chunk_id', 0)
            except (json.JSONDecodeError, FileNotFoundError):
                self.next_chunk_id = 0
        else:
            self.next_chunk_id = 0
    
    def _save_chunk_counter(self):
        """Save the current chunk counter to file."""
        try:
            with open(self.chunk_counter_file, 'w') as f:
                json.dump({'next_chunk_id': self.next_chunk_id}, f)
        except Exception as e:
            logging.error(f"Error saving chunk counter: {e}")
    
    def _get_next_chunk_id(self) -> int:
        """Get the next available chunk ID and increment counter."""
        chunk_id = self.next_chunk_id
        self.next_chunk_id += 1
        self._save_chunk_counter()
        return chunk_id
    
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
        # Get next sequential chunk ID
        chunk_id = self._get_next_chunk_id()
        doc_id = str(chunk_id)
        
        # Add chunk ID to metadata
        metadata_with_id = {**metadata, "absolute_chunk_id": chunk_id}
        
        # Generate embedding and add to ChromaDB
        embedding = self._encode_text(text).tolist()
        self.collection.add(
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata_with_id],
            ids=[doc_id]
        )
        
        logging.info(f"Added document chunk with ID: {chunk_id}")
        
        # Process text for BM25
        processed_tokens = text_processor.process_text(text)
        
        if processed_tokens:
            bm25_idx = len(self.bm25_documents)
            self.bm25_documents.append(processed_tokens)
            
            bm25_metadata = {**metadata, "absolute_chunk_id": chunk_id}
            self.bm25_metadata.append(bm25_metadata)
            
            self.chunk_id_to_bm25_idx[chunk_id] = bm25_idx
            
            self._rebuild_bm25_index()
            self._save_bm25_data()
            
            logging.debug(f"Added document to BM25 index: chunk_id={chunk_id}, tokens={len(processed_tokens)}")
        else:
            logging.warning(f"No tokens extracted for chunk_id={chunk_id}, skipping BM25 indexing")
        
        return chunk_id
    
    def search_similar(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search for similar documents using semantic similarity.
        
        Args:
            query: Search query text
            n_results: Number of results to return
            
        Returns:
            List of similar documents with metadata
        """
        query_embedding = self._encode_query(query).tolist()
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        formatted_results = []
        if results["documents"] and results["documents"][0]:
            for i in range(len(results["documents"][0])):
                metadata = results["metadatas"][0][i]
                distance = results["distances"][0][i]
                similarity = 1.0 - distance
                
                formatted_results.append({
                    "text": results["documents"][0][i],
                    "metadata": metadata,
                    "similarity": similarity,
                    "chunk_id": metadata.get("absolute_chunk_id", 0)
                })
        
        return formatted_results
    
    def _calculate_term_scores(self, query_tokens: List[str], doc_tokens: List[str], doc_idx: int) -> Dict[str, float]:
        """Calculate BM25 contribution score for each query term in a document."""
        term_scores = {}
        
        if not self.bm25_index:
            return term_scores
        
        doc_len = len(doc_tokens)
        avgdl = self.bm25_index.avgdl
        k1 = self.bm25_index.k1
        b = self.bm25_index.b
        
        for term in query_tokens:
            if term in doc_tokens:
                tf = doc_tokens.count(term)
                
                if hasattr(self.bm25_index, 'idf') and term in self.bm25_index.idf:
                    idf = self.bm25_index.idf[term]
                else:
                    idf = 0
                
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * doc_len / avgdl)
                term_score = idf * (numerator / denominator)
                
                term_scores[term] = term_score
        
        return term_scores
    
    def search_bm25(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search using BM25 keyword matching."""
        if not self.bm25_index or not self.bm25_documents:
            logging.warning("BM25 index is empty or not initialized")
            return []
        
        query_tokens = text_processor.process_query(query)
        
        if not query_tokens:
            logging.warning("No tokens extracted from query")
            return []
        
        scores = self.bm25_index.get_scores(query_tokens)
        top_indices = np.argsort(scores)[::-1][:n_results]
        
        max_score = max(scores) if len(scores) > 0 else 1.0
        min_score = min(s for s in scores if s > 0) if any(s > 0 for s in scores) else 0.0
        score_range = max_score - min_score if max_score > min_score else 1.0
        
        results = []
        for idx in top_indices:
            if idx < len(self.bm25_metadata) and scores[idx] > 0:
                metadata = self.bm25_metadata[idx]
                chunk_id = metadata.get("absolute_chunk_id")
                text = ""
                
                try:
                    chroma_results = self.collection.get(
                        ids=[str(chunk_id)],
                        include=["documents"]
                    )
                    if chroma_results["documents"]:
                        text = chroma_results["documents"][0]
                except Exception as e:
                    logging.warning(f"Could not retrieve text for chunk_id {chunk_id}: {e}")
                
                normalized_similarity = (scores[idx] - min_score) / score_range if score_range > 0 else 0.5
                
                doc_tokens = self.bm25_documents[idx]
                term_scores = self._calculate_term_scores(query_tokens, doc_tokens, idx)
                sorted_terms = sorted(term_scores.items(), key=lambda x: x[1], reverse=True)
                
                filtered_terms = []
                for term, score in sorted_terms:
                    if '_' in term:
                        components = term.split('_')
                        if any(comp.lower() in text_processor.stopwords for comp in components):
                            continue
                        display_term = term.replace('_', ' ')
                    else:
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
        """Search using vector similarity (wrapper around search_similar)."""
        return self.search_similar(query, n_results)
    
    def reciprocal_rank_fusion(self, vector_results: List[Dict[str, Any]], 
                              bm25_results: List[Dict[str, Any]], 
                              k: int = 60) -> List[Dict[str, Any]]:
        """Combine vector and BM25 results using Reciprocal Rank Fusion."""
        vector_ranks = {}
        vector_results_map = {}
        for rank, result in enumerate(vector_results):
            chunk_id = result.get("chunk_id")
            if chunk_id is not None:
                vector_ranks[chunk_id] = rank + 1
                vector_results_map[chunk_id] = result
        
        bm25_ranks = {}
        bm25_results_map = {}
        for rank, result in enumerate(bm25_results):
            chunk_id = result.get("chunk_id")
            if chunk_id is not None:
                bm25_ranks[chunk_id] = rank + 1
                bm25_results_map[chunk_id] = result
        
        all_chunk_ids = set(vector_ranks.keys()) | set(bm25_ranks.keys())
        rrf_scores = {}
        
        for chunk_id in all_chunk_ids:
            rrf_score = 0
            if chunk_id in vector_ranks:
                rrf_score += 1 / (k + vector_ranks[chunk_id])
            if chunk_id in bm25_ranks:
                rrf_score += 1 / (k + bm25_ranks[chunk_id])
            rrf_scores[chunk_id] = rrf_score
        
        sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        
        fused_results = []
        for chunk_id in sorted_chunk_ids:
            if chunk_id in vector_results_map:
                result = vector_results_map[chunk_id].copy()
                result["cosine_similarity"] = result.get("similarity", 0)
            else:
                result = bm25_results_map[chunk_id].copy()
                result["cosine_similarity"] = 0
            
            if chunk_id in bm25_results_map:
                bm25_result = bm25_results_map[chunk_id]
                result["bm25_score"] = bm25_result.get("bm25_score", 0)
                result["top_matching_words"] = bm25_result.get("top_matching_words", [])
            else:
                result["bm25_score"] = 0
                result["top_matching_words"] = []
            
            result["rrf_score"] = rrf_scores[chunk_id]
            result["vector_rank"] = vector_ranks.get(chunk_id, None)
            result["bm25_rank"] = bm25_ranks.get(chunk_id, None)
            result["similarity"] = result["cosine_similarity"]
            
            fused_results.append(result)
        
        return fused_results
    
    def hybrid_search(self, query: str, n_results: int = 5, 
                     min_cosine_similarity: float = 0.05) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining vector and BM25 results using RRF.
        Only returns results with meaningful cosine similarity.
        """
        search_multiplier = 3
        extended_n_results = min(n_results * search_multiplier, 30)
        
        vector_results = self.search_vector(query, extended_n_results)
        
        filtered_vector_results = [
            r for r in vector_results 
            if r.get("similarity", 0) >= min_cosine_similarity
        ]
        
        logging.info(f"Vector search: {len(vector_results)} results, "
                    f"{len(filtered_vector_results)} after filtering (min similarity: {min_cosine_similarity})")
        
        if not filtered_vector_results:
            logging.warning("No results with sufficient cosine similarity found")
            return []
        
        bm25_results = self.search_bm25(query, extended_n_results)
        
        logging.info(f"Hybrid search: vector={len(filtered_vector_results)}, bm25={len(bm25_results)} results")
        
        fused_results = self.reciprocal_rank_fusion(filtered_vector_results, bm25_results)
        
        final_results = [
            r for r in fused_results 
            if r.get("cosine_similarity", 0) >= min_cosine_similarity
        ]
        
        return final_results[:n_results]
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about both vector and BM25 collections."""
        try:
            count = self.collection.count()
            return {
                "total_documents": count,
                "model_name": self.model_name,
                "db_path": self.db_path,
                "bm25_documents": len(self.bm25_documents),
                "bm25_index_exists": self.bm25_index is not None
            }
        except Exception as e:
            logging.error(f"Error getting collection stats: {e}")
            return {
                "total_documents": 0,
                "model_name": self.model_name,
                "db_path": self.db_path,
                "bm25_documents": len(self.bm25_documents),
                "bm25_index_exists": self.bm25_index is not None,
                "error": str(e)
            }
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete a document from the vector database."""
        try:
            self.collection.delete(ids=[doc_id])
            logging.info(f"Deleted document: {doc_id}")
            return True
        except Exception as e:
            logging.error(f"Error deleting document {doc_id}: {e}")
            return False
    
    def clear_collection(self) -> bool:
        """Clear all documents from the collection."""
        try:
            self.client.delete_collection("documents")
            self.collection = self.client.get_or_create_collection(
                name="documents",
                metadata={"hnsw:space": "cosine"}
            )
            
            self.next_chunk_id = 0
            self._save_chunk_counter()
            
            # Clear BM25 data
            self.bm25_index = None
            self.bm25_documents = []
            self.bm25_metadata = []
            self.chunk_id_to_bm25_idx = {}
            self._save_bm25_data()
            
            logging.info("Cleared all documents from collection and reset chunk counter")
            return True
        except Exception as e:
            logging.error(f"Error clearing collection: {e}")
            return False
    
    def get_documents_by_filename(self, filename: str) -> List[Dict[str, Any]]:
        """Get all document chunks for a specific filename."""
        try:
            results = self.collection.get(
                where={"filename": filename},
                include=["documents", "metadatas"]
            )
            
            formatted_results = []
            if results["documents"]:
                for i in range(len(results["documents"])):
                    formatted_results.append({
                        "text": results["documents"][i],
                        "metadata": results["metadatas"][i],
                        "id": results["ids"][i]
                    })
            
            return formatted_results
        except Exception as e:
            logging.error(f"Error getting documents for {filename}: {e}")
            return []


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
