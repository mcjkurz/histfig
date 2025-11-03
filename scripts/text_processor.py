"""
Text processing utilities for hybrid search system.
Handles Chinese segmentation with jieba and English lemmatization with NLTK.
"""

import re
import logging
from typing import List, Set
import jieba
import nltk
from nltk.stem import WordNetLemmatizer
import string

class TextProcessor:
    def __init__(self, stopwords_dir: str = "./data/stopwords"):
        """
        Initialize text processor with required NLTK data.
        
        Args:
            stopwords_dir: Directory containing stopword files
        """
        self._download_nltk_data()
        self.lemmatizer = WordNetLemmatizer()
        
        # Load stopwords from files (for display filtering only, not for indexing)
        self.stopwords = self._load_stopwords(stopwords_dir)
        
        logging.info(f"Text processor initialized with {len(self.stopwords)} stopwords")
    
    def _download_nltk_data(self):
        """Download required NLTK data if not present."""
        required_data = ['punkt', 'wordnet', 'averaged_perceptron_tagger']
        
        for data_name in required_data:
            try:
                nltk.data.find(f'tokenizers/{data_name}')
            except LookupError:
                try:
                    logging.info(f"Downloading NLTK data: {data_name}")
                    nltk.download(data_name, quiet=True)
                except Exception as e:
                    logging.warning(f"Failed to download NLTK data {data_name}: {e}")
    
    def _load_stopwords(self, stopwords_dir: str) -> Set[str]:
        """
        Load stopwords from text files in the stopwords directory.
        
        Args:
            stopwords_dir: Directory containing stopword files
            
        Returns:
            Set of stopwords
        """
        import os
        stopwords = set()
        
        if not os.path.exists(stopwords_dir):
            logging.warning(f"Stopwords directory not found: {stopwords_dir}")
            return stopwords
        
        # Load all .txt files in the stopwords directory
        for filename in os.listdir(stopwords_dir):
            if filename.endswith('.txt'):
                filepath = os.path.join(stopwords_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for line in f:
                            word = line.strip()
                            if word:  # Skip empty lines
                                stopwords.add(word.lower())
                    logging.debug(f"Loaded stopwords from {filename}")
                except Exception as e:
                    logging.warning(f"Error loading stopwords from {filename}: {e}")
        
        return stopwords
    
    def segment_text(self, text: str) -> List[str]:
        """
        Segment text using jieba for both Chinese and English content.
        
        Args:
            text: Input text
            
        Returns:
            List of segmented tokens
        """
        # Use jieba for segmentation (handles both Chinese and English)
        tokens = jieba.lcut(text)
        
        # Filter out whitespace and empty tokens
        filtered_tokens = []
        for token in tokens:
            token = token.strip()
            if token and not token.isspace():
                filtered_tokens.append(token)
        
        return filtered_tokens
    
    def lemmatize_tokens(self, tokens: List[str]) -> List[str]:
        """
        Lemmatize tokens using NLTK. Chinese tokens remain unchanged.
        Filters out URLs, long numbers, and footnote references.
        
        Args:
            tokens: List of segmented tokens
            
        Returns:
            List of lemmatized tokens
        """
        processed_tokens = []
        
        for token in tokens:
            token = token.lower()
            
            # Skip pure punctuation
            if token in string.punctuation or token in ["。", "，", "、", "：", "？", "！", "：", "；", "，", "、", "：", "？", "！", "：", "；"]:
                continue
                
            # Skip empty or whitespace tokens
            if not token or token.isspace():
                continue
            
            # Filter out long tokens (likely URLs)
            if len(token) > 24:
                continue
            
            # Filter out footnote references like [18], [19]
            if re.match(r'^\[\d+\]$', token):
                continue
            
            # Filter out long numbers (more than 4 digits)
            if token.isdigit() and len(token) > 4:
                continue
            
            # Lemmatize if it's alphabetic (English), otherwise keep as is (Chinese/mixed)
            if token.isalpha():
                try:
                    lemmatized = self.lemmatizer.lemmatize(token)
                    processed_tokens.append(lemmatized)
                except Exception as e:
                    logging.warning(f"Error lemmatizing token '{token}': {e}")
                    processed_tokens.append(token)
            else:
                # Keep alphanumeric tokens (like "covid-19", "3d", etc.) and Chinese tokens
                if any(c.isalnum() for c in token):
                    processed_tokens.append(token)
        
        return processed_tokens
    
    def generate_ngrams(self, tokens: List[str], n: int = 2) -> List[str]:
        """
        Generate n-grams from tokens.
        
        Args:
            tokens: List of tokens
            n: Size of n-gram (2 for bigrams, 3 for trigrams, etc.)
            
        Returns:
            List of n-grams as joined strings
        """
        if len(tokens) < n:
            return []
        
        ngrams = []
        for i in range(len(tokens) - n + 1):
            ngram = "_".join(tokens[i:i+n])
            ngrams.append(ngram)
        
        return ngrams
    
    def process_text(self, text: str, include_bigrams: bool = True) -> List[str]:
        """
        Process text using jieba segmentation followed by NLTK lemmatization.
        Optionally includes bigrams alongside unigrams.
        
        Args:
            text: Input text
            include_bigrams: Whether to include bigrams in output
            
        Returns:
            List of processed tokens (unigrams + bigrams if enabled)
        """
        if not text or not text.strip():
            return []
        
        # Segment text using jieba (handles both Chinese and English)
        tokens = self.segment_text(text)
        
        # Lemmatize tokens (English tokens get lemmatized, Chinese remain unchanged)
        processed_tokens = self.lemmatize_tokens(tokens)
        
        # Add bigrams if requested
        if include_bigrams and len(processed_tokens) >= 2:
            bigrams = self.generate_ngrams(processed_tokens, n=2)
            processed_tokens.extend(bigrams)
        
        return processed_tokens
    
    def process_query(self, query: str, include_bigrams: bool = True) -> List[str]:
        """
        Process a search query using the same logic as document processing.
        
        Args:
            query: Search query
            include_bigrams: Whether to include bigrams in output
            
        Returns:
            List of processed query tokens (unigrams + bigrams if enabled)
        """
        return self.process_text(query, include_bigrams=include_bigrams)
    
    def filter_stopwords(self, tokens: List[str]) -> List[str]:
        """
        Filter stopwords from a list of tokens (for display purposes only).
        Does NOT affect indexing or scoring.
        
        Args:
            tokens: List of tokens to filter
            
        Returns:
            List of tokens with stopwords removed
        """
        return [token for token in tokens if token.lower() not in self.stopwords]

# Global instance
text_processor = TextProcessor()
