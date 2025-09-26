"""
Document processing utilities for extracting text from PDFs and text files,
and chunking them for vector storage.
"""

import os
import re
from typing import List, Dict, Any
import PyPDF2
import logging
from io import BytesIO

class DocumentProcessor:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        """
        Initialize document processor.
        
        Args:
            chunk_size: Target size for text chunks (in characters)
            chunk_overlap: Overlap between chunks (in characters)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def extract_text_from_pdf(self, file_content: bytes) -> str:
        """
        Extract text from PDF file content.
        
        Args:
            file_content: PDF file content as bytes
            
        Returns:
            Extracted text
        """
        try:
            pdf_file = BytesIO(file_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            text = ""
            for page in pdf_reader.pages:
                try:
                    page_text = page.extract_text()
                    if page_text.strip():
                        text += page_text
                except Exception as e:
                    logging.warning(f"Error extracting text from page: {e}")
                    continue
            
            return text
        except Exception as e:
            logging.error(f"Error extracting text from PDF: {e}")
            raise Exception(f"Failed to extract text from PDF: {str(e)}")
    
    def extract_text_from_txt(self, file_content: bytes) -> str:
        """
        Extract text from text file content.
        
        Args:
            file_content: Text file content as bytes
            
        Returns:
            Extracted text
        """
        try:
            # Try different encodings
            encodings = ['utf-8', 'utf-16', 'latin-1', 'cp1252']
            
            for encoding in encodings:
                try:
                    text = file_content.decode(encoding)
                    return text
                except UnicodeDecodeError:
                    continue
            
            # If all encodings fail, use utf-8 with error handling
            text = file_content.decode('utf-8', errors='replace')
            return text
            
        except Exception as e:
            logging.error(f"Error extracting text from text file: {e}")
            raise Exception(f"Failed to extract text from text file: {str(e)}")
    
    
    def clean_text(self, text: str) -> str:
        """
        Clean and normalize text by removing newlines and normalizing whitespace.
        
        Args:
            text: Raw text
            
        Returns:
            Cleaned text as one long string without newlines
        """
        # Remove all newlines and normalize whitespace
        text = text.replace('\n', ' ').replace('\r', ' ')
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def chunk_text(self, text: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Split text into chunks by max length after removing all newlines.
        
        Args:
            text: Text to chunk
            metadata: Base metadata for all chunks
            
        Returns:
            List of text chunks with metadata
        """
        if metadata is None:
            metadata = {}
        
        # Clean text to create one long string without newlines
        text = self.clean_text(text)
        
        if len(text) <= self.chunk_size:
            # Text is small enough to be a single chunk
            return [{
                "text": text,
                "metadata": {**metadata, "chunk_index": 0, "total_chunks": 1}
            }]
        
        chunks = []
        chunk_index = 0
        start = 0
        
        while start < len(text):
            # Determine end position for this chunk
            end = start + self.chunk_size
            
            if end >= len(text):
                # Last chunk - take remaining text
                chunk_text = text[start:]
            else:
                # Try to break at word boundary
                chunk_text = text[start:end]
                # Find the last space to avoid breaking words
                last_space = chunk_text.rfind(' ')
                if last_space != -1 and last_space > start + self.chunk_size // 2:
                    # Break at word boundary if it's not too far back
                    chunk_text = text[start:start + last_space]
                    end = start + last_space + 1  # +1 to skip the space
                else:
                    # No good word boundary found, use the full chunk
                    end = start + self.chunk_size
            
            chunks.append({
                "text": chunk_text.strip(),
                "metadata": {**metadata, "chunk_index": chunk_index}
            })
            
            # Move to next chunk with overlap
            if self.chunk_overlap > 0 and end < len(text):
                start = end - self.chunk_overlap
            else:
                start = end
            
            chunk_index += 1
        
        # Update total_chunks in all metadata
        total_chunks = len(chunks)
        for chunk in chunks:
            chunk["metadata"]["total_chunks"] = total_chunks
        
        return chunks
    
    
    def process_file(self, file_content: bytes, filename: str, file_type: str) -> List[Dict[str, Any]]:
        """
        Process a file and return text chunks with metadata.
        
        Args:
            file_content: File content as bytes
            filename: Original filename
            file_type: File type ('pdf' or 'txt')
            
        Returns:
            List of processed text chunks
        """
        try:
            # Extract text based on file type
            if file_type.lower() == 'pdf':
                text = self.extract_text_from_pdf(file_content)
            elif file_type.lower() in ['txt', 'text']:
                text = self.extract_text_from_txt(file_content)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")
            
            if not text.strip():
                raise ValueError("No text content found in file")
            
            # Create base metadata
            base_metadata = {
                "filename": filename,
                "file_type": file_type,
                "file_size": len(file_content),
                "text_length": len(text)
            }
            
            # Chunk the text
            chunks = self.chunk_text(text, base_metadata)
            
            logging.info(f"Processed {filename}: {len(chunks)} chunks created")
            return chunks
            
        except Exception as e:
            logging.error(f"Error processing file {filename}: {e}")
            raise Exception(f"Failed to process {filename}: {str(e)}")

# Global instance
document_processor = DocumentProcessor()
