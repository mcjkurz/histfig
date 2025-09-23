#!/usr/bin/env python3
"""Test script to demonstrate the improved PDF chunking."""

from document_processor import DocumentProcessor

# Create a document processor
processor = DocumentProcessor(chunk_size=200, chunk_overlap=20)

# Simulate text that would come from a PDF with broken lines
sample_pdf_text = """This is a sample text that
demonstrates how PDF text
extraction often breaks lines
in the middle of sentences. This
makes the text appear fragmented
when it should be continuous.

Another paragraph starts here and
it also has the same issue with
line breaks appearing in random
places throughout the text. The
chunking algorithm should now
handle this properly by removing
these unnecessary line breaks.

A third paragraph with more text
that spans multiple lines and
should be processed into a single
coherent line of text without
the artificial breaks."""

print("Original text (with line breaks):")
print("-" * 50)
print(sample_pdf_text)
print("-" * 50)

# Process the text into chunks
chunks = processor.chunk_text(sample_pdf_text)

print(f"\nNumber of chunks created: {len(chunks)}")
print("\nProcessed chunks (line breaks removed):")
print("-" * 50)

for i, chunk in enumerate(chunks):
    print(f"\nChunk {i + 1}:")
    print(chunk['text'])
    print(f"Length: {len(chunk['text'])} characters")

# Clean up test file
import os
os.remove(__file__)
