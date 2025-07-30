from faster_whisper import WhisperModel
import os
import subprocess
from uuid import uuid4
from config import logger

model = WhisperModel("base", compute_type="int8", device="cpu")

async def transcribe_voice(file_path: str) -> str:
    try:
        wav_path = f"./tmp/{uuid4().hex}.wav"
        subprocess.run(
            ["ffmpeg", "-i", file_path, "-ar", "16000", "-ac", "1", wav_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        segments, _ = model.transcribe(wav_path, language="ru")
        text = "".join([segment.text for segment in segments]).strip()

        os.remove(wav_path)
        return text

    except Exception as e:
        logger.exception(e)
        return ""
