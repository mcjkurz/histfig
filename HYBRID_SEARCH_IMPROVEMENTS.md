# Hybrid Search Improvements - Summary

## Problem
The hybrid search was returning documents with 0% cosine similarity match. This occurred because the Reciprocal Rank Fusion (RRF) algorithm combined results from both vector search (semantic/cosine similarity) and BM25 (keyword search), allowing documents with no semantic relevance (0% cosine) to appear if they scored high on keyword matching alone.

## Solution
Implemented a three-tier improvement to the hybrid search system:

### 1. **Filtering by Cosine Similarity**
   - Added `min_cosine_similarity` threshold (default: 0.05 or 5%)
   - Filter vector search results BEFORE applying RRF fusion
   - Final filter ensures no results with 0% cosine similarity are returned
   - Empty results returned if no documents meet minimum similarity threshold

### 2. **Separate Metric Display**
   - **Cosine Similarity**: Shows semantic relevance (vector search)
   - **Top Matching Keywords**: Shows up to 5 matching words from query (BM25)
   - Both metrics are independently calculated and displayed

### 3. **Enhanced UI Display**
   - **Match (cosine)**: Green text showing percentage match from vector search
   - **Keywords**: Orange text showing matched keywords from BM25 search
   - Clear visual distinction between semantic and keyword matching

## Files Modified

### Backend Changes

#### 1. `scripts/hybrid_search.py`
   - **`search_bm25()`**: Added extraction of top matching words (up to 5) between query and document
   - **`reciprocal_rank_fusion()`**: 
     - Preserves both `cosine_similarity` and `top_matching_words` for each result
     - Merges information from both vector and BM25 results
   - **`hybrid_search()`**:
     - Added `min_cosine_similarity` parameter (default 0.05)
     - Filters vector results before RRF fusion
     - Final filter to ensure all results have meaningful cosine similarity
     - Returns empty list if no results meet threshold

#### 2. `scripts/figure_manager.py`
   - **`search_figure_documents()`**: Added cosine similarity filtering with `min_cosine_similarity` parameter
   - **`_search_figure_bm25()`**: Added top matching words extraction using cached BM25 documents
   - **`_reciprocal_rank_fusion()`**: Updated to preserve both cosine and BM25 metrics

#### 3. `scripts/app.py`
   - Updated chat endpoint to include new fields in sources_data:
     - `cosine_similarity`: Explicit cosine similarity value
     - `top_matching_words`: Array of matching keywords
   - Applied to both streaming and non-streaming response paths
   - Backward compatible with existing `similarity` field

### Frontend Changes

#### 4. `static/chat-app.js`
   - **`displaySources()`**: Updated document display to show:
     - **Cosine similarity**: Green text, formatted as "Match (cosine): X%"
     - **Top keywords**: Orange text, formatted as "Keywords: word1, word2, ..."
     - Shows "Keywords: none" if no matching words found

#### 5. Templates (Automatic)
   - `templates/index.html`: Uses shared `chat-app.js` (automatically updated)
   - `templates/index_mobile.html`: Uses shared `chat-app.js` (automatically updated)

## Technical Details

### Cosine Similarity Filtering
```python
# Filter vector results before RRF
filtered_vector_results = [
    r for r in vector_results 
    if r.get("similarity", 0) >= min_cosine_similarity
]

# Final filter after RRF
final_results = [
    r for r in fused_results 
    if r.get("cosine_similarity", 0) >= min_cosine_similarity
]
```

### Top Matching Words Extraction
```python
# Find top 5 matching words between query and document
doc_tokens = self.bm25_documents[idx]
matching_words = [word for word in query_tokens if word in doc_tokens]
top_matching_words = matching_words[:5] if matching_words else []
```

### Result Structure
```python
{
    "text": "document text...",
    "metadata": {...},
    "similarity": 0.79,              # Backward compatible
    "cosine_similarity": 0.79,       # Explicit cosine similarity
    "top_matching_words": ["word1", "word2", "word3"],  # BM25 matches
    "bm25_score": 12.5,
    "chunk_id": 985,
    "rrf_score": 0.032,
    "vector_rank": 1,
    "bm25_rank": 3
}
```

## Benefits

1. **No More 0% Matches**: All results now have meaningful semantic relevance
2. **Transparency**: Users can see both semantic and keyword matching separately
3. **Better Understanding**: Clear indication of why a document was retrieved
4. **Robust Filtering**: Multiple filtering stages ensure quality results
5. **Backward Compatible**: Existing code using `similarity` field still works

## Configuration

The minimum cosine similarity threshold can be adjusted:

```python
# In hybrid_search.py and figure_manager.py
min_cosine_similarity: float = 0.05  # Default 5%

# Can be adjusted higher for stricter filtering:
# 0.05 (5%) - Very lenient, catches weak matches
# 0.10 (10%) - Balanced default
# 0.20 (20%) - Strict, only strong matches
```

## Example Output

**Before:**
```
maozedong_202: Mao_Zedong_Red_Book.pdf
propaganda among the people...
0% match  ❌ (Should not appear!)
```

**After:**
```
maozedong_985: Mao_Zedong_Wiki.pdf
The republicans' figurehead was Sun Yat-sen...
Match (cosine): 79% ✅
Keywords: republican, sun, yatsen
```

## Testing

To test the improvements:
1. Start the server: `python scripts/app.py`
2. Enable RAG in the chat interface
3. Send a query and observe the "Retrieved Documents" panel
4. Verify:
   - All documents show non-zero cosine similarity
   - Top matching keywords are displayed
   - No more 0% matches appear

## Future Enhancements

Potential improvements:
- Make `min_cosine_similarity` configurable via UI
- Add visual indicators for match strength (color coding)
- Display BM25 score percentage
- Add tooltips explaining each metric
- Show query terms highlighting in document preview

