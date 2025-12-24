#!/usr/bin/env python3
"""
Rebuild BM25 indexes for all figures from ChromaDB.
This script rebuilds the BM25 search indexes for all historical figures
based on the documents stored in ChromaDB.
"""

import sys
import os
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from figure_manager import FigureManager
from config import CHROMA_DB_PATH, FIGURES_DIR

def setup_logging():
    """Configure logging for the script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def rebuild_all_bm25_indexes():
    """Rebuild BM25 indexes for all figures."""
    print("=" * 70)
    print("BM25 Index Rebuild Script")
    print("=" * 70)
    print()
    
    try:
        # Initialize FigureManager
        print("Initializing FigureManager...")
        figure_manager = FigureManager(
            figures_dir=FIGURES_DIR,
            db_path=CHROMA_DB_PATH
        )
        print("✓ FigureManager initialized")
        print()
        
        # Get all figures
        print("Fetching all figures...")
        figures = figure_manager.get_figure_list()
        
        if not figures:
            print("⚠ No figures found in the system.")
            return
        
        print(f"✓ Found {len(figures)} figure(s)")
        print()
        
        # Process each figure
        success_count = 0
        fail_count = 0
        
        for i, figure in enumerate(figures, 1):
            figure_id = figure['figure_id']
            figure_name = figure['name']
            
            print(f"[{i}/{len(figures)}] Processing: {figure_name} (ID: {figure_id})")
            print("-" * 70)
            
            try:
                # Get document count
                stats = figure_manager.get_figure_stats(figure_id)
                doc_count = stats.get('document_count', 0)
                print(f"  Documents in collection: {doc_count}")
                
                if doc_count == 0:
                    print(f"  ⚠ Skipping - no documents to index")
                    print()
                    continue
                
                # Clear old BM25 cache
                print(f"  Clearing old BM25 cache...")
                figure_manager._invalidate_bm25_cache(figure_id)
                
                # Rebuild BM25 index from ChromaDB
                print(f"  Rebuilding BM25 index from ChromaDB...")
                success = figure_manager._build_bm25_from_chromadb(figure_id)
                
                if success:
                    print(f"  ✓ BM25 index rebuilt successfully")
                    success_count += 1
                else:
                    print(f"  ✗ Failed to rebuild BM25 index")
                    fail_count += 1
                
            except Exception as e:
                print(f"  ✗ Error: {str(e)}")
                logging.error(f"Error processing figure {figure_id}: {e}", exc_info=True)
                fail_count += 1
            
            print()
        
        # Summary
        print("=" * 70)
        print("REBUILD SUMMARY")
        print("=" * 70)
        print(f"Total figures processed: {len(figures)}")
        print(f"Successfully rebuilt: {success_count}")
        print(f"Failed: {fail_count}")
        print()
        
        if success_count > 0:
            print("✓ BM25 indexes have been rebuilt!")
            print()
            print("IMPORTANT: Please restart the server to load the new indexes:")
            print("  ./restart.sh")
            print()
        else:
            print("⚠ No indexes were rebuilt.")
        
    except Exception as e:
        print(f"✗ Fatal error: {str(e)}")
        logging.error(f"Fatal error in rebuild script: {e}", exc_info=True)
        sys.exit(1)

def main():
    """Main entry point."""
    setup_logging()
    
    print()
    rebuild_all_bm25_indexes()
    print("Done.")

if __name__ == "__main__":
    main()

