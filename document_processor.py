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
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text.strip():
                        # Fix common character encoding issues from PDF extraction
                        page_text = self._fix_pdf_encoding_issues(page_text)
                        text += f"\n--- Page {page_num + 1} ---\n"
                        text += page_text
                except Exception as e:
                    logging.warning(f"Error extracting text from page {page_num + 1}: {e}")
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
    
    def _fix_pdf_encoding_issues(self, text: str) -> str:
        """
        Fix common character encoding issues from PDF extraction.
        
        Args:
            text: Raw text from PDF extraction
            
        Returns:
            Text with fixed encoding issues
        """
        # Dictionary of common problematic characters and their replacements
        replacements = {
            '\u25a0': '-',  # Black square (■) to hyphen
            '\u25aa': '-',  # Small black square to hyphen
            '\u25ab': '-',  # Small white square to hyphen
            '\u2022': '•',  # Bullet point
            '\u2013': '-',  # En dash to hyphen
            '\u2014': '--', # Em dash to double hyphen
            '\u2018': "'",  # Left single quote
            '\u2019': "'",  # Right single quote
            '\u201c': '"',  # Left double quote
            '\u201d': '"',  # Right double quote
            '\u2026': '...', # Ellipsis
            '\ufb01': 'fi', # fi ligature
            '\ufb02': 'fl', # fl ligature
            '\ufffd': '',   # Replacement character (remove)
            '\xa0': ' ',    # Non-breaking space
            '\u00ad': '-',  # Soft hyphen
            '\u2010': '-',  # Hyphen
            '\u2011': '-',  # Non-breaking hyphen
            '\u2012': '-',  # Figure dash
            '\u2015': '--', # Horizontal bar
            '■': '-',       # Direct black square character
            '□': '-',       # White square
            '▪': '-',       # Small black square
            '▫': '-',       # Small white square
        }
        
        # Apply replacements
        for old_char, new_char in replacements.items():
            text = text.replace(old_char, new_char)
        
        # Remove any remaining control characters except newlines and tabs
        text = ''.join(char if char.isprintable() or char in '\n\t' else ' ' for char in text)
        
        return text
    
    def clean_text(self, text: str, preserve_newlines: bool = True) -> str:
        """
        Clean and normalize text.
        
        Args:
            text: Raw text
            preserve_newlines: Whether to preserve newline structure
            
        Returns:
            Cleaned text
        """
        # Remove page numbers and headers (basic patterns)
        text = re.sub(r'--- Page \d+ ---', '', text)
        
        if preserve_newlines:
            # Preserve paragraph structure by keeping newlines
            # Remove excessive whitespace within lines but keep line breaks
            lines = text.split('\n')
            cleaned_lines = []
            for line in lines:
                # Clean each line individually
                cleaned_line = re.sub(r'\s+', ' ', line.strip())
                # Remove special characters but keep basic punctuation
                cleaned_line = re.sub(r'[^\w\s\.\,\!\?\;\:\-\(\)\[\]\"\']+', '', cleaned_line)
                cleaned_lines.append(cleaned_line)
            text = '\n'.join(cleaned_lines)
        else:
            # Original cleaning behavior - remove all newlines
            text = re.sub(r'\s+', ' ', text)
            text = re.sub(r'[^\w\s\.\,\!\?\;\:\-\(\)\[\]\"\']+', '', text)
            text = text.replace('\n', ' ').replace('\r', ' ')
        
        return text.strip()
    
    def chunk_text(self, text: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Split text into chunks based on document structure (passages/paragraphs).
        
        Strategy:
        1. First, split by passages (newlines) to respect document structure
        2. For short passages, combine them into coherent chunks
        3. For long passages with multiple sentences, split them appropriately
        4. Remove line breaks within chunks to create coherent single-line text
        
        Args:
            text: Text to chunk
            metadata: Base metadata for all chunks
            
        Returns:
            List of text chunks with metadata
        """
        if metadata is None:
            metadata = {}
        
        chunks = []
        text = self.clean_text(text, preserve_newlines=True)
        
        if len(text) <= self.chunk_size:
            # Text is small enough to be a single chunk
            # Remove line breaks to create coherent single-line text
            single_line_text = ' '.join(text.split())
            chunks.append({
                "text": single_line_text,
                "metadata": {**metadata, "chunk_index": 0, "total_chunks": 1}
            })
            return chunks
        
        # Split into passages/paragraphs (by newlines)
        passages = [p.strip() for p in text.split('\n') if p.strip()]
        
        current_chunk_passages = []
        current_chunk_length = 0
        chunk_index = 0
        
        for passage in passages:
            # Check if this passage alone exceeds chunk_size
            if len(passage) > self.chunk_size:
                # First, save any accumulated passages as a chunk
                if current_chunk_passages:
                    # Join passages with space and remove line breaks
                    chunk_text = ' '.join(current_chunk_passages)
                    chunk_text = ' '.join(chunk_text.split())
                    chunks.append({
                        "text": chunk_text,
                        "metadata": {**metadata, "chunk_index": chunk_index}
                    })
                    chunk_index += 1
                    current_chunk_passages = []
                    current_chunk_length = 0
                
                # Split the long passage by sentences
                long_passage_chunks = self._chunk_long_passage(passage, metadata, chunk_index)
                chunks.extend(long_passage_chunks)
                chunk_index += len(long_passage_chunks)
            else:
                # Check if adding this passage would exceed chunk_size
                passage_with_newline_length = len(passage) + (1 if current_chunk_passages else 0)
                
                if current_chunk_length + passage_with_newline_length > self.chunk_size and current_chunk_passages:
                    # Save current chunk
                    # Join passages with space and remove line breaks
                    chunk_text = ' '.join(current_chunk_passages)
                    chunk_text = ' '.join(chunk_text.split())
                    chunks.append({
                        "text": chunk_text,
                        "metadata": {**metadata, "chunk_index": chunk_index}
                    })
                    chunk_index += 1
                    
                    # Start new chunk with potential overlap
                    if self.chunk_overlap > 0 and current_chunk_passages:
                        # Include the last passage(s) as overlap if they fit within overlap size
                        overlap_passages = []
                        overlap_length = 0
                        for i in range(len(current_chunk_passages) - 1, -1, -1):
                            passage_len = len(current_chunk_passages[i]) + 1  # +1 for space
                            if overlap_length + passage_len <= self.chunk_overlap:
                                overlap_passages.insert(0, current_chunk_passages[i])
                                overlap_length += passage_len
                            else:
                                break
                        
                        current_chunk_passages = overlap_passages + [passage]
                        current_chunk_length = overlap_length + len(passage)
                    else:
                        current_chunk_passages = [passage]
                        current_chunk_length = len(passage)
                else:
                    # Add passage to current chunk
                    current_chunk_passages.append(passage)
                    current_chunk_length += passage_with_newline_length
        
        # Add the last chunk if it exists
        if current_chunk_passages:
            # Join passages with space and remove line breaks
            chunk_text = ' '.join(current_chunk_passages)
            chunk_text = ' '.join(chunk_text.split())
            chunks.append({
                "text": chunk_text,
                "metadata": {**metadata, "chunk_index": chunk_index}
            })
        
        # Update total_chunks in all metadata
        total_chunks = len(chunks)
        for chunk in chunks:
            chunk["metadata"]["total_chunks"] = total_chunks
        
        return chunks
    
    def _chunk_long_passage(self, passage: str, base_metadata: Dict[str, Any], start_chunk_index: int) -> List[Dict[str, Any]]:
        """
        Chunk a single passage that's longer than chunk_size by sentences.
        
        Args:
            passage: Long passage to chunk
            base_metadata: Base metadata for chunks
            start_chunk_index: Starting chunk index
            
        Returns:
            List of chunks from the passage
        """
        chunks = []
        
        # First, remove line breaks within the passage to create coherent text
        passage = ' '.join(passage.split())
        
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', passage)
        
        current_chunk = ""
        chunk_index = start_chunk_index
        
        for sentence in sentences:
            # Check if adding this sentence would exceed chunk size
            if len(current_chunk) + len(sentence) + 1 > self.chunk_size and current_chunk:
                # Save current chunk (already single-line)
                chunks.append({
                    "text": current_chunk.strip(),
                    "metadata": {**base_metadata, "chunk_index": chunk_index}
                })
                
                # Start new chunk with overlap
                if self.chunk_overlap > 0:
                    # Take the last part of current chunk as overlap
                    overlap_text = current_chunk[-self.chunk_overlap:]
                    # Find the start of a word to avoid cutting words
                    space_index = overlap_text.find(' ')
                    if space_index != -1:
                        overlap_text = overlap_text[space_index + 1:]
                    current_chunk = overlap_text + " " + sentence
                else:
                    current_chunk = sentence
                
                chunk_index += 1
            else:
                # Add sentence to current chunk
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
        
        # Add the last chunk if it exists
        if current_chunk.strip():
            chunks.append({
                "text": current_chunk.strip(),
                "metadata": {**base_metadata, "chunk_index": chunk_index}
            })
        
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
