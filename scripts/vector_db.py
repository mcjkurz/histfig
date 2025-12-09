"""
Vector database module using ChromaDB for document storage and retrieval.
Handles document embeddings and similarity search for RAG functionality.
"""

import os
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import uuid
from typing import List, Dict, Any, Optional
import logging
import torch
import json
from config import EMBEDDING_MODEL, CHROMA_DB_PATH

class VectorDatabase:
    def __init__(self, db_path: str = "./chroma_db", model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize vector database with ChromaDB and sentence transformer model.
        
        Args:
            db_path: Path to store ChromaDB data
            model_name: Sentence transformer model for embeddings
        """
        self.db_path = db_path
        self.model_name = model_name
        self.chunk_counter_file = os.path.join(db_path, "chunk_counter.json")
        
        # Detect best available device
        # For testing, force CPU to avoid accelerate dependency issues
        if model_name == "all-MiniLM-L6-v2":
            self.device = "cpu"
            logging.info("Using CPU for embeddings (test mode)")
        elif torch.backends.mps.is_available():
            self.device = "mps"  # Apple Silicon GPU
            logging.info("Using Apple Silicon GPU (MPS) for embeddings")
        elif torch.cuda.is_available():
            self.device = "cuda"  # NVIDIA GPU
            logging.info("Using CUDA GPU for embeddings")
        else:
            self.device = "cpu"  # CPU fallback
            logging.info("Using CPU for embeddings")
        
        # Initialize sentence transformer with proper device handling
        self.encoder = self._initialize_sentence_transformer(model_name)
        logging.info(f"Initialized SentenceTransformer '{model_name}' on device: {self.device}")
        
        # Initialize database components
        self._initialize_database()
    
    def _initialize_sentence_transformer(self, model_name: str) -> SentenceTransformer:
        """Initialize SentenceTransformer with device handling and model-specific configurations."""
        # Handle special models that might need additional parameters
        model_kwargs = {}
        tokenizer_kwargs = {}
        
        # Check if it's a Qwen model and add recommended settings
        if "qwen" in model_name.lower():
            model_kwargs = {
                "attn_implementation": "flash_attention_2", 
                "device_map": "auto"
            }
            tokenizer_kwargs = {"padding_side": "left"}
            logging.info(f"Detected Qwen model, using optimized settings")
        
        try:
            # Try to initialize with device parameter and model-specific settings
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
                # Fallback: Initialize without device, then move
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
                # Final fallback to CPU
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
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=self.db_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"}
        )
        
        # Initialize chunk counter
        self._initialize_chunk_counter()
        
        logging.info(f"Vector database initialized with {self.collection.count()} documents")
    
    def _encode_text(self, text: str):
        """Encode document text with model-specific handling."""
        with torch.no_grad():
            # For Qwen models, encode documents without special prompts
            if "qwen" in self.model_name.lower():
                return self.encoder.encode(text)
            else:
                return self.encoder.encode(text)
    
    def _encode_query(self, query: str):
        """Encode query text with model-specific handling."""
        with torch.no_grad():
            # For Qwen models, use the query prompt if available
            if "qwen" in self.model_name.lower():
                try:
                    # Try to use the query prompt if the model supports it
                    return self.encoder.encode(query, prompt_name="query")
                except:
                    # Fallback to regular encoding if prompt doesn't exist
                    return self.encoder.encode(query)
            else:
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
    
    def add_document(self, text: str, metadata: Dict[str, Any]) -> int:
        """
        Add a document chunk to the vector database.
        
        Args:
            text: Document text content
            metadata: Document metadata (filename, page, etc.)
            
        Returns:
            Absolute chunk ID (integer)
        """
        # Get next sequential chunk ID
        chunk_id = self._get_next_chunk_id()
        doc_id = str(chunk_id)
        
        # Add chunk ID to metadata
        metadata_with_id = {**metadata, "absolute_chunk_id": chunk_id}
        
        # Generate embedding
        embedding = self._encode_text(text).tolist()
        
        # Add to collection
        self.collection.add(
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata_with_id],
            ids=[doc_id]
        )
        
        logging.info(f"Added document chunk with ID: {chunk_id}")
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
        # Generate query embedding
        query_embedding = self._encode_query(query).tolist()
        
        # Search in collection
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        # Format results
        formatted_results = []
        if results["documents"] and results["documents"][0]:
            for i in range(len(results["documents"][0])):
                metadata = results["metadatas"][0][i]
                # Convert cosine distance to similarity score
                # ChromaDB returns cosine distance = 1 - cosine_similarity
                # distance 0 = identical (similarity 1), distance 2 = opposite (similarity -1)
                distance = results["distances"][0][i]
                similarity = 1.0 - distance  # Range: [-1, 1]
                
                formatted_results.append({
                    "text": results["documents"][0][i],
                    "metadata": metadata,
                    "similarity": similarity,
                    "chunk_id": metadata.get("absolute_chunk_id", 0)  # Use stored absolute chunk ID
                })
        
        return formatted_results
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the document collection."""
        try:
            count = self.collection.count()
            return {
                "total_documents": count,
                "model_name": self.model_name,
                "db_path": self.db_path
            }
        except Exception as e:
            logging.error(f"Error getting collection stats: {e}")
            return {
                "total_documents": 0,
                "model_name": self.model_name,
                "db_path": self.db_path,
                "error": str(e)
            }
    
    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document from the vector database.
        
        Args:
            doc_id: Document ID to delete
            
        Returns:
            True if successful
        """
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
            # Delete the collection and recreate it
            self.client.delete_collection("documents")
            self.collection = self.client.get_or_create_collection(
                name="documents",
                metadata={"hnsw:space": "cosine"}
            )
            
            # Reset chunk counter
            self.next_chunk_id = 0
            self._save_chunk_counter()
            
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

# Note: Global vector_db instance removed - system now uses:
# - get_hybrid_db() from hybrid_search.py for hybrid search functionality
# - FigureManager for per-figure vector stores
# The VectorDatabase class is still used as a base class for HybridSearchDatabase
