import random

import pyttsx3

from utils import settings


class pyttsx:
    def __init__(self):
        self.max_chars = 5000
        self.voices = []
        self.default_voice = settings.config["settings"]["tts"]["python_voice"]

        self.engine = pyttsx3.init()
        voice_id = settings.config["settings"]["tts"]["python_voice"]
        voice_num = settings.config["settings"]["tts"]["py_voice_num"]
        if voice_id == "" or voice_num == "":
            voice_id = 2
            voice_num = 3
            raise ValueError("set pyttsx values to a valid value, switching to defaults")
        self.voices = range(0, len(engine.getProperty("voices")))

    def run(
        self,
        text: str,
        filepath: str,
        voice=None,
    ):
        if voice is None:
            voice = self.get_default_voice()

        self.engine.setProperty(
            "voice", voices[int(voice)].id
        )  # changing index changes voices but ony 0 and 1 are working here
        engine.save_to_file(text, f"{filepath}")
        engine.runAndWait()

    def get_random_voice(self):
        return random.choice(self.voices)

    def get_default_voice(self):
        return self.default_voice