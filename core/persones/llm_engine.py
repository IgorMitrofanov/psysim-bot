from config import config, logger
from openai import OpenAI
import asyncio

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

async def get_response(messages, temperature=1, max_tokens=None):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, sync_get_response, messages, temperature, max_tokens)
