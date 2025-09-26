# Model Provider Setup Guide

The Historical Figures Chat System supports local Ollama models and external API endpoints! You can use local models or connect to any OpenAI-compatible API endpoint directly from the browser.

## Supported Providers

1. **Ollama** (Default) - Local models
2. **External API** - Any OpenAI-compatible endpoint (POE, Azure, OpenAI, etc.)

## Configuration

Provider settings can be configured via environment variables or by editing `scripts/config.py`.

### Using Ollama (Default)

No additional configuration needed! Just ensure Ollama is running:

```bash
ollama serve
./start_foreground.sh
```


### Using External API (Browser Configuration)

The easiest way to use external APIs like POE:

1. Start the application normally:
```bash
./start_foreground.sh
```

2. In the browser interface:
   - Select **"External API"** from the model dropdown
   - Three fields will appear:
     - **API Endpoint**: Pre-filled with `https://api.poe.com/v1`
     - **Model Name**: Pre-filled with `GPT-5-mini`
     - **API Key**: Enter your POE API key (get it from [poe.com/api_key](https://poe.com/api_key))

3. Start chatting! The system will use your external API.

**Supported External APIs:**
- **POE API** - Access to GPT-5-mini and other models
- **Azure OpenAI** - Use your Azure endpoint
- **Any OpenAI-compatible API** - Local or cloud-based

## Testing Your Setup

Run the test script to verify your provider is working:

```bash
python test_providers.py
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MODEL_PROVIDER` | Provider to use: `ollama` | `ollama` |
| `OLLAMA_URL` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Default Ollama model | `gpt-oss:20b` |

## Using Alternative OpenAI-Compatible APIs

You can use any OpenAI-compatible API (like Azure OpenAI, local LLMs with OpenAI-compatible endpoints, etc.) using the **External API** option in the browser interface - no environment variables needed!

## Features Preserved

All existing features work seamlessly with any provider:
- ✅ RAG (Retrieval-Augmented Generation) with historical documents
- ✅ Streaming responses
- ✅ Conversation history
- ✅ Figure personality simulation
- ✅ Thinking modes
- ✅ Temperature control
- ✅ Multi-language support

## Troubleshooting

### Provider not connecting?

1. **Ollama**: Ensure Ollama is running (`ollama serve`)
2. **External API**: Check your API key is valid and has credits
3. Run `python test_providers.py` to diagnose issues

### Models not showing up?

- **Ollama**: Pull models first (`ollama pull model-name`)
- **External API**: Enter the model name manually in the External API configuration

### Streaming not working?

All providers support streaming. If you see issues, check your network connection and API limits.

## Cost Considerations

- **Ollama**: Free (runs locally)
- **External APIs**: Most charge per token - check your provider's pricing

## Security Notes

- Never commit API keys to version control
- Use environment variables or secure key management systems
- Consider using `.env` files (add to `.gitignore`)

## Example .env File

Create a `.env` file in the project root (optional):

```env
# Ollama settings (optional customization)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=your-preferred-model
```

Then load it before starting:

```bash
source .env
./start_foreground.sh
```

**Note**: For external APIs, use the browser interface instead of environment variables!
