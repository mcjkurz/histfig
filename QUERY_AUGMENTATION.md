# Query Augmentation

Query augmentation is a feature that automatically enriches user queries with additional context and details before performing the search. This helps improve search results by making queries more comprehensive, while keeping the process transparent to the end user.

## How It Works

1. **User submits a query** - The user enters a search query in the normal way
2. **Query augmentation** (if enabled) - The system sends the query to an LLM API to expand it with relevant details
3. **Search execution** - The augmented query is used for vector and keyword search
4. **Results returned** - The user sees improved results without knowing the query was augmented

## Configuration

### Environment Variables

Set these environment variables to configure query augmentation:

```bash
# Enable or disable query augmentation (default: false)
export QUERY_AUGMENTATION_ENABLED=true

# Model to use for augmentation (default: GPT-5-nano)
export QUERY_AUGMENTATION_MODEL="GPT-5-nano"

# API endpoint (default: OpenRouter)
export QUERY_AUGMENTATION_API_URL="https://openrouter.ai/api/v1"

# API key for external model access (required when augmentation is enabled)
export EXTERNAL_API_KEY="your-api-key-here"
```

### In config.py

You can also modify the defaults in `scripts/config.py`:

```python
# Query Augmentation Settings
QUERY_AUGMENTATION_ENABLED = True  # Enable augmentation
QUERY_AUGMENTATION_MODEL = "GPT-5-nano"  # Model to use
QUERY_AUGMENTATION_API_URL = "https://openrouter.ai/api/v1"  # API endpoint
```

## Supported Models

The system works with any OpenAI-compatible API. Some recommended models:

- **GPT-5-nano** (default) - Fast and efficient for query expansion
- **GPT-5-mini** - More detailed augmentation
- **GPT-4.1-mini** - Alternative option
- **Gemini-2.5-Flash** - Google's option
- Any other OpenAI-compatible model

## Testing

Test the query augmentation feature:

```bash
# Set environment variables
export QUERY_AUGMENTATION_ENABLED=true
export EXTERNAL_API_KEY="your-api-key-here"

# Run the test script
cd scripts
python test_query_augmentation.py
```

## Examples

### Example 1: Simple Query
- **Original**: "Napoleon"
- **Augmented**: "Napoleon Bonaparte, French military leader and emperor, his campaigns, battles, exile, and impact on European history"

### Example 2: Question
- **Original**: "What was Einstein's contribution to physics?"
- **Augmented**: "Albert Einstein's major contributions to physics including theory of relativity, E=mc², photoelectric effect, quantum mechanics, space-time continuum, and Nobel Prize work"

## How It Integrates

Query augmentation is automatically integrated into the figure-specific search system:

```python
from figure_manager import get_figure_manager

# Initialize figure manager
fm = get_figure_manager()

# User query (augmentation happens automatically if enabled)
results = fm.search_figure_documents(figure_id, "Napoleon")

# Results are based on the augmented query, but user sees their original query
```

**Note**: Query augmentation is only applied to figure-specific searches (the main chat interface). It is NOT applied to the general upload/admin search interface.

## Performance Considerations

- **Latency**: Adds ~200-500ms per query (depends on API response time)
- **Cost**: Each query augmentation counts as a small API call
- **Fallback**: If augmentation fails, the original query is used automatically

## Disabling Augmentation

To disable query augmentation:

```bash
export QUERY_AUGMENTATION_ENABLED=false
```

Or simply don't set the `EXTERNAL_API_KEY` environment variable.

## Troubleshooting

### Augmentation not working?

1. Check if it's enabled:
   ```python
   from config import QUERY_AUGMENTATION_ENABLED
   print(QUERY_AUGMENTATION_ENABLED)  # Should be True
   ```

2. Check if API key is set:
   ```python
   from config import EXTERNAL_API_KEY
   print(bool(EXTERNAL_API_KEY))  # Should be True
   ```

3. Check logs for error messages:
   ```bash
   # The system will log augmentation attempts
   # Look for messages like: "Query augmented: '...' -> '...'"
   ```

### API errors?

- Verify your API key is correct
- Check your API quota/credits
- Ensure the API URL is correct
- Check your internet connection

## Architecture

The query augmentation feature consists of:

1. **config.py** - Configuration settings
2. **query_augmentation.py** - Core augmentation logic
3. **figure_manager.py** - Integration with figure-specific search

The augmentation happens transparently in the `search_figure_documents()` method, so no changes are needed to existing code that calls this method. It is specifically integrated into the main chat application's search flow.

