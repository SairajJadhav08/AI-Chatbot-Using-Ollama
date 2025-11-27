"""
FastAPI Backend for AI Chatbot
Main application file handling API endpoints and Ollama integration.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import os
from dotenv import load_dotenv
from ollama_client import OllamaClient
import json

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="AI Chatbot API", version="1.0.0")

# Configure CORS to allow frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Ollama client
ollama_client = OllamaClient(
    base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
    model=os.getenv("OLLAMA_MODEL", "llama3")
)


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str
    history: Optional[List[Dict[str, str]]] = None
    custom_instructions: Optional[str] = None


async def generate_response_stream(message: str, history: Optional[List[Dict[str, str]]] = None, custom_instructions: Optional[str] = None):
    """
    Generator function that streams responses from Ollama.
    
    Args:
        message: User's message
        history: Conversation history
        custom_instructions: Custom instructions for AI behavior
    
    Yields:
        SSE-formatted chunks
    """
    try:
        # Quick check if Ollama is reachable before starting
        import httpx
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.get(f"{ollama_client.base_url}/api/tags")
        except Exception:
            error_msg = {
                "error": f"Ollama server is not running at {ollama_client.base_url}. Please start Ollama with 'ollama serve' in a terminal.",
                "type": "connection_error"
            }
            yield f"data: {json.dumps(error_msg)}\n\n"
            return
        
        # Create a temporary client with custom instructions if provided
        client_to_use = ollama_client
        if custom_instructions:
            client_to_use = OllamaClient(
                base_url=ollama_client.base_url,
                model=ollama_client.model
            )
            # Update system prompt with custom instructions
            client_to_use.system_prompt = f"{ollama_client.system_prompt}\n\nAdditional instructions from user: {custom_instructions}"
        
        async for chunk in client_to_use.generate_stream(message, history):
            # Format as Server-Sent Events (SSE)
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        
        # Send done signal
        yield f"data: {json.dumps({'done': True})}\n\n"
    
    except ConnectionError as e:
        error_msg = {
            "error": str(e),
            "type": "connection_error"
        }
        yield f"data: {json.dumps(error_msg)}\n\n"
    
    except Exception as e:
        error_msg = {
            "error": f"An error occurred: {str(e)}",
            "type": "general_error"
        }
        yield f"data: {json.dumps(error_msg)}\n\n"


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "online",
        "service": "AI Chatbot API",
        "ollama_url": ollama_client.base_url,
        "model": ollama_client.model
    }


@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Chat endpoint that streams responses from Ollama.
    
    Accepts:
        - message: User's message (required)
        - history: Previous conversation history (optional)
        - custom_instructions: Custom instructions for AI behavior (optional)
    
    Returns:
        StreamingResponse with SSE-formatted chunks
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    return StreamingResponse(
        generate_response_stream(request.message, request.history, request.custom_instructions),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

