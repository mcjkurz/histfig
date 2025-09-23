#!/usr/bin/env python3
"""Test script to demonstrate the improved character encoding fix for PDFs."""

from document_processor import DocumentProcessor

# Create a document processor
processor = DocumentProcessor()

# Simulate text that would come from a PDF with corrupted characters
sample_corrupted_text = """
a low■ranking official,

a single
hand■written letter that

Some other problematic characters:
- En dash – should become hyphen
- Em dash — should become double hyphen
- Smart quotes "like these" and 'these'
- Ellipsis… should become three dots
- Ligatures: ﬁle and ﬂow
- Black squares: ■ □ ▪ ▫
- Various dashes: ‐ ‑ ‒ ―
"""

print("Original text (with corrupted characters):")
print("-" * 50)
print(sample_corrupted_text)
print("-" * 50)

# Fix the encoding issues
fixed_text = processor._fix_pdf_encoding_issues(sample_corrupted_text)

print("\nFixed text (characters replaced):")
print("-" * 50)
print(fixed_text)
print("-" * 50)

# Now clean and chunk the text
cleaned_text = processor.clean_text(fixed_text)
chunks = processor.chunk_text(cleaned_text)

print(f"\nNumber of chunks created: {len(chunks)}")
print("\nProcessed chunk (with fixes applied):")
print("-" * 50)
print(chunks[0]['text'])
print("-" * 50)

# Clean up test file
import os
os.remove(__file__)
