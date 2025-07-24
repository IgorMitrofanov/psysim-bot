from config import config, logger
from openai import OpenAI
import asyncio
from typing import Dict, List, Tuple


client = OpenAI(api_key=config.AI_API_KEY)

def sync_get_response(messages, temperature, max_tokens):
    response = client.chat.completions.create(
        model=config.DEFAULT_MODEL,
        messages=messages,
        temperature=temperature,
    )
    reply = response.choices[0].message.content
    tokens = response.usage.total_tokens if response.usage else 0
    return reply, tokens

async def call_llm_for_meta_ai(
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 150
    ) -> Tuple[str, int]:
        """
        Make a call to LLM.
        
        Args:
            system_prompt: System message for LLM
            user_prompt: User message for LLM
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            Tuple of (LLM response, tokens used)
        """
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response, tokens = await get_response(
                messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            logger.debug(f"LLM response: {response[:200]}... (tokens: {tokens})")
            return response.strip(), tokens
            
        except Exception as e:
            logger.error(f"[AI-decision system] LLM call error: {str(e)}", exc_info=True)
            return "", 0

async def get_response(messages, temperature=0.8, max_tokens=None):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, sync_get_response, messages, temperature, max_tokens)
