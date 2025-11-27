"""
Ollama API Client Module
Handles communication with the local Ollama server for LLM interactions.
"""

import httpx
import json
from typing import List, Dict, Optional, AsyncGenerator
import os


class OllamaClient:
    """Client for interacting with Ollama API."""
    
    def __init__(self, base_url: str = None, model: str = None):
        """
        Initialize Ollama client.
        
        Args:
            base_url: Ollama server URL (default: from env or http://localhost:11434)
            model: Model name to use (default: from env or llama3)
        """
        self.base_url = base_url or os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3")
        self.system_prompt = """You are a friendly and professional AI assistant. 
Answer concisely, clearly and politely. 
Use emojis appropriately to make your responses more engaging and visually appealing. 
Use emojis to express emotions, highlight important points, or add visual interest to your messages. 
Be natural and don't overuse emojis - use them to enhance communication, not distract from it."""
    
    def _format_history(self, history: Optional[List[Dict[str, str]]]) -> List[Dict[str, str]]:
        """
        Format conversation history for Ollama API.
        
        Args:
            history: List of previous messages in format [{"role": "user", "content": "..."}, ...]
        
        Returns:
            Formatted history with system message prepended
        """
        formatted_history = []
        
        # Add system message if history is empty or doesn't start with system
        if not history or (history and history[0].get("role") != "system"):
            formatted_history.append({
                "role": "system",
                "content": self.system_prompt
            })
        
        # Add conversation history
        if history:
            formatted_history.extend(history)
        
        return formatted_history
    
    async def generate_stream(
        self, 
        message: str, 
        history: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate streaming response from Ollama.
        
        Args:
            message: User's message
            history: Previous conversation history
        
        Yields:
            Response chunks as strings
        
        Raises:
            httpx.RequestError: If connection to Ollama fails
        """
        # Format the full conversation including new message
        conversation_history = self._format_history(history) if history else [{
            "role": "system",
            "content": self.system_prompt
        }]
        
        # Add the current user message
        conversation_history.append({
            "role": "user",
            "content": message
        })
        
        # Prepare request payload with options for faster response
        payload = {
            "model": self.model,
            "messages": conversation_history,
            "stream": True,
            "options": {
                "temperature": 0.7,  # Lower temperature for more focused responses
                "num_predict": 500,   # Limit response length for faster generation
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise httpx.HTTPStatusError(
                            f"Ollama API returned status {response.status_code}: {error_text.decode()}",
                            request=response.request,
                            response=response
                        )
                    
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                chunk_data = json.loads(line)
                                if "message" in chunk_data and "content" in chunk_data["message"]:
                                    content = chunk_data["message"]["content"]
                                    if content:
                                        yield content
                                
                                # Check if this is the final chunk
                                if chunk_data.get("done", False):
                                    break
                            except json.JSONDecodeError:
                                # Skip invalid JSON lines
                                continue
        
        except httpx.ConnectError:
            raise ConnectionError(
                f"Failed to connect to Ollama server at {self.base_url}. "
                "Please ensure Ollama is running (run 'ollama serve' in terminal)."
            )
        except httpx.TimeoutException:
            raise TimeoutError(
                "Request to Ollama server timed out. The model may be taking too long to respond."
            )
        except Exception as e:
            raise Exception(f"Error communicating with Ollama: {str(e)}")

