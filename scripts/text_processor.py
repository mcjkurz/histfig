"""
Text processing utilities for hybrid search system.
Handles Chinese segmentation with jieba and English lemmatization with NLTK.
"""

import re
import logging
from typing import List, Set, Tuple

logger = logging.getLogger('histfig')
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
        
        # Load stopwords from files (used for filtering n-grams at indexing time)
        self.stopwords = self._load_stopwords(stopwords_dir)
        
        logger.info(f"Text processor initialized with {len(self.stopwords)} stopwords")
    
    def _download_nltk_data(self):
        """Download required NLTK data if not present."""
        required_data = ['punkt', 'wordnet', 'averaged_perceptron_tagger']
        
        for data_name in required_data:
            try:
                nltk.data.find(f'tokenizers/{data_name}')
            except LookupError:
                try:
                    logger.info(f"Downloading NLTK data: {data_name}")
                    nltk.download(data_name, quiet=True)
                except Exception as e:
                    logger.warning(f"Failed to download NLTK data {data_name}: {e}")
    
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
            logger.warning(f"Stopwords directory not found: {stopwords_dir}")
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
                    logger.debug(f"Loaded stopwords from {filename}")
                except Exception as e:
                    logger.warning(f"Error loading stopwords from {filename}: {e}")
        
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
            
            # Skip pure punctuation (Chinese and English)
            if token in string.punctuation or token in ["。", "，", "、", "：", "？", "！", "；"]:
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
            
            # Filter out single-letter English tokens (e.g., "s" from "Mao's", "t" from "don't")
            # These are typically artifacts from possessives/contractions and add no value
            if len(token) == 1 and token.isalpha() and token.isascii():
                continue
            
            # Lemmatize if it's alphabetic (English), otherwise keep as is (Chinese/mixed)
            if token.isalpha():
                try:
                    lemmatized = self.lemmatizer.lemmatize(token)
                    processed_tokens.append(lemmatized)
                except Exception as e:
                    logger.warning(f"Error lemmatizing token '{token}': {e}")
                    processed_tokens.append(token)
            else:
                # Keep alphanumeric tokens (like "covid-19", "3d", etc.) and Chinese tokens
                if any(c.isalnum() for c in token):
                    processed_tokens.append(token)
        
        return processed_tokens
    
    def generate_ngrams(self, tokens: List[str], n: int = 2, filter_stopwords: bool = True) -> List[str]:
        """
        Generate n-grams from tokens, optionally filtering those containing stopwords.
        
        Args:
            tokens: List of tokens
            n: Size of n-gram (2 for bigrams, 3 for trigrams, etc.)
            filter_stopwords: If True, exclude n-grams where any component is a stopword
            
        Returns:
            List of n-grams as joined strings (meaningful phrases only)
        """
        if len(tokens) < n:
            return []
        
        ngrams = []
        for i in range(len(tokens) - n + 1):
            components = tokens[i:i+n]
            
            # Filter n-grams containing stopwords (produces cleaner, more meaningful bigrams)
            if filter_stopwords:
                if any(comp.lower() in self.stopwords for comp in components):
                    continue
            
            ngram = "_".join(components)
            ngrams.append(ngram)
        
        return ngrams
    
    def process_text(self, text: str, ngram_range: Tuple[int, int] = (1, 2)) -> List[str]:
        """
        Process text using jieba segmentation followed by NLTK lemmatization.
        Generates n-grams within the specified range.
        
        Args:
            text: Input text
            ngram_range: Tuple of (min_n, max_n) for n-gram generation.
                         (1, 1) = unigrams only
                         (1, 2) = unigrams + bigrams (default)
                         (2, 2) = bigrams only
                         (1, 3) = unigrams + bigrams + trigrams
            
        Returns:
            List of processed tokens with n-grams in specified range
        """
        if not text or not text.strip():
            return []
        
        # Segment text using jieba (handles both Chinese and English)
        tokens = self.segment_text(text)
        
        # Lemmatize tokens (English tokens get lemmatized, Chinese remain unchanged)
        unigrams = self.lemmatize_tokens(tokens)
        
        # Generate n-grams for the specified range
        min_n, max_n = ngram_range
        result = []
        
        for n in range(min_n, max_n + 1):
            if n == 1:
                result.extend(unigrams)
            elif len(unigrams) >= n:
                result.extend(self.generate_ngrams(unigrams, n=n))
        
        return result
    
    def process_query(self, query: str, ngram_range: Tuple[int, int] = (1, 2)) -> List[str]:
        """
        Process a search query using the same logic as document processing.
        
        Args:
            query: Search query
            ngram_range: Tuple of (min_n, max_n) for n-gram generation
            
        Returns:
            List of processed query tokens with n-grams in specified range
        """
        return self.process_text(query, ngram_range=ngram_range)
    
# Global instance
text_processor = TextProcessor()
