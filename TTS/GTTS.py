import random

from gtts import gTTS

from utils import settings


class GTTS:
    def __init__(self):
        self.max_chars = 5000
        self.voices = []
        self.default_voice = None

    def run(self, text, filepath, voice=None):
        tts = gTTS(
            text=text,
            lang=settings.config["reddit"]["thread"]["post_lang"] or "en",
            slow=False,
        )
        tts.save(filepath)

    def get_random_voice(self):
        return random.choice(self.voices)

    def get_default_voice(self):
        return self.default_voice