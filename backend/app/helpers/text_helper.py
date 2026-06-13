from openai import AsyncOpenAI

from app.config import settings


class TextHelper:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.EMBEDDING_API_KEY or settings.GITHUB_TOKEN,
            base_url=settings.EMBEDDING_BASE_URL,
        )

    async def detect_language(self, text: str) -> str:
        devanagari = sum(1 for char in text if "\u0900" <= char <= "\u097F")
        return "hi" if devanagari > len(text) * 0.1 else "en"

    async def translate_to_english(self, text: str) -> str:
        response = await self.client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Translate the following Hindi text to English. Return only the translation.",
                },
                {"role": "user", "content": text},
            ],
            extra_body={"reasoning": {"enabled": True}},
        )
        return response.choices[0].message.content.strip()

    def clean_text(self, text: str) -> str:
        return " ".join(text.split())

    def truncate_safe(self, text: str, max_len: int = 2000) -> str:
        return text[:max_len] + "..." if len(text) > max_len else text
