"""
Figure Management System for Historical Figures Simulation
Handles CRUD operations for historical figures and their document collections.
"""

import os
import json
import shutil
from typing import List, Dict, Any, Optional
import logging
from pathlib import Path
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import torch
import re
from config import EMBEDDING_MODEL

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
        logging.info(f"Figure manager initialized with device: {self.device}")
    
    def create_figure(self, figure_id: str, name: str, description: str = "", 
                     personality_prompt: str = "", metadata: Dict[str, Any] = None,
                     max_length: int = 500) -> bool:
        """
        Create a new historical figure with validation.
        
        Args:
            figure_id: Unique identifier for the figure (only alphabetic characters)
            name: Display name (only alphabetic characters and spaces)
            description: Description of the figure (max 400 chars)
            personality_prompt: Optional personality prompt (max 400 chars)
            metadata: Additional metadata (birth_year, death_year, etc.)
            max_length: Maximum length for document paragraphs (100-2000 chars)
            
        Returns:
            True if successful
        """
        try:
            # Additional validation at model level
            if not re.match(r'^[a-zA-Z]+$', figure_id):
                logging.error(f"Invalid figure_id format: {figure_id}")
                return False
            
            if not re.match(r'^[a-zA-Z\s]+$', name):
                logging.error(f"Invalid name format: {name}")
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
            documents_path = figure_path / "documents"
            documents_path.mkdir(exist_ok=True)
            
            # Validate and clamp max_length
            max_length = max(100, min(2000, max_length))
            
            # Create metadata file
            figure_metadata = {
                "figure_id": figure_id,
                "name": name,
                "description": description,
                "personality_prompt": personality_prompt,
                "created_at": str(Path().resolve()),
                "document_count": 0,
                "max_length": max_length,
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
            
            # Validate updates
            if 'name' in updates and updates['name']:
                if not re.match(r'^[a-zA-Z\s]+$', updates['name']):
                    logging.error(f"Invalid name format: {updates['name']}")
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
    
    def add_document_to_figure(self, figure_id: str, text: str, metadata: Dict[str, Any]) -> Optional[int]:
        """
        Add a document chunk to a figure's collection.
        
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
            
            # Generate embedding
            embedding = self.encoder.encode(text).tolist()
            
            # Generate unique document ID
            doc_id = f"{figure_id}_{collection.count()}"
            
            # Add to collection
            collection.add(
                documents=[text],
                embeddings=[embedding],
                metadatas=[metadata],
                ids=[doc_id]
            )
            
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
    
    def search_figure_documents(self, figure_id: str, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search for similar documents in a figure's collection.
        
        Args:
            figure_id: Figure identifier
            query: Search query
            n_results: Number of results to return
            
        Returns:
            List of similar documents
        """
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
                    # ChromaDB returns IDs by default in the results
                    doc_id = results.get("ids", [None])[0][i] if results.get("ids") and len(results["ids"]) > 0 and len(results["ids"][0]) > i else f"doc_{i}"
                    formatted_results.append({
                        "text": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "similarity": 1 - results["distances"][0][i],
                        "document_id": doc_id
                    })
            
            return formatted_results
        
        except Exception as e:
            logging.error(f"Error searching documents for figure {figure_id}: {e}")
            return []
    
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
