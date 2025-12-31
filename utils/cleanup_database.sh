#!/bin/bash

# Cleanup unused ChromaDB files
# Removes leftover index folders from previously deleted figures/collections

cd "$(dirname "$0")/.."

echo "🧹 Database Cleanup"
echo "==================="
echo ""
echo "This script removes unused index folders left behind when figures are deleted."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found."
    exit 1
fi

source venv/bin/activate

python3 -c "
import os
import shutil
import sqlite3

db_path = 'chroma_db'

# Get IDs of index folders that are currently in use
try:
    conn = sqlite3.connect(f'{db_path}/chroma.sqlite3')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM segments')
    active_ids = set(row[0] for row in cursor.fetchall())
    conn.close()
except Exception as e:
    print(f'❌ Error reading database: {e}')
    exit(1)

print(f'Index folders in use: {len(active_ids)}')

# Find all UUID-style folders on disk (these are index folders)
index_folders = []
for item in os.listdir(db_path):
    path = os.path.join(db_path, item)
    # UUID format: 8-4-4-4-12 characters
    if os.path.isdir(path) and len(item) == 36 and item.count('-') == 4:
        index_folders.append(item)

print(f'Index folders on disk: {len(index_folders)}')

# Find unused folders (not in database anymore)
unused = [f for f in index_folders if f not in active_ids]

if not unused:
    print('\\n✅ No unused folders found. Database is clean!')
    exit(0)

print(f'\\nUnused folders to delete: {len(unused)}')

# Delete unused folders and track freed space
deleted_count = 0
freed_bytes = 0

for folder in unused:
    path = os.path.join(db_path, folder)
    try:
        size = sum(os.path.getsize(os.path.join(path, f)) 
                  for f in os.listdir(path) 
                  if os.path.isfile(os.path.join(path, f)))
        freed_bytes += size
        shutil.rmtree(path)
        deleted_count += 1
        print(f'  Deleted: {folder} ({size/1024:.1f} KB)')
    except Exception as e:
        print(f'  Error deleting {folder}: {e}')

print(f'\\n✅ Deleted {deleted_count} unused folders')
print(f'✅ Freed {freed_bytes/1024/1024:.1f} MB of disk space')
"

echo ""
echo "Done."

