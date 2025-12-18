"""
Figure Management System for Historical Figures Simulation
Handles CRUD operations for historical figures and their document collections.
"""

import os
import json
import shutil
import pickle
from typing import List, Dict, Any, Optional
import logging
from pathlib import Path
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import torch
import re
import numpy as np
from rank_bm25 import BM25Okapi
from config import EMBEDDING_MODEL
from text_processor import text_processor
from query_augmentation import augment_query

class FigureManager:
    def __init__(self, figures_dir: str = "./figures", db_path: str = "./chroma_db"):
        """
        Initialize figure manager.
        
        Args:
            figures_dir: Directory to store figure data
            db_path: Path to ChromaDB database
        """
        self.figures_dir = Path(figures_dir)
        self.db_path = db_path
        self.figures_dir.mkdir(exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Initialize sentence transformer for embeddings
        if torch.backends.mps.is_available():
            self.device = "mps"
        elif torch.cuda.is_available():
            self.device = "cuda"
        else:
            self.device = "cpu"
        
        self.encoder = SentenceTransformer(EMBEDDING_MODEL, device=self.device)
        
        # BM25 memory cache for fast searches
        self.bm25_cache = {}  # figure_id -> BM25Okapi object
        self.bm25_documents_cache = {}  # figure_id -> list of token lists
        self.bm25_metadata_cache = {}  # figure_id -> list of metadata dicts
        
        # BM25 persistence paths
        self.bm25_dir = Path(db_path) / "bm25_indexes"
        self.bm25_dir.mkdir(exist_ok=True)
        
        logging.info(f"Figure manager initialized with device: {self.device}")
    
    def _get_bm25_paths(self, figure_id: str) -> tuple:
        """Get BM25 file paths for a figure."""
        base_path = self.bm25_dir / figure_id
        return (
            base_path.with_suffix('.index.pkl'),
            base_path.with_suffix('.docs.pkl'),
            base_path.with_suffix('.meta.pkl')
        )
    
    def _save_bm25_to_disk(self, figure_id: str):
        """Save BM25 data to disk for persistence."""
        if figure_id not in self.bm25_cache:
            return
            
        try:
            index_path, docs_path, meta_path = self._get_bm25_paths(figure_id)
            
            with open(index_path, 'wb') as f:
                pickle.dump(self.bm25_cache[figure_id], f)
            
            with open(docs_path, 'wb') as f:
                pickle.dump(self.bm25_documents_cache.get(figure_id, []), f)
            
            with open(meta_path, 'wb') as f:
                pickle.dump(self.bm25_metadata_cache.get(figure_id, []), f)
                
            logging.debug(f"Saved BM25 data to disk for figure {figure_id}")
        except Exception as e:
            logging.error(f"Error saving BM25 data for figure {figure_id}: {e}")
    
    def _load_bm25_from_disk(self, figure_id: str) -> bool:
        """Load BM25 data from disk if available."""
        try:
            index_path, docs_path, meta_path = self._get_bm25_paths(figure_id)
            
            if not all(p.exists() for p in [index_path, docs_path, meta_path]):
                return False
            
            with open(index_path, 'rb') as f:
                self.bm25_cache[figure_id] = pickle.load(f)
            
            with open(docs_path, 'rb') as f:
                self.bm25_documents_cache[figure_id] = pickle.load(f)
            
            with open(meta_path, 'rb') as f:
                self.bm25_metadata_cache[figure_id] = pickle.load(f)
                
            logging.info(f"Loaded BM25 data from disk for figure {figure_id}")
            return True
        except Exception as e:
            logging.error(f"Error loading BM25 data for figure {figure_id}: {e}")
            return False
    
    def _invalidate_bm25_cache(self, figure_id: str):
        """Invalidate BM25 cache for a figure when documents change."""
        # Clear memory cache
        if figure_id in self.bm25_cache:
            del self.bm25_cache[figure_id]
        if figure_id in self.bm25_documents_cache:
            del self.bm25_documents_cache[figure_id]
        if figure_id in self.bm25_metadata_cache:
            del self.bm25_metadata_cache[figure_id]
            
        # Remove disk files
        try:
            index_path, docs_path, meta_path = self._get_bm25_paths(figure_id)
            for path in [index_path, docs_path, meta_path]:
                if path.exists():
                    path.unlink()
        except Exception as e:
            logging.warning(f"Error removing BM25 files for figure {figure_id}: {e}")
            
        logging.debug(f"Invalidated BM25 cache for figure {figure_id}")
    
    def preload_bm25_index(self, figure_id: str) -> bool:
        """Preload BM25 index for a figure from disk or build from ChromaDB."""
        try:
            # Check if already loaded in memory
            if figure_id in self.bm25_cache:
                return True
            
            # Try to load from disk first
            if self._load_bm25_from_disk(figure_id):
                return True
            
            # Build from ChromaDB if not on disk
            return self._build_bm25_from_chromadb(figure_id)
            
        except Exception as e:
            logging.error(f"Error preloading BM25 index for figure {figure_id}: {e}")
            return False
    
    def _build_bm25_from_chromadb(self, figure_id: str) -> bool:
        """Build BM25 index from ChromaDB metadata."""
        try:
            collection = self.get_figure_collection(figure_id)
            if not collection:
                return False
            
            # Get all documents with their processed tokens from metadata
            all_docs = collection.get(include=["metadatas"])
            if not all_docs["metadatas"]:
                logging.info(f"No documents found for figure {figure_id}")
                return False
            
            # Extract processed tokens from metadata (deserialize JSON)
            token_lists = []
            metadata_list = []
            
            for metadata in all_docs["metadatas"]:
                tokens_json = metadata.get("processed_tokens", "")
                if tokens_json:  # Only include documents that have processed tokens
                    try:
                        import json
                        tokens = json.loads(tokens_json)
                        if tokens:  # Make sure the list is not empty
                            token_lists.append(tokens)
                            metadata_list.append(metadata)
                    except (json.JSONDecodeError, TypeError) as e:
                        logging.warning(f"Could not parse processed tokens: {e}")
                        continue
            
            if not token_lists:
                logging.info(f"No processed tokens found for figure {figure_id}")
                return False
            
            # Build BM25 index
            bm25_index = BM25Okapi(token_lists)
            
            # Cache in memory
            self.bm25_cache[figure_id] = bm25_index
            self.bm25_documents_cache[figure_id] = token_lists
            self.bm25_metadata_cache[figure_id] = metadata_list
            
            # Save to disk for future use
            self._save_bm25_to_disk(figure_id)
            
            logging.info(f"Built and cached BM25 index for figure {figure_id}: {len(token_lists)} documents")
            return True
            
        except Exception as e:
            logging.error(f"Error building BM25 index for figure {figure_id}: {e}")
            return False
    
    def _get_bm25_index(self, figure_id: str) -> Optional[BM25Okapi]:
        """Get BM25 index for a figure, preloading if necessary."""
        if figure_id not in self.bm25_cache:
            if not self.preload_bm25_index(figure_id):
                return None
        return self.bm25_cache.get(figure_id)

    def create_figure(self, figure_id: str, name: str, description: str = "", 
                     personality_prompt: str = "", metadata: Dict[str, Any] = None) -> bool:
        """
        Create a new historical figure with validation.
        
        Args:
            figure_id: Unique identifier for the figure (only alphabetic characters)
            name: Display name (Unicode letters and spaces allowed)
            description: Description of the figure (max 400 chars)
            personality_prompt: Optional personality prompt (max 400 chars)
            metadata: Additional metadata (birth_year, death_year, etc.)
            
        Returns:
            True if successful
        """
        try:
            # Additional validation at model level
            if not re.match(r'^[a-zA-Z]+$', figure_id):
                logging.error(f"Invalid figure_id format: {figure_id}")
                return False
            
            # Allow Unicode letters (including Chinese) and spaces, but not numbers or special chars
            if re.search(r'[0-9!@#$%^&*()_+=\[\]{};:\'",.<>?/\\|`~]', name):
                logging.error(f"Invalid name format (contains numbers or special characters): {name}")
                return False
            
            # Enforce length limits
            description = description[:400] if description else ""
            personality_prompt = personality_prompt[:400] if personality_prompt else ""
            
            figure_path = self.figures_dir / figure_id
            
            if figure_path.exists():
                logging.error(f"Figure {figure_id} already exists")
                return False
            
            # Create figure directory structure
            figure_path.mkdir(exist_ok=True)
            
            # Create metadata file
            figure_metadata = {
                "figure_id": figure_id,
                "name": name,
                "description": description,
                "personality_prompt": personality_prompt,
                "created_at": str(Path().resolve()),
                "document_count": 0,
                "metadata": metadata or {}
            }
            
            metadata_file = figure_path / "metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(figure_metadata, f, indent=2, ensure_ascii=False)
            
            # Create ChromaDB collection for this figure
            collection_name = f"figure_{figure_id}"
            self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine", "figure_id": figure_id}
            )
            
            logging.info(f"Created figure: {name} ({figure_id})")
            return True
            
        except Exception as e:
            logging.error(f"Error creating figure {figure_id}: {e}")
            return False
    
    def get_figure_list(self) -> List[Dict[str, Any]]:
        """Get list of all available figures."""
        figures = []
        
        try:
            for figure_dir in self.figures_dir.iterdir():
                if figure_dir.is_dir():
                    metadata_file = figure_dir / "metadata.json"
                    if metadata_file.exists():
                        try:
                            with open(metadata_file, 'r', encoding='utf-8') as f:
                                metadata = json.load(f)
                                figures.append(metadata)
                        except (json.JSONDecodeError, FileNotFoundError):
                            logging.warning(f"Invalid metadata file for figure: {figure_dir.name}")
                            continue
            
            return sorted(figures, key=lambda x: x.get('name', ''))
        
        except Exception as e:
            logging.error(f"Error getting figure list: {e}")
            return []
    
    def get_figure_metadata(self, figure_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific figure."""
        try:
            metadata_file = self.figures_dir / figure_id / "metadata.json"
            if not metadata_file.exists():
                return None
            
            with open(metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        except Exception as e:
            logging.error(f"Error getting metadata for figure {figure_id}: {e}")
            return None
    
    def update_figure_metadata(self, figure_id: str, updates: Dict[str, Any]) -> bool:
        """Update metadata for a figure with validation."""
        try:
            metadata = self.get_figure_metadata(figure_id)
            if not metadata:
                logging.error(f"Figure {figure_id} not found")
                return False
            
            # Validate updates - allow Unicode letters (including Chinese) and spaces
            if 'name' in updates and updates['name']:
                if re.search(r'[0-9!@#$%^&*()_+=\[\]{};:\'",.<>?/\\|`~]', updates['name']):
                    logging.error(f"Invalid name format (contains numbers or special characters): {updates['name']}")
                    return False
            
            # Enforce length limits
            if 'description' in updates:
                updates['description'] = updates['description'][:400] if updates['description'] else ""
            if 'personality_prompt' in updates:
                updates['personality_prompt'] = updates['personality_prompt'][:400] if updates['personality_prompt'] else ""
            
            # Update metadata
            metadata.update(updates)
            
            # Save updated metadata
            metadata_file = self.figures_dir / figure_id / "metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            logging.info(f"Updated metadata for figure: {figure_id}")
            return True
        
        except Exception as e:
            logging.error(f"Error updating metadata for figure {figure_id}: {e}")
            return False
    
    def delete_figure(self, figure_id: str) -> bool:
        """Delete a figure and all its data."""
        try:
            figure_path = self.figures_dir / figure_id
            if not figure_path.exists():
                logging.error(f"Figure {figure_id} not found")
                return False
            
            # Delete ChromaDB collection
            collection_name = f"figure_{figure_id}"
            try:
                self.client.delete_collection(collection_name)
            except Exception as e:
                logging.warning(f"Error deleting collection {collection_name}: {e}")
            
            # Delete figure directory
            shutil.rmtree(figure_path)
            
            logging.info(f"Deleted figure: {figure_id}")
            return True
        
        except Exception as e:
            logging.error(f"Error deleting figure {figure_id}: {e}")
            return False
    
    def get_figure_collection(self, figure_id: str):
        """Get ChromaDB collection for a figure."""
        try:
            collection_name = f"figure_{figure_id}"
            return self.client.get_collection(collection_name)
        except Exception as e:
            logging.error(f"Error getting collection for figure {figure_id}: {e}")
            return None
    
    def add_document_to_figure(self, figure_id: str, text: str, metadata: Dict[str, Any]) -> Optional[str]:
        """
        Add a document chunk to a figure's collection with hybrid search support.
        
        Args:
            figure_id: Figure identifier
            text: Document text content
            metadata: Document metadata
            
        Returns:
            Document ID if successful, None otherwise
        """
        try:
            collection = self.get_figure_collection(figure_id)
            if not collection:
                logging.error(f"Collection not found for figure: {figure_id}")
                return None
            
            # Generate embedding for vector search
            embedding = self.encoder.encode(text).tolist()
            
            # Generate unique document ID
            doc_id = f"{figure_id}_{collection.count()}"
            
            # Process text for BM25 search
            processed_tokens = text_processor.process_text(text)
            
            # Create complete metadata with doc_id and processed tokens
            metadata_with_id = {**metadata, "doc_id": doc_id}
            if processed_tokens:
                import json
                metadata_with_id["processed_tokens"] = json.dumps(processed_tokens)
                logging.debug(f"Added {len(processed_tokens)} processed tokens to metadata for {doc_id}")
            else:
                logging.warning(f"No tokens extracted for {doc_id}, BM25 search may be limited")
            
            # Add to ChromaDB collection with complete metadata
            collection.add(
                documents=[text],
                embeddings=[embedding],
                metadatas=[metadata_with_id],
                ids=[doc_id]
            )
            
            # Update BM25 cache incrementally if it exists
            if figure_id in self.bm25_cache and processed_tokens:
                try:
                    # Add to existing cache
                    self.bm25_documents_cache.setdefault(figure_id, []).append(processed_tokens)
                    self.bm25_metadata_cache.setdefault(figure_id, []).append(metadata_with_id)
                    
                    # Rebuild BM25 index with new document
                    self.bm25_cache[figure_id] = BM25Okapi(self.bm25_documents_cache[figure_id])
                    
                    # Save updated index to disk
                    self._save_bm25_to_disk(figure_id)
                    
                    logging.debug(f"Updated BM25 index for figure {figure_id} with new document")
                except Exception as e:
                    logging.warning(f"Error updating BM25 cache, invalidating: {e}")
                    self._invalidate_bm25_cache(figure_id)
            else:
                # Invalidate cache if it exists but we couldn't update it
                if figure_id in self.bm25_cache:
                    self._invalidate_bm25_cache(figure_id)
            
            # Update document count in figure metadata
            figure_metadata = self.get_figure_metadata(figure_id)
            if figure_metadata:
                figure_metadata["document_count"] = collection.count()
                self.update_figure_metadata(figure_id, figure_metadata)
            
            logging.info(f"Added document to figure {figure_id}: {doc_id}")
            return doc_id
        
        except Exception as e:
            logging.error(f"Error adding document to figure {figure_id}: {e}")
            return None
    
    def search_figure_documents(self, figure_id: str, query: str, n_results: int = 5, 
                               min_cosine_similarity: float = 0.05) -> List[Dict[str, Any]]:
        """
        Search for similar documents in a figure's collection using hybrid search.
        Only returns results with meaningful cosine similarity.
        
        Args:
            figure_id: Figure identifier
            query: Search query (will be augmented if enabled)
            n_results: Number of results to return
            min_cosine_similarity: Minimum cosine similarity threshold (default 0.05)
            
        Returns:
            List of similar documents ranked by hybrid search with both metrics
        """
        try:
            # Get figure name for query augmentation
            figure_metadata = self.get_figure_metadata(figure_id)
            figure_name = figure_metadata.get('name', figure_id) if figure_metadata else figure_id
            
            # Augment query if enabled (transparent to user)
            augmented_query = augment_query(query, figure_name=figure_name)
            logging.info(f"Original query: '{query}'")
            if augmented_query != query:
                logging.info(f"Using augmented query: '{augmented_query}'")
            
            # Use augmented query for search
            search_query = augmented_query
            
            # Preload BM25 index for efficient searching
            self.preload_bm25_index(figure_id)
            
            # Get more results from each method to improve fusion
            search_multiplier = 3
            extended_n_results = min(n_results * search_multiplier, 30)
            
            # Perform vector search (using augmented query)
            vector_results = self._search_figure_vector(figure_id, search_query, extended_n_results)
            
            # Filter vector results to only those with meaningful cosine similarity
            filtered_vector_results = [
                r for r in vector_results 
                if r.get("similarity", 0) >= min_cosine_similarity
            ]
            
            logging.info(f"Figure {figure_id} vector search: {len(vector_results)} results, "
                        f"{len(filtered_vector_results)} after filtering (min similarity: {min_cosine_similarity})")
            
            # If no vector results pass the filter, return empty results
            if not filtered_vector_results:
                logging.warning(f"No results with sufficient cosine similarity found for figure {figure_id}")
                return []
            
            # Perform BM25 search (using augmented query)
            bm25_results = self._search_figure_bm25(figure_id, search_query, extended_n_results)
            
            logging.info(f"Figure {figure_id} hybrid search: vector={len(filtered_vector_results)}, bm25={len(bm25_results)} results")
            
            # Fuse results using RRF
            fused_results = self._reciprocal_rank_fusion(filtered_vector_results, bm25_results)
            
            # Final filter: only return results with meaningful cosine similarity
            final_results = [
                r for r in fused_results 
                if r.get("cosine_similarity", 0) >= min_cosine_similarity
            ]
            
            # Return top n_results
            return final_results[:n_results]
        
        except Exception as e:
            logging.error(f"Error in hybrid search for figure {figure_id}: {e}")
            return []
    
    def _search_figure_vector(self, figure_id: str, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Perform vector search for a figure."""
        try:
            collection = self.get_figure_collection(figure_id)
            if not collection:
                return []
            
            # Generate query embedding
            query_embedding = self.encoder.encode(query).tolist()
            
            # Search in collection
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )
            
            # Format results
            formatted_results = []
            if results["documents"] and results["documents"][0]:
                for i in range(len(results["documents"][0])):
                    # ChromaDB query doesn't return IDs by default, we need to get them from metadata or generate
                    metadata = results["metadatas"][0][i]
                    doc_id = metadata.get("doc_id", f"doc_{i}")
                    # Convert cosine distance to similarity score
                    # ChromaDB returns cosine distance = 1 - cosine_similarity
                    # distance 0 = identical (similarity 1), distance 2 = opposite (similarity -1)
                    distance = results["distances"][0][i]
                    similarity = 1.0 - distance  # Range: [-1, 1]
                    
                    formatted_results.append({
                        "text": results["documents"][0][i],
                        "metadata": metadata,
                        "similarity": similarity,
                        "document_id": doc_id
                    })
            
            return formatted_results
        
        except Exception as e:
            logging.error(f"Error in vector search for figure {figure_id}: {e}")
            return []
    
    def _calculate_term_scores(self, bm25_index, query_tokens: List[str], doc_tokens: List[str], doc_idx: int) -> Dict[str, float]:
        """
        Calculate BM25 contribution score for each query term in a document.
        
        Args:
            bm25_index: BM25Okapi index object
            query_tokens: Processed query tokens
            doc_tokens: Processed document tokens
            doc_idx: Document index in BM25 corpus
            
        Returns:
            Dictionary mapping terms to their BM25 contribution scores
        """
        term_scores = {}
        
        if not bm25_index:
            return term_scores
        
        # Get document frequencies and IDF values
        doc_len = len(doc_tokens)
        avgdl = bm25_index.avgdl
        
        # BM25 parameters
        k1 = bm25_index.k1
        b = bm25_index.b
        
        # Calculate score contribution for each query term
        for term in query_tokens:
            if term in doc_tokens:
                # Get term frequency in document
                tf = doc_tokens.count(term)
                
                # Get IDF value from BM25 index
                if hasattr(bm25_index, 'idf') and term in bm25_index.idf:
                    idf = bm25_index.idf[term]
                else:
                    # Default IDF if not found
                    idf = 0
                
                # BM25 formula for this term
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * doc_len / avgdl)
                term_score = idf * (numerator / denominator)
                
                term_scores[term] = term_score
        
        return term_scores
    
    def _search_figure_bm25(self, figure_id: str, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Perform BM25 search for a figure using cached index with top matching words."""
        try:
            # Get BM25 index (builds from ChromaDB if not cached)
            bm25_index = self._get_bm25_index(figure_id)
            
            if not bm25_index:
                logging.warning(f"No BM25 index available for figure {figure_id}")
                return []
            
            # Process query
            query_tokens = text_processor.process_query(query)
            
            if not query_tokens:
                logging.warning("No tokens extracted from query")
                return []
            
            # Get BM25 scores
            scores = bm25_index.get_scores(query_tokens)
            
            # Get top results
            top_indices = np.argsort(scores)[::-1][:n_results]
            
            # Use cached metadata instead of querying ChromaDB
            cached_metadata = self.bm25_metadata_cache.get(figure_id, [])
            if not cached_metadata:
                logging.warning(f"No cached metadata for figure {figure_id}")
                return []
            
            # Get tokenized documents for finding matching words
            bm25_documents = self.bm25_documents_cache.get(figure_id, [])
            
            # Get documents from ChromaDB for the results
            collection = self.get_figure_collection(figure_id)
            if not collection:
                return []
            
            results = []
            for idx in top_indices:
                if idx < len(cached_metadata) and idx < len(scores) and scores[idx] > 0:
                    metadata = cached_metadata[idx]
                    doc_id = metadata.get("doc_id", f"doc_{idx}")
                    
                    # Get document text from ChromaDB
                    try:
                        chroma_results = collection.get(
                            ids=[doc_id],
                            include=["documents"]
                        )
                        text = ""
                        if chroma_results["documents"]:
                            text = chroma_results["documents"][0]
                    except Exception as e:
                        logging.warning(f"Could not retrieve text for doc_id {doc_id}: {e}")
                        text = ""
                    
                    # Calculate per-term BM25 scores and rank by importance
                    top_matching_words = []
                    if idx < len(bm25_documents):
                        doc_tokens = bm25_documents[idx]
                        term_scores = self._calculate_term_scores(bm25_index, query_tokens, doc_tokens, idx)
                        
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
                        "top_matching_words": top_matching_words,
                        "document_id": doc_id
                    })
            
            return results
        
        except Exception as e:
            logging.error(f"Error in BM25 search for figure {figure_id}: {e}")
            return []
    
    def _reciprocal_rank_fusion(self, vector_results: List[Dict[str, Any]], 
                               bm25_results: List[Dict[str, Any]], 
                               k: int = 60) -> List[Dict[str, Any]]:
        """Combine vector and BM25 results using Reciprocal Rank Fusion with both metrics."""
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
            
            # Add vector contribution
            if doc_id in vector_ranks:
                rrf_score += 1 / (k + vector_ranks[doc_id])
            
            # Add BM25 contribution
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
                # Store the original cosine similarity from vector search
                result["cosine_similarity"] = result.get("similarity", 0)
            else:
                result = bm25_results_map[doc_id].copy()
                # No vector match, cosine similarity is 0
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
            
            # Keep the unified similarity field for backward compatibility
            # Use cosine similarity as the primary metric
            result["similarity"] = result["cosine_similarity"]
            
            fused_results.append(result)
        
        return fused_results
    
    def clear_figure_documents(self, figure_id: str) -> bool:
        """
        Clear all documents from a figure's collection.
        
        Args:
            figure_id: Figure identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            collection_name = f"figure_{figure_id}"
            
            # Check if figure exists
            if not self.get_figure_metadata(figure_id):
                logging.error(f"Figure {figure_id} not found")
                return False
            
            # Delete and recreate the collection to clear all documents
            try:
                self.client.delete_collection(collection_name)
            except Exception as e:
                logging.warning(f"Collection {collection_name} may not exist: {e}")
            
            # Recreate empty collection
            self.client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            
            # Invalidate BM25 cache for this figure
            self._invalidate_bm25_cache(figure_id)
            
            # Update document count in figure metadata
            figure_metadata = self.get_figure_metadata(figure_id)
            if figure_metadata:
                figure_metadata["document_count"] = 0
                self.update_figure_metadata(figure_id, figure_metadata)
            
            logging.info(f"Cleared all documents from figure: {figure_id}")
            return True
        
        except Exception as e:
            logging.error(f"Error clearing documents for figure {figure_id}: {e}")
            return False
    
    def get_figure_stats(self, figure_id: str) -> Dict[str, Any]:
        """Get statistics for a figure's document collection."""
        try:
            collection = self.get_figure_collection(figure_id)
            if not collection:
                return {"error": "Figure not found"}
            
            metadata = self.get_figure_metadata(figure_id)
            return {
                "figure_id": figure_id,
                "name": metadata.get("name", "Unknown") if metadata else "Unknown",
                "document_count": collection.count(),
                "collection_name": f"figure_{figure_id}"
            }
        
        except Exception as e:
            logging.error(f"Error getting stats for figure {figure_id}: {e}")
            return {"error": str(e)}

# Global instance
figure_manager = None

def get_figure_manager() -> FigureManager:
    """Get or create global figure manager instance."""
    global figure_manager
    if figure_manager is None:
        figure_manager = FigureManager()
    return figure_manager
