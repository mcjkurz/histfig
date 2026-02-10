"""
Text processing utilities for hybrid search system.
Handles Chinese segmentation with jieba and English lemmatization with NLTK.

Tokenizer abstraction:
    Subclass ``Tokenizer`` and pass an instance to ``TextProcessor`` to swap
    the segmentation backend without touching the rest of the pipeline.
"""

import re
import logging
from abc import ABC, abstractmethod
from typing import List, Set, Tuple

logger = logging.getLogger('histfig')
import nltk
from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet
import string


# ---------------------------------------------------------------------------
# Tokenizer abstraction
# ---------------------------------------------------------------------------

class Tokenizer(ABC):
    """Base class for tokenizers used by TextProcessor."""

    @abstractmethod
    def tokenize(self, text: str) -> List[str]:
        """
        Split *text* into a list of tokens.

        The returned tokens may include whitespace or empty strings —
        TextProcessor will filter those out downstream.
        """
        ...

    def warmup(self) -> None:
        """Optional: pre-load heavy resources so the first real call is fast."""
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__


class JiebaTokenizer(Tokenizer):
    """Tokenizer backed by jieba (Chinese + English segmentation)."""

    def tokenize(self, text: str) -> List[str]:
        import jieba
        return jieba.lcut(text)

    def warmup(self) -> None:
        import jieba
        jieba.lcut("测试句子 test sentence")


class TextProcessor:
    def __init__(self, stopwords_dir: str = "./data/stopwords", tokenizer: Tokenizer = None):
        """
        Initialize text processor with character-based chunking.
        
        Args:
            stopwords_dir: Directory containing stopword files
            tokenizer: Tokenizer instance to use for segmentation.
                        Defaults to JiebaTokenizer if not provided.
        """
        self.tokenizer = tokenizer or JiebaTokenizer()
        self._download_nltk_data()
        self.lemmatizer = WordNetLemmatizer()
        
        # Load stopwords from files (used for filtering n-grams at indexing time)
        self.stopwords = self._load_stopwords(stopwords_dir)
        
        logger.info(f"Text processor initialized with {len(self.stopwords)} stopwords "
                     f"(tokenizer: {self.tokenizer.name})")
    
    def _download_nltk_data(self):
        """Download required NLTK data if not present."""
        # (resource_id, search_prefix) — search_prefix is used by nltk.data.find()
        required_data = [
            ('punkt', 'tokenizers'),
            ('punkt_tab', 'tokenizers'),
            ('wordnet', 'corpora'),
            ('averaged_perceptron_tagger_eng', 'taggers'),
        ]
        
        for data_name, prefix in required_data:
            try:
                nltk.data.find(f'{prefix}/{data_name}')
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
        Segment text using the configured tokenizer.
        
        Args:
            text: Input text
            
        Returns:
            List of segmented tokens (whitespace / empty tokens removed)
        """
        tokens = self.tokenizer.tokenize(text)
        
        # Filter out whitespace and empty tokens
        filtered_tokens = []
        for token in tokens:
            token = token.strip()
            if token and not token.isspace():
                filtered_tokens.append(token)
        
        return filtered_tokens
    
    @staticmethod
    def _penn_to_wordnet(tag: str):
        """Convert Penn Treebank POS tag to WordNet POS tag."""
        if tag.startswith('J'):
            return wordnet.ADJ
        elif tag.startswith('V'):
            return wordnet.VERB
        elif tag.startswith('R'):
            return wordnet.ADV
        else:
            return wordnet.NOUN  # default

    def lemmatize_tokens(self, tokens: List[str]) -> List[str]:
        """
        Lemmatize tokens using NLTK with POS tagging for accurate results.
        Chinese tokens remain unchanged.
        Filters out URLs, long numbers, and footnote references.
        
        Args:
            tokens: List of segmented tokens
            
        Returns:
            List of lemmatized tokens
        """
        # Separate English-alphabetic tokens from others so we can POS-tag
        # the English tokens in one batch (much faster than one-by-one).
        english_tokens = []   # (index, lowered_token)
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

            if token.isalpha() and token.isascii():
                # Collect English tokens for batch POS tagging
                english_tokens.append((len(processed_tokens), token))
                processed_tokens.append(token)  # placeholder
            elif token.isalpha():
                # Non-ASCII alphabetic (Chinese, etc.) — keep as-is
                processed_tokens.append(token)
            else:
                # Keep alphanumeric tokens (like "covid-19", "3d", etc.) and Chinese tokens
                if any(c.isalnum() for c in token):
                    processed_tokens.append(token)

        # Batch POS-tag all English tokens and lemmatize with the correct POS
        if english_tokens:
            words = [t for _, t in english_tokens]
            try:
                tagged = nltk.pos_tag(words)
            except Exception as e:
                logger.warning(f"POS tagging failed, falling back to noun-only lemmatization: {e}")
                tagged = [(w, 'NN') for w in words]

            for (idx, token), (_, tag) in zip(english_tokens, tagged):
                wn_pos = self._penn_to_wordnet(tag)
                try:
                    processed_tokens[idx] = self.lemmatizer.lemmatize(token, pos=wn_pos)
                except Exception as e:
                    logger.warning(f"Error lemmatizing token '{token}': {e}")
                    # placeholder already contains the original token

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
        Process text using tokenizer segmentation followed by NLTK lemmatization.
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
        
        # Segment text using the configured tokenizer
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
