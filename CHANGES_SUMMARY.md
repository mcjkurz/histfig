# Changes Summary

## Fixed Issues

### 1. ✅ Fixed `upload_app.py` to use `get_hybrid_db`
**Files Changed:**
- `/scripts/upload_app.py`

**Changes:**
- Added `import secrets` for secure secret key generation
- Changed secret key from hardcoded string to environment variable: `os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))`
- Replaced all instances of `get_vector_db()` with `get_hybrid_db()` (lines 36, 138, 171, 187)

### 2. ✅ Added Character & Word-Based Chunking Controls
**Files Changed:**
- `/scripts/document_processor.py`
- `/scripts/config.py`
- `/scripts/figure_manager.py`
- `/scripts/admin_app.py`
- `/templates/admin/new_figure.html`

**Changes:**
- **document_processor.py**: 
  - Added `max_chunk_chars` and `char_overlap` parameters to `__init__`
  - Updated docstrings to clarify character-based (primary) vs word-based (secondary) chunking
  
- **config.py**:
  - Added new config variables: `MAX_CHUNK_CHARS = 1000` and `CHAR_OVERLAP = 250`
  
- **figure_manager.py**:
  - Added `max_chunk_chars` parameter to `create_figure()` method
  - Validates max_chunk_chars between 500-3000 characters
  - Stores both `max_length` (words) and `max_chunk_chars` (characters) in figure metadata
  
- **admin_app.py**:
  - Added `max_chunk_chars` to form data collection
  - Passes both chunking parameters to `DocumentProcessor` when processing uploads
  - Updated both streaming and non-streaming upload endpoints
  
- **new_figure.html**:
  - Added new section "Document Chunking Settings"
  - Added input field for "Max Characters per Chunk" (500-3000, default 1000)
  - Relabeled existing field as "Max Words per Chunk (Legacy/Semantic)"
  - Added helpful descriptions for both fields

### 3. ✅ JavaScript Modularization (Started)
**Files Created:**
- `/static/modules/state-manager.js` - Manages application state
- `/static/modules/api-client.js` - Handles all API calls
- `/static/modules/ui-manager.js` - Manages UI updates and interactions

**Architecture:**
```
chat-app.js (orchestrator)
├── StateManager - handles state persistence and management
├── APIClient - handles all backend API calls
├── UIManager - handles UI updates and rendering
├── MessageHandler (to be created) - handles message rendering
└── DocumentHandler (to be created) - handles document sources
```

## Remaining Work for Complete Modularization

To complete the JavaScript refactoring, you'll need to:

1. **Create `message-handler.js`**: Extract message rendering, streaming, and thinking content processing
2. **Create `document-handler.js`**: Extract document sources display and modal handling
3. **Update `chat-app.js`**: Import and orchestrate all modules
4. **Update `index.html`**: Add `<script type="module">` tags to load modular JavaScript

Example structure for main `chat-app.js`:
```javascript
import { StateManager } from './modules/state-manager.js';
import { APIClient } from './modules/api-client.js';
import { UIManager } from './modules/ui-manager.js';
// Import other modules...

class ChatApp {
    constructor() {
        this.state = new StateManager();
        this.api = new APIClient();
        this.ui = new UIManager(elements, this.state);
        // Initialize other components...
    }
    // Orchestrate interactions between modules...
}
```

## Important Notes

### Issue #4 - Secret Key Regeneration
You asked: "Is that an important bug? Why does it matter?"

**Answer**: YES, it matters in production:
- **Session Invalidation**: All users get logged out on server restart
- **Multi-instance Problems**: If you have multiple server instances (load balancing), each would have a different secret key, breaking sessions
- **User Experience**: Users lose their conversation history, selected figures, and settings

**However**, since you're using in-memory `session_data` dict (which also gets wiped on restart), the session invalidation is somewhat redundant. For production, consider:
1. Using a persistent secret key (environment variable required, not optional)
2. Moving session data to Redis or database for persistence

### Issue #7 - Similarity Score
You asked: "How to do it right and why?"

**Answer**: Your current implementation is actually **correct**:
```python
similarity = max(0.0, 1.0 - (distance / 2.0))
```

ChromaDB returns **cosine distance** (0 = identical, 2 = opposite). Your formula correctly converts it to **cosine similarity** (0 = no match, 1 = perfect match). The normalization by 2.0 is correct because:
- Cosine distance = 1 - cosine_similarity
- Range: [0, 2]
- Your formula: similarity = 1 - (distance/2) = 1 - ((1-cos_sim)/2) ✓

No change needed here!

## Testing Checklist

After these changes, test:
- [ ] Create new figure with both chunking parameters
- [ ] Upload documents to figure and verify chunking works correctly  
- [ ] Verify both character-based and word-based parameters are saved
- [ ] Test upload_app.py functionality (if you use it)
- [ ] Verify secret key is loaded from environment or generated once
- [ ] Test RAG search with different chunking sizes

## Configuration

Add to your environment variables (optional):
```bash
export FLASK_SECRET_KEY="your-persistent-secret-key-here"
export MAX_CHUNK_CHARS=1000  # Default characters per chunk
export CHAR_OVERLAP=250      # Default character overlap
```

