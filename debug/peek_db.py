#!/usr/bin/env python3
"""
Script to peek into the database and show document representations
"""

import sys
import os
import json
import random

# Add scripts directory to path (parent directory)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import chromadb
from chromadb.config import Settings

def peek_database(figure_id="zhenghe"):
    """Peek into database and show both segmented and non-segmented text"""
    
    # Initialize ChromaDB client (path relative to project root)
    db_path = os.path.join(os.path.dirname(__file__), '..', 'chroma_db')
    client = chromadb.PersistentClient(
        path=db_path,
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=True
        )
    )
    
    # List all collections
    print("=" * 80)
    print("Available Collections:")
    print("=" * 80)
    collections = client.list_collections()
    for col in collections:
        print(f"  - {col.name} (count: {col.count()})")
    print()
    
    # Get the specific collection
    collection_name = f"figure_{figure_id}"
    try:
        collection = client.get_collection(collection_name)
        print(f"Accessing collection: {collection_name}")
        print(f"Total documents: {collection.count()}")
        print()
    except Exception as e:
        print(f"Error: Collection '{collection_name}' not found!")
        print(f"Details: {e}")
        return
    
    # Get all documents (or a sample if too many)
    total_docs = collection.count()
    if total_docs == 0:
        print("No documents found in collection!")
        return
    
    # Get a random document
    results = collection.get(
        limit=min(total_docs, 100)  # Get up to 100 docs to sample from
    )
    
    # Pick a random one
    random_idx = random.randint(0, len(results['ids']) - 1)
    
    doc_id = results['ids'][random_idx]
    doc_text = results['documents'][random_idx]
    doc_metadata = results['metadatas'][random_idx]
    
    print("=" * 80)
    print(f"Random Document Sample (ID: {doc_id})")
    print("=" * 80)
    print()
    
    # Show metadata
    print("METADATA:")
    print("-" * 80)
    for key, value in doc_metadata.items():
        if key != "processed_tokens":  # Skip this for now
            print(f"  {key}: {value}")
    print()
    
    # Show non-segmented text (original)
    print("NON-SEGMENTED TEXT (Original):")
    print("-" * 80)
    print(doc_text)
    print()
    print(f"Character count: {len(doc_text)}")
    print()
    
    # Show segmented text (processed tokens)
    print("SEGMENTED TEXT (Processed Tokens):")
    print("-" * 80)
    if "processed_tokens" in doc_metadata:
        try:
            tokens = json.loads(doc_metadata["processed_tokens"])
            print(" / ".join(tokens))
            print()
            print(f"Token count: {len(tokens)}")
            print()
            print("First 50 tokens:")
            print(" / ".join(tokens[:50]))
        except Exception as e:
            print(f"Error parsing processed tokens: {e}")
    else:
        print("No processed_tokens found in metadata!")
    print()
    
    print("=" * 80)

if __name__ == "__main__":
    figure_id = sys.argv[1] if len(sys.argv) > 1 else "zhenghe"
    peek_database(figure_id)



