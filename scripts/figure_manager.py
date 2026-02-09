"""
Figure Management System for Historical Figures Simulation
Handles CRUD operations for historical figures and their document collections.
Provides async wrappers for ChromaDB operations using asyncio.to_thread.
"""

import json
import shutil
import pickle
import asyncio
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
from pathlib import Path

logger = logging.getLogger('histfig')
import chromadb
from chromadb.config import Settings
import re
import numpy as np
from rank_bm25 import BM25Okapi
from config import MIN_COSINE_SIMILARITY, SEARCH_MULTIPLIER, MAX_SEARCH_RESULTS, RRF_K, FIGURES_DIR, CHROMA_DB_PATH
from text_processor import text_processor
from search_utils import reciprocal_rank_fusion
from embedding_provider import get_embedding_provider


class FigureManager:
    def __init__(self, figures_dir: str = "./figures", db_path: str = "./chroma_db"):
        """Initialize figure manager."""
        self.figures_dir = Path(figures_dir)
        self.db_path = db_path
        self.figures_dir.mkdir(exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        self.embedding_provider = get_embedding_provider()
        
        self.bm25_cache = {}
        self.bm25_documents_cache = {}
        self.bm25_metadata_cache = {}
        
        self.bm25_dir = Path(db_path) / "bm25_indexes"
        self.bm25_dir.mkdir(exist_ok=True)
        
        logger.info("Figure manager initialized")
    
    @staticmethod
    def _generate_doc_id(figure_id: str) -> str:
        """Generate a unique document ID using UUID."""
        return f"{figure_id}_{uuid.uuid4().hex[:12]}"
    
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
                
            logger.debug(f"Saved BM25 data to disk for figure {figure_id}")
        except Exception as e:
            logger.error(f"Error saving BM25 data for figure {figure_id}: {e}")
    
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
                
            logger.info(f"Loaded BM25 data from disk for figure {figure_id}")
            return True
        except Exception as e:
            logger.error(f"Error loading BM25 data for figure {figure_id}: {e}")
            return False
    
    def _invalidate_bm25_cache(self, figure_id: str):
        """Invalidate BM25 cache for a figure when documents change."""
        if figure_id in self.bm25_cache:
            del self.bm25_cache[figure_id]
        if figure_id in self.bm25_documents_cache:
            del self.bm25_documents_cache[figure_id]
        if figure_id in self.bm25_metadata_cache:
            del self.bm25_metadata_cache[figure_id]
            
        try:
            index_path, docs_path, meta_path = self._get_bm25_paths(figure_id)
            for path in [index_path, docs_path, meta_path]:
                if path.exists():
                    path.unlink()
        except Exception as e:
            logger.warning(f"Error removing BM25 files for figure {figure_id}: {e}")
            
        logger.debug(f"Invalidated BM25 cache for figure {figure_id}")
    
    async def invalidate_bm25_cache_async(self, figure_id: str):
        """Async wrapper for _invalidate_bm25_cache."""
        await asyncio.to_thread(self._invalidate_bm25_cache, figure_id)
    
    def preload_bm25_index(self, figure_id: str) -> bool:
        """Preload BM25 index for a figure from disk or build from ChromaDB."""
        try:
            if figure_id in self.bm25_cache:
                return True
            
            if self._load_bm25_from_disk(figure_id):
                return True
            
            return self._build_bm25_from_chromadb(figure_id)
            
        except Exception as e:
            logger.error(f"Error preloading BM25 index for figure {figure_id}: {e}")
            return False
    
    def _build_bm25_from_chromadb(self, figure_id: str) -> bool:
        """Build BM25 index from ChromaDB metadata."""
        try:
            collection = self.get_figure_collection(figure_id)
            if not collection:
                return False
            
            all_docs = collection.get(include=["metadatas"])
            if not all_docs["metadatas"]:
                logger.info(f"No documents found for figure {figure_id}")
                return False
            
            token_lists = []
            metadata_list = []
            
            for metadata in all_docs["metadatas"]:
                tokens_json = metadata.get("processed_tokens", "")
                if tokens_json:
                    try:
                        tokens = json.loads(tokens_json)
                        if tokens:
                            token_lists.append(tokens)
                            metadata_list.append(metadata)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Could not parse processed tokens: {e}")
                        continue
            
            if not token_lists:
                logger.info(f"No processed tokens found for figure {figure_id}")
                return False
            
            bm25_index = BM25Okapi(token_lists)
            
            self.bm25_cache[figure_id] = bm25_index
            self.bm25_documents_cache[figure_id] = token_lists
            self.bm25_metadata_cache[figure_id] = metadata_list
            
            self._save_bm25_to_disk(figure_id)
            
            logger.info(f"Built and cached BM25 index for figure {figure_id}: {len(token_lists)} documents")
            return True
            
        except Exception as e:
            logger.error(f"Error building BM25 index for figure {figure_id}: {e}")
            return False
    
    def _get_bm25_index(self, figure_id: str) -> Optional[BM25Okapi]:
        """Get BM25 index for a figure, preloading if necessary."""
        if figure_id not in self.bm25_cache:
            if not self.preload_bm25_index(figure_id):
                return None
        return self.bm25_cache.get(figure_id)

    def create_figure(self, figure_id: str, name: str, description: str = "", 
                     personality_prompt: str = "", metadata: Dict[str, Any] = None) -> bool:
        """Create a new historical figure with validation."""
        try:
            if not re.match(r'^[a-zA-Z]+$', figure_id):
                logger.error(f"Invalid figure_id format: {figure_id}")
                return False
            
            if re.search(r'[0-9!@#$%^&*()_+=\[\]{};:\'",.<>?/\\|`~]', name):
                logger.error(f"Invalid name format: {name}")
                return False
            
            description = description[:400] if description else ""
            personality_prompt = personality_prompt[:400] if personality_prompt else ""
            
            figure_path = self.figures_dir / figure_id
            
            if figure_path.exists():
                logger.error(f"Figure {figure_id} already exists")
                return False
            
            figure_path.mkdir(exist_ok=True)
            
            figure_metadata = {
                "figure_id": figure_id,
                "name": name,
                "description": description,
                "personality_prompt": personality_prompt,
                "created_at": datetime.now().isoformat(),
                "document_count": 0,
                "metadata": metadata or {}
            }
            
            metadata_file = figure_path / "metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(figure_metadata, f, indent=2, ensure_ascii=False)
            
            collection_name = f"figure_{figure_id}"
            self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine", "figure_id": figure_id}
            )
            
            logger.info(f"Created figure: {name} ({figure_id})")
            return True
            
        except Exception as e:
            logger.error(f"Error creating figure {figure_id}: {e}")
            return False

    # Async wrapper
    async def create_figure_async(self, figure_id: str, name: str, description: str = "",
                                  personality_prompt: str = "", metadata: Dict[str, Any] = None) -> bool:
        """Async wrapper for create_figure."""
        return await asyncio.to_thread(
            self.create_figure, figure_id, name, description, personality_prompt, metadata
        )
    
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
                            logger.warning(f"Invalid metadata file for figure: {figure_dir.name}")
                            continue
            
            return sorted(figures, key=lambda x: x.get('name', ''))
        
        except Exception as e:
            logger.error(f"Error getting figure list: {e}")
            return []

    # Async wrapper
    async def get_figure_list_async(self) -> List[Dict[str, Any]]:
        """Async wrapper for get_figure_list."""
        return await asyncio.to_thread(self.get_figure_list)
    
    def get_figure_metadata(self, figure_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific figure."""
        try:
            metadata_file = self.figures_dir / figure_id / "metadata.json"
            if not metadata_file.exists():
                return None
            
            with open(metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        except Exception as e:
            logger.error(f"Error getting metadata for figure {figure_id}: {e}")
            return None

    # Async wrapper
    async def get_figure_metadata_async(self, figure_id: str) -> Optional[Dict[str, Any]]:
        """Async wrapper for get_figure_metadata."""
        return await asyncio.to_thread(self.get_figure_metadata, figure_id)
    
    def update_figure_metadata(self, figure_id: str, updates: Dict[str, Any]) -> bool:
        """Update metadata for a figure with validation."""
        try:
            metadata = self.get_figure_metadata(figure_id)
            if not metadata:
                logger.error(f"Figure {figure_id} not found")
                return False
            
            if 'name' in updates and updates['name']:
                if re.search(r'[0-9!@#$%^&*()_+=\[\]{};:\'",.<>?/\\|`~]', updates['name']):
                    logger.error(f"Invalid name format: {updates['name']}")
                    return False
            
            if 'description' in updates:
                updates['description'] = updates['description'][:400] if updates['description'] else ""
            if 'personality_prompt' in updates:
                updates['personality_prompt'] = updates['personality_prompt'][:400] if updates['personality_prompt'] else ""
            
            metadata.update(updates)
            
            metadata_file = self.figures_dir / figure_id / "metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Updated metadata for figure: {figure_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error updating metadata for figure {figure_id}: {e}")
            return False

    # Async wrapper
    async def update_figure_metadata_async(self, figure_id: str, updates: Dict[str, Any]) -> bool:
        """Async wrapper for update_figure_metadata."""
        return await asyncio.to_thread(self.update_figure_metadata, figure_id, updates)
    
    def delete_figure(self, figure_id: str) -> bool:
        """Delete a figure and all its data: collection, files, BM25 cache, and image."""
        try:
            figure_path = self.figures_dir / figure_id
            if not figure_path.exists():
                logger.error(f"Figure {figure_id} not found")
                return False
            
            # Delete ChromaDB collection
            collection_name = f"figure_{figure_id}"
            try:
                self.client.delete_collection(collection_name)
            except Exception as e:
                logger.warning(f"Error deleting collection {collection_name}: {e}")
            
            # Invalidate BM25 cache and remove pickle files
            self._invalidate_bm25_cache(figure_id)
            
            # Remove figure image if it exists
            try:
                figure_images_dir = self.figures_dir.parent / "static" / "figure_images"
                if figure_images_dir.exists():
                    for img_file in figure_images_dir.iterdir():
                        if img_file.stem == figure_id:
                            img_file.unlink()
                            logger.debug(f"Removed figure image: {img_file}")
                            break
            except Exception as e:
                logger.warning(f"Error removing figure image for {figure_id}: {e}")
            
            # Remove figure directory (metadata.json, etc.)
            shutil.rmtree(figure_path)
            
            logger.info(f"Deleted figure: {figure_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error deleting figure {figure_id}: {e}")
            return False

    # Async wrapper
    async def delete_figure_async(self, figure_id: str) -> bool:
        """Async wrapper for delete_figure."""
        return await asyncio.to_thread(self.delete_figure, figure_id)
    
    def get_figure_collection(self, figure_id: str):
        """Get ChromaDB collection for a figure."""
        try:
            collection_name = f"figure_{figure_id}"
            return self.client.get_collection(collection_name)
        except Exception as e:
            logger.error(f"Error getting collection for figure {figure_id}: {e}")
            return None
    
    def add_document_to_figure(self, figure_id: str, text: str, metadata: Dict[str, Any]) -> Optional[str]:
        """Add a document chunk to a figure's collection.
        
        Stores the chunk text, embedding, and processed tokens in ChromaDB.
        BM25 index is NOT rebuilt here — call invalidate_bm25_cache() after
        the entire upload batch completes, and BM25 will rebuild lazily on next search.
        """
        try:
            collection = self.get_figure_collection(figure_id)
            if not collection:
                logger.error(f"Collection not found for figure: {figure_id}")
                return None
            
            embedding = self.embedding_provider.encode_document_sync(text)
            
            doc_id = self._generate_doc_id(figure_id)
            
            processed_tokens = text_processor.process_text(text)
            
            metadata_with_id = {**metadata, "doc_id": doc_id}
            if processed_tokens:
                metadata_with_id["processed_tokens"] = json.dumps(processed_tokens)
                logger.debug(f"Added {len(processed_tokens)} processed tokens to metadata for {doc_id}")
            else:
                logger.warning(f"No tokens extracted for {doc_id}, BM25 search may be limited")
            
            collection.add(
                documents=[text],
                embeddings=[embedding],
                metadatas=[metadata_with_id],
                ids=[doc_id]
            )
            
            logger.debug(f"Added document to figure {figure_id}: {doc_id}")
            return doc_id
        
        except Exception as e:
            logger.error(f"Error adding document to figure {figure_id}: {e}")
            return None

    # Async wrapper
    async def add_document_to_figure_async(self, figure_id: str, text: str, metadata: Dict[str, Any]) -> Optional[str]:
        """Async wrapper for add_document_to_figure."""
        return await asyncio.to_thread(self.add_document_to_figure, figure_id, text, metadata)
    
    def sync_document_count(self, figure_id: str) -> bool:
        """Sync the document count in metadata with the actual collection count."""
        try:
            collection = self.get_figure_collection(figure_id)
            if not collection:
                return False
            
            figure_metadata = self.get_figure_metadata(figure_id)
            if figure_metadata:
                figure_metadata["document_count"] = collection.count()
                self.update_figure_metadata(figure_id, figure_metadata)
                logger.info(f"Synced document count for {figure_id}: {collection.count()}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error syncing document count for {figure_id}: {e}")
            return False

    # Async wrapper
    async def sync_document_count_async(self, figure_id: str) -> bool:
        """Async wrapper for sync_document_count."""
        return await asyncio.to_thread(self.sync_document_count, figure_id)
    
    def search_figure_documents(self, figure_id: str, query: str, n_results: int = 5, 
                               min_cosine_similarity: float = MIN_COSINE_SIMILARITY) -> List[Dict[str, Any]]:
        """Search for similar documents in a figure's collection using hybrid search."""
        try:
            self.preload_bm25_index(figure_id)
            
            extended_n_results = min(n_results * SEARCH_MULTIPLIER, MAX_SEARCH_RESULTS)
            
            vector_results = self._search_figure_vector(figure_id, query, extended_n_results)
            
            filtered_vector_results = [
                r for r in vector_results 
                if r.get("similarity", 0) >= min_cosine_similarity
            ]
            
            logger.info(f"Figure {figure_id} vector search: {len(vector_results)} results, "
                        f"{len(filtered_vector_results)} after filtering (min similarity: {min_cosine_similarity})")
            
            if not filtered_vector_results:
                logger.warning(f"No results with sufficient cosine similarity found for figure {figure_id}")
                return []
            
            bm25_results = self._search_figure_bm25(figure_id, query, extended_n_results)
            
            logger.info(f"Figure {figure_id} hybrid search: vector={len(filtered_vector_results)}, bm25={len(bm25_results)} results")
            
            fused_results = reciprocal_rank_fusion(filtered_vector_results, bm25_results, k=RRF_K)
            
            final_results = [
                r for r in fused_results 
                if r.get("cosine_similarity", 0) >= min_cosine_similarity
            ]
            
            return final_results[:n_results]
        
        except Exception as e:
            logger.error(f"Error in hybrid search for figure {figure_id}: {e}")
            return []

    # Async wrapper
    async def search_figure_documents_async(self, figure_id: str, query: str, n_results: int = 5,
                                           min_cosine_similarity: float = MIN_COSINE_SIMILARITY) -> List[Dict[str, Any]]:
        """Async wrapper for search_figure_documents."""
        return await asyncio.to_thread(
            self.search_figure_documents, figure_id, query, n_results, min_cosine_similarity
        )
    
    def _search_figure_vector(self, figure_id: str, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Perform vector search for a figure."""
        try:
            collection = self.get_figure_collection(figure_id)
            if not collection:
                return []
            
            query_embedding = self.embedding_provider.encode_query_sync(query)
            
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )
            
            formatted_results = []
            if results["documents"] and results["documents"][0]:
                for i in range(len(results["documents"][0])):
                    metadata = results["metadatas"][0][i]
                    doc_id = metadata.get("doc_id", f"doc_{i}")
                    distance = results["distances"][0][i]
                    similarity = 1.0 - distance
                    
                    formatted_results.append({
                        "text": results["documents"][0][i],
                        "metadata": metadata,
                        "similarity": similarity,
                        "document_id": doc_id
                    })
            
            return formatted_results
        
        except Exception as e:
            logger.error(f"Error in vector search for figure {figure_id}: {e}")
            return []
    
    def _calculate_term_scores(self, bm25_index, query_tokens: List[str], doc_tokens: List[str], doc_idx: int) -> Dict[str, float]:
        """Calculate BM25 contribution score for each query term in a document."""
        term_scores = {}
        
        if not bm25_index:
            return term_scores
        
        doc_len = len(doc_tokens)
        avgdl = bm25_index.avgdl
        
        k1 = bm25_index.k1
        b = bm25_index.b
        
        for term in query_tokens:
            if term in doc_tokens:
                tf = doc_tokens.count(term)
                
                if hasattr(bm25_index, 'idf') and term in bm25_index.idf:
                    idf = bm25_index.idf[term]
                else:
                    idf = 0
                
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * doc_len / avgdl)
                term_score = idf * (numerator / denominator)
                
                term_scores[term] = term_score
        
        return term_scores
    
    def _search_figure_bm25(self, figure_id: str, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Perform BM25 search for a figure using cached index with top matching words."""
        try:
            bm25_index = self._get_bm25_index(figure_id)
            
            if not bm25_index:
                logger.warning(f"No BM25 index available for figure {figure_id}")
                return []
            
            query_tokens = text_processor.process_query(query)
            
            if not query_tokens:
                logger.warning("No tokens extracted from query")
                return []
            
            scores = bm25_index.get_scores(query_tokens)
            
            top_indices = np.argsort(scores)[::-1][:n_results]
            
            cached_metadata = self.bm25_metadata_cache.get(figure_id, [])
            if not cached_metadata:
                logger.warning(f"No cached metadata for figure {figure_id}")
                return []
            
            bm25_documents = self.bm25_documents_cache.get(figure_id, [])
            
            collection = self.get_figure_collection(figure_id)
            if not collection:
                return []
            
            results = []
            for idx in top_indices:
                if idx < len(cached_metadata) and idx < len(scores) and scores[idx] > 0:
                    metadata = cached_metadata[idx]
                    doc_id = metadata.get("doc_id", f"doc_{idx}")
                    
                    try:
                        chroma_results = collection.get(
                            ids=[doc_id],
                            include=["documents"]
                        )
                        text = ""
                        if chroma_results["documents"]:
                            text = chroma_results["documents"][0]
                    except Exception as e:
                        logger.warning(f"Could not retrieve text for doc_id {doc_id}: {e}")
                        text = ""
                    
                    top_matching_words = []
                    if idx < len(bm25_documents):
                        doc_tokens = bm25_documents[idx]
                        term_scores = self._calculate_term_scores(bm25_index, query_tokens, doc_tokens, idx)
                        
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
                        "top_matching_words": top_matching_words,
                        "document_id": doc_id
                    })
            
            return results
        
        except Exception as e:
            logger.error(f"Error in BM25 search for figure {figure_id}: {e}")
            return []
    
    def clear_figure_documents(self, figure_id: str) -> bool:
        """Clear all documents from a figure's collection."""
        try:
            collection_name = f"figure_{figure_id}"
            
            if not self.get_figure_metadata(figure_id):
                logger.error(f"Figure {figure_id} not found")
                return False
            
            try:
                self.client.delete_collection(collection_name)
            except Exception as e:
                logger.warning(f"Collection {collection_name} may not exist: {e}")
            
            self.client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine", "figure_id": figure_id}
            )
            
            self._invalidate_bm25_cache(figure_id)
            
            figure_metadata = self.get_figure_metadata(figure_id)
            if figure_metadata:
                figure_metadata["document_count"] = 0
                self.update_figure_metadata(figure_id, figure_metadata)
            
            logger.info(f"Cleared all documents from figure: {figure_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error clearing documents for figure {figure_id}: {e}")
            return False

    # Async wrapper
    async def clear_figure_documents_async(self, figure_id: str) -> bool:
        """Async wrapper for clear_figure_documents."""
        return await asyncio.to_thread(self.clear_figure_documents, figure_id)
    
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
            logger.error(f"Error getting stats for figure {figure_id}: {e}")
            return {"error": str(e)}

    # Async wrapper
    async def get_figure_stats_async(self, figure_id: str) -> Dict[str, Any]:
        """Async wrapper for get_figure_stats."""
        return await asyncio.to_thread(self.get_figure_stats, figure_id)


# Global instance
figure_manager = None


def get_figure_manager() -> FigureManager:
    """Get or create global figure manager instance."""
    global figure_manager
    if figure_manager is None:
        figure_manager = FigureManager(figures_dir=FIGURES_DIR, db_path=CHROMA_DB_PATH)
    return figure_manager
