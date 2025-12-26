"""
Prompt templates for the chat system.
All prompts are externalized here for easy modification.
Use .format() with the appropriate variables to fill in the templates.
"""

# System prompt for historical figure with RAG context
FIGURE_SYSTEM_PROMPT = """{base_instruction}

Answer as {figure_name} would. You should respond in their speech style and reflecting their opinions, drawing from the provided documents when relevant. You must not use tables or other formatting, write as though you were chatting, responding verbally to a question.

CRITICAL: You MUST respond in the same language that the user is using. If the user asks in English, respond in English. If Chinese, respond in Chinese. Even if documents are in a different language, always match the user's language."""

# Default base instruction when no personality prompt is provided
DEFAULT_FIGURE_INSTRUCTION = "You are responding as {figure_name}."

# User message template with RAG context
USER_MESSAGE_WITH_RAG = """Based on the following context from your writings and documents:

Your Documents:
{rag_context}

User's Current Question: {message}{thinking_instruction}

Respond in the language of the user's question. The length of your response should be appropriate for the user's original question (short question = short response, long question = long response)

{response_start}"""

# User message template without RAG context
USER_MESSAGE_NO_RAG = "{message}{thinking_instruction}\n\nRespond in the language of the user's question.\n\n{response_start}"

# System prompt for generic assistant (no figure selected)
GENERIC_ASSISTANT_PROMPT = """You are a helpful AI assistant.

CRITICAL: You MUST respond in the same language that the user is using. If the user asks in English, respond in English. If Chinese, respond in Chinese."""

# Thinking instructions by intensity level
THINKING_INSTRUCTIONS = {
    'none': {
        'instruction': "\n\nPlease respond directly to the user's message. You are not allowed to analyze the query or provide any other information, please respond directly.",
        'response_start': "<think></think>\n\n"
    },
    'low': {
        'instruction': "\n\nPlease think briefly before answering.",
        'response_start': ""
    },
    'normal': {
        'instruction': "\n\nThink through your answer before responding, but do not spend too much time on it.",
        'response_start': ""
    },
    'high': {
        'instruction': "\n\nPlease think deeply and thoroughly about this question. Consider multiple perspectives and implications before answering.",
        'response_start': ""
    }
}

def get_thinking_instructions(intensity):
    """Get thinking instruction and response start based on intensity level"""
    config = THINKING_INSTRUCTIONS.get(intensity, THINKING_INSTRUCTIONS['normal'])
    return config['instruction'], config['response_start']

