# thin wrapper around https://github.com/Giooorgiooo/TikTok-Voice-TTS
import base64
import random
import time
from typing import Optional, Final
from third_party.tiktokvoice import tiktokvoice

import requests

from utils import settings

__all__ = ["TikTokVoice", "TikTokVoiceException"]

disney_voices: Final[tuple] = (
    "en_us_ghostface",  # Ghost Face
    "en_us_chewbacca",  # Chewbacca
    "en_us_c3po",  # C3PO
    "en_us_stitch",  # Stitch
    "en_us_stormtrooper",  # Stormtrooper
    "en_us_rocket",  # Rocket
    "en_female_madam_leota",  # Madame Leota
    "en_male_ghosthost",  # Ghost Host
    "en_male_pirate",  # pirate
)

eng_voices: Final[tuple] = (
    "en_au_001",  # English AU - Female
    "en_au_002",  # English AU - Male
    "en_uk_001",  # English UK - Male 1
    "en_uk_003",  # English UK - Male 2
    "en_us_001",  # English US - Female (Int. 1)
    "en_us_002",  # English US - Female (Int. 2)
    "en_us_006",  # English US - Male 1
    "en_us_007",  # English US - Male 2
    "en_us_009",  # English US - Male 3
    "en_us_010",  # English US - Male 4
    "en_male_narration",  # Narrator
    "en_male_funny",  # Funny
    "en_female_emotional",  # Peaceful
    "en_male_cody",  # Serious
)

non_eng_voices: Final[tuple] = (
    # Western European voices
    "fr_001",  # French - Male 1
    "fr_002",  # French - Male 2
    "de_001",  # German - Female
    "de_002",  # German - Male
    "es_002",  # Spanish - Male
    "it_male_m18",  # Italian - Male
    # South american voices
    "es_mx_002",  # Spanish MX - Male
    "br_001",  # Portuguese BR - Female 1
    "br_003",  # Portuguese BR - Female 2
    "br_004",  # Portuguese BR - Female 3
    "br_005",  # Portuguese BR - Male
    # asian voices
    "id_001",  # Indonesian - Female
    "jp_001",  # Japanese - Female 1
    "jp_003",  # Japanese - Female 2
    "jp_005",  # Japanese - Female 3
    "jp_006",  # Japanese - Male
    "kr_002",  # Korean - Male 1
    "kr_003",  # Korean - Female
    "kr_004",  # Korean - Male 2
)

vocals: Final[tuple] = (
    "en_female_f08_salut_damour",  # Alto
    "en_male_m03_lobby",  # Tenor
    "en_male_m03_sunshine_soon",  # Sunshine Soon
    "en_female_f08_warmy_breeze",  # Warmy Breeze
    "en_female_ht_f08_glorious",  # Glorious
    "en_male_sing_funny_it_goes_up",  # It Goes Up
    "en_male_m2_xhxs_m03_silly",  # Chipmunk
    "en_female_ht_f08_wonderful_world",  # Dramatic
)


class TikTokVoice:
    """TikTokVoice Text-to-Speech Wrapper"""

    def __init__(self):
        self.max_chars = 300
        
        # merge and patch VOICES
        self.all_voices = list(set(disney_voices + eng_voices + non_eng_voices + vocals) | set(tiktokvoice.VOICES))
        # print(f"{self.all_voices}")
        self.default_voice = settings.config["settings"]["tts"]["tiktok_voice"]
        tiktokvoice.VOICES = self.all_voices

    def run(self, text: str, filepath: str, voice = None):
        if voice is None:
            voice = self.get_default_voice()

        tiktokvoice.tts(text=text, voice=voice, output_filename=filepath)

    def get_random_voice(self) -> str:
        lang = settings.config["reddit"]["thread"]["post_lang"]
        if not lang:
            return random.choice(eng_voices)
        else:
            return self.default_voice

    def get_default_voice(self):
        return self.default_voice

class TikTokVoiceException(Exception):
    def __init__(self, code: int, message: str):
        self._code = code
        self._message = message

    def __str__(self) -> str:
        if self._code == 1:
            return f"Code: {self._code}, reason: probably the aid value isn't correct, message: {self._message}"

        if self._code == 2:
            return f"Code: {self._code}, reason: the text is too long, message: {self._message}"

        if self._code == 4:
            return f"Code: {self._code}, reason: the speaker doesn't exist, message: {self._message}"

        return f"Code: {self._message}, reason: unknown, message: {self._message}"
