from utils.api_client import APIClient


class VoiceService:
    def __init__(self):
        self.client = APIClient()

    def transcribe(self, audio_bytes: bytes, filename: str, language: str = "en") -> dict:
        return self.client.post_multipart(
            "/voice/transcribe",
            files={"audio_file": (filename, audio_bytes)},
            data={"language": language},
        )
