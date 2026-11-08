import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.monica_client import MonicaClient
from app.models.openai_types import ChatMessage
import asyncio
import json

async def main():
    with open("data/cookies.json", "r", encoding="utf-8") as f:
        cookies = json.load(f)
    c = cookies[0]
    client = MonicaClient(cookie=c["cookie"])
    messages = [ChatMessage(role="user", content="hi")]
    try:
        resp = await client.chat(messages, model="gemini-3-flash-preview", stream=False)
        print("Success chat response:", resp.choices[0].message.content[:200])
    except Exception as e:
        print("Chat failed:", type(e), e)

asyncio.run(main())
