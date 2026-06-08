class TextHelper:
    async def detect_language(self, text: str) -> str:
        devanagari = sum(1 for char in text if "\u0900" <= char <= "\u097F")
        return "hi" if devanagari > len(text) * 0.1 else "en"

    async def translate_to_english(self, text: str) -> str:
        raise NotImplementedError("Translation will be implemented after account/auth.")

    def clean_text(self, text: str) -> str:
        return " ".join(text.split())

    def truncate_safe(self, text: str, max_len: int = 2000) -> str:
        return text[:max_len] + "..." if len(text) > max_len else text
