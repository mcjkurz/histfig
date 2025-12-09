#!/usr/bin/env python3
"""
Command Line Interface for Historical Figures Management
Provides commands to create, manage, and upload documents for historical figures.
"""

import argparse
import sys
import os
import json
from pathlib import Path
from typing import List, Dict, Any
import logging

# Add the current directory to Python path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from figure_manager import get_figure_manager
from document_processor import DocumentProcessor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

class FigureCLI:
    def __init__(self):
        self.figure_manager = get_figure_manager()
    
    def create_figure(self, args):
        """Create a new historical figure."""
        figure_id = args.figure_id
        name = args.name
        description = args.description or ""
        personality_prompt = args.personality_prompt or ""
        
        # Parse additional metadata if provided
        metadata = {}
        if args.metadata:
            try:
                metadata = json.loads(args.metadata)
            except json.JSONDecodeError:
                print("Error: Invalid JSON in metadata field")
                return False
        
        success = self.figure_manager.create_figure(
            figure_id=figure_id,
            name=name,
            description=description,
            personality_prompt=personality_prompt,
            metadata=metadata
        )
        
        if success:
            print(f"✓ Created figure: {name} ({figure_id})")
            return True
        else:
            print(f"✗ Failed to create figure: {figure_id}")
            return False
    
    def list_figures(self, args):
        """List all available figures."""
        figures = self.figure_manager.get_figure_list()
        
        if not figures:
            print("No figures found.")
            return
        
        print(f"\nAvailable Figures ({len(figures)}):")
        print("-" * 50)
        
        for figure in figures:
            print(f"ID: {figure['figure_id']}")
            print(f"Name: {figure['name']}")
            print(f"Description: {figure['description']}")
            print(f"Documents: {figure.get('document_count', 0)}")
            if figure.get('personality_prompt'):
                prompt_preview = figure['personality_prompt'][:100]
                if len(figure['personality_prompt']) > 100:
                    prompt_preview += "..."
                print(f"Personality: {prompt_preview}")
            print("-" * 50)
    
    def show_figure(self, args):
        """Show detailed information about a figure."""
        figure_id = args.figure_id
        metadata = self.figure_manager.get_figure_metadata(figure_id)
        
        if not metadata:
            print(f"Figure '{figure_id}' not found.")
            return False
        
        stats = self.figure_manager.get_figure_stats(figure_id)
        
        print(f"\nFigure Details: {metadata['name']}")
        print("=" * 50)
        print(f"ID: {metadata['figure_id']}")
        print(f"Name: {metadata['name']}")
        print(f"Description: {metadata['description']}")
        print(f"Document Count: {stats.get('document_count', 0)}")
        
        if metadata.get('personality_prompt'):
            print(f"\nPersonality Prompt:")
            print(f"  {metadata['personality_prompt']}")
        
        if metadata.get('metadata'):
            print(f"\nAdditional Metadata:")
            for key, value in metadata['metadata'].items():
                print(f"  {key}: {value}")
        
        return True
    
    def delete_figure(self, args):
        """Delete a figure and all its data."""
        figure_id = args.figure_id
        
        # Confirm deletion
        if not args.force:
            metadata = self.figure_manager.get_figure_metadata(figure_id)
            if metadata:
                print(f"Are you sure you want to delete '{metadata['name']}' ({figure_id})?")
                print("This will permanently remove the figure and all its documents.")
                response = input("Type 'yes' to confirm: ")
                if response.lower() != 'yes':
                    print("Deletion cancelled.")
                    return False
            else:
                print(f"Figure '{figure_id}' not found.")
                return False
        
        success = self.figure_manager.delete_figure(figure_id)
        if success:
            print(f"✓ Deleted figure: {figure_id}")
            return True
        else:
            print(f"✗ Failed to delete figure: {figure_id}")
            return False
    
    def upload_documents(self, args):
        """Upload documents to a figure."""
        figure_id = args.figure_id
        file_paths = args.files
        
        # Check if figure exists and get metadata
        figure_metadata = self.figure_manager.get_figure_metadata(figure_id)
        if not figure_metadata:
            print(f"Figure '{figure_id}' not found.")
            return False
        
        # Get figure-specific chunk size
        max_length = figure_metadata.get('max_length', 250)
        document_processor = DocumentProcessor(chunk_size=max_length)
        
        successful_uploads = 0
        total_files = len(file_paths)
        
        for file_path in file_paths:
            if not os.path.exists(file_path):
                print(f"✗ File not found: {file_path}")
                continue
            
            try:
                # Read file content
                with open(file_path, 'rb') as f:
                    file_content = f.read()
                
                # Determine file type
                file_extension = Path(file_path).suffix.lower()
                if file_extension == '.pdf':
                    file_type = 'pdf'
                elif file_extension in ['.txt', '.text']:
                    file_type = 'txt'
                elif file_extension == '.docx':
                    file_type = 'docx'
                else:
                    print(f"✗ Unsupported file type: {file_path}")
                    continue
                
                # Process the file into chunks
                filename = Path(file_path).name
                chunks = document_processor.process_file(file_content, filename, file_type)
                
                # Add each chunk to the figure's collection
                chunk_count = 0
                for chunk in chunks:
                    doc_id = self.figure_manager.add_document_to_figure(
                        figure_id=figure_id,
                        text=chunk['text'],
                        metadata=chunk['metadata']
                    )
                    if doc_id:
                        chunk_count += 1
                
                print(f"✓ Uploaded {filename}: {chunk_count} chunks added")
                successful_uploads += 1
                
            except Exception as e:
                print(f"✗ Error processing {file_path}: {e}")
                continue
        
        print(f"\nUpload Summary: {successful_uploads}/{total_files} files processed successfully.")
        
        # Show updated stats
        stats = self.figure_manager.get_figure_stats(figure_id)
        print(f"Total documents for {figure_id}: {stats.get('document_count', 0)}")
        
        return successful_uploads > 0
    
    def search_figure(self, args):
        """Search documents for a specific figure."""
        figure_id = args.figure_id
        query = args.query
        n_results = args.limit or 5
        
        if not self.figure_manager.get_figure_metadata(figure_id):
            print(f"Figure '{figure_id}' not found.")
            return False
        
        results = self.figure_manager.search_figure_documents(figure_id, query, n_results)
        
        if not results:
            print(f"No results found for query: '{query}'")
            return False
        
        print(f"\nSearch Results for '{query}' in {figure_id}:")
        print("=" * 60)
        
        for i, result in enumerate(results, 1):
            similarity = result.get('similarity', 0)
            filename = result['metadata'].get('filename', 'Unknown')
            chunk_index = result['metadata'].get('chunk_index', 0)
            
            print(f"\n{i}. [{filename}, chunk {chunk_index}] (similarity: {similarity:.3f})")
            print("-" * 40)
            
            # Show text preview
            text = result['text']
            if len(text) > 300:
                text = text[:300] + "..."
            print(text)
        
        return True

def main():
    parser = argparse.ArgumentParser(description="Historical Figures Management CLI")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create figure command
    create_parser = subparsers.add_parser('create', help='Create a new historical figure')
    create_parser.add_argument('figure_id', help='Unique identifier for the figure (e.g., napoleon_bonaparte)')
    create_parser.add_argument('name', help='Display name for the figure (e.g., "Napoleon Bonaparte")')
    create_parser.add_argument('--description', help='Description of the figure')
    create_parser.add_argument('--personality-prompt', help='Personality prompt for responses')
    create_parser.add_argument('--metadata', help='Additional metadata as JSON string')
    
    # List figures command
    list_parser = subparsers.add_parser('list', help='List all available figures')
    
    # Show figure command
    show_parser = subparsers.add_parser('show', help='Show detailed information about a figure')
    show_parser.add_argument('figure_id', help='Figure identifier')
    
    # Delete figure command
    delete_parser = subparsers.add_parser('delete', help='Delete a figure and all its data')
    delete_parser.add_argument('figure_id', help='Figure identifier')
    delete_parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    
    # Upload documents command
    upload_parser = subparsers.add_parser('upload', help='Upload documents to a figure')
    upload_parser.add_argument('figure_id', help='Figure identifier')
    upload_parser.add_argument('files', nargs='+', help='Paths to PDF or TXT files to upload')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search documents for a specific figure')
    search_parser.add_argument('figure_id', help='Figure identifier')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--limit', type=int, help='Number of results to return (default: 5)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    cli = FigureCLI()
    
    try:
        if args.command == 'create':
            success = cli.create_figure(args)
        elif args.command == 'list':
            cli.list_figures(args)
            success = True
        elif args.command == 'show':
            success = cli.show_figure(args)
        elif args.command == 'delete':
            success = cli.delete_figure(args)
        elif args.command == 'upload':
            success = cli.upload_documents(args)
        elif args.command == 'search':
            success = cli.search_figure(args)
        else:
            print(f"Unknown command: {args.command}")
            success = False
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
