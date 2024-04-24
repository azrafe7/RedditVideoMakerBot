import os
import re
from pathlib import Path
from typing import Tuple

import numpy as np
from moviepy.audio.AudioClip import AudioClip
from moviepy.audio.fx.volumex import volumex
from moviepy.editor import AudioFileClip
from rich.progress import (track, Progress)
from rich.markup import escape
import ffmpeg
from pathlib import Path
from video_creation.final_video import print_ffmpeg_cmd
import cleantext
from utils.unmark import unmark

from utils import settings
from utils.console import print_step, print_substep, console
from utils.voice import sanitize_text

print(f"Importing translators...", flush=True)
import translators
# _ = translators.preaccelerate_and_speedtest()
translators.get_region_of_server()

DEFAULT_MAX_LENGTH: int = (
    70  # Max video length (in seconds), edit this on your own risk. It should work, but it's not supported
)

MAX_COMMENTS = 2  # max number of comments to process, or set it to None to use DEFAULT_MAX_LENGTH

class TTSEngine:
    """Calls the given TTS engine to reduce code duplication and allow multiple TTS engines.

    Args:
        tts_module            : The TTS module. Your module should handle the TTS itself and saving to the given path under the run method.
        reddit_object         : The reddit object that contains the posts to read.
        path (Optional)       : The unix style path to save the mp3 files to. This must not have leading or trailing slashes.
        max_length (Optional) : The maximum length of the mp3 files in total.

    Notes:
        tts_module must take the arguments text and filepath.
    """

    def __init__(
        self,
        tts_module,
        reddit_object: dict,
        path: str = "assets/temp/",
        max_length: int = DEFAULT_MAX_LENGTH,
        last_clip_length: int = 0,
    ):
        self.tts_module = tts_module()
        self.reddit_object = reddit_object

        self.redditid = re.sub(r"[^\w\s-]", "", reddit_object["thread_id"])
        self.path = path + self.redditid + "/mp3"
        self.max_length = max_length
        self.length = 0
        self.last_clip_length = last_clip_length

    def add_periods(
        self, text
    ):  # adds periods to the end of paragraphs (where people often forget to put them) so tts doesn't blend sentences
        # remove links
        regex_urls = r"((http|https)\:\/\/)?[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*"
        text = re.sub(regex_urls, " ", text)
        text = text.replace("\n", ". ")
        text = re.sub(r"\bAI\b", "A.I", text)
        text = re.sub(r"\bAGI\b", "A.G.I", text)
        if text[-1] != ".":
            text += "."
        text = text.replace(". . .", ".")
        text = text.replace(".. .", ".")
        text = text.replace(". .", ".")
        text = re.sub(r'\."\.', '".', text)

        return text

    def run(self) -> Tuple[int, int]:
        Path(self.path).mkdir(parents=True, exist_ok=True)
        lang = settings.config["reddit"]["thread"]["post_lang"]
        translator = settings.config["settings"]["translator"]
        tts_engine = settings.config["settings"]["tts"]["voice_choice"]
        print_step((f"Translating (with '{translator}') and " if lang else "") + f"Saving Text to MP3 files (with '{tts_engine}')...")

        print_substep(f"DEFAULT_MAX_LENGTH: {DEFAULT_MAX_LENGTH} seconds   MAX_COMMENTS: {MAX_COMMENTS}")
        print_substep("Using [bold dark_orange]" + ("DEFAULT_MAX_LENGTH" if MAX_COMMENTS is None else "MAX_COMMENTS"))

        self.create_silence_mp3()

        self.use_random_voice = settings.config["settings"]["tts"]["random_voice"]
        
        for comment in self.reddit_object["comments"]: 
            comment = self.add_periods(comment)
        
        self.add_periods()
        print_substep(f"Saving title...")
        voice = self.tts_module.get_random_voice() if self.use_random_voice else self.get_default_voice()
        self.call_tts("title", process_text(self.reddit_object["tts_title"]), add_silence=True, voice=voice)

        processed_comments = 0
        
        if settings.config["settings"]["storymode"]:
            if settings.config["settings"]["storymodemethod"] == 0:
                self.call_tts("postaudio", process_text(self.reddit_object["thread_post"]), add_silence=True, voice=voice)
            elif settings.config["settings"]["storymodemethod"] == 1:
                with Progress(console=console) as progress:
                    task = progress.add_task("", total=None)
                    for idx, text in enumerate(self.reddit_object["thread_post"]):
                        progress.console.print(f"#{idx + 1} Saving post text...")
                        progress.advance(task)
                        processed_comments += 1
                        self.call_tts(f"postaudio-{idx}", process_text(text), add_silence=True, voice=voice)

        else:
            submission_obj = self.reddit_object["submission_obj"]
            selftext = self.reddit_object["tts_selftext"]
            if selftext:
                self.call_tts(f"postaudio", process_text(selftext), add_silence=True, voice=voice)

                # merge with title audio
                title_file = f"{self.path}/title.mp3"
                selftext_file = f"{self.path}/postaudio.mp3"
                output_file = title_file
                self.merge_audio_files([title_file, selftext_file], output_file)
            
            with Progress(console=console) as progress:
                task = progress.add_task("", total=None)
                for idx, comment in enumerate(self.reddit_object["comments"]):
                    # ! Stop creating mp3 files if the length is greater than max length, or idx >= MAX_COMMENTS.
                    must_break = False
                    if MAX_COMMENTS is None:
                        if self.length > self.max_length and idx > 1:
                            self.length -= self.last_clip_length
                            must_break = True
                    elif idx >= MAX_COMMENTS:
                        must_break = True
                        
                    if must_break:
                        break

                    progress.console.print(f"#{idx + 1} Saving comment...")
                    progress.advance(task)
                    processed_comments += 1
                
                    voice = self.tts_module.get_random_voice() if self.use_random_voice else self.get_default_voice()
                    self.call_tts(f"{idx}", process_text(comment["tts_text"]), add_silence=True, voice=voice)
                    # self.call_tts(f"{idx}", process_text(comment["comment_body"]), add_silence=True, voice=voice)

        print_substep("Saved Text to MP3 files successfully.", style="bold green")
        return self.length, processed_comments

    def split_text(self, text: str):
        splitted_text = [
            x.group().strip()
            for x in re.finditer(
                r" *(((.|\n){0," + str(self.tts_module.max_chars) + "})(\.|.$))", text
            )
        ]
        
        return splitted_text

    def split_text2(self, text: str):
        splitted_text = []
        threshold = self.tts_module.max_chars
        for chunk in re.split('\. |\n|!|\?', text):
            if splitted_text and len(chunk) + len(splitted_text[-1]) < threshold:
                splitted_text[-1] += ' ' + chunk + '.'
            else:
                splitted_text.append(chunk + '.')
        
        return splitted_text

    def split_post(self, text: str, filename):
        print(f"SPLIT_POST: self.random_voice: {self.random_voice}")
        split_files = []
        split_text = [
            x.group().strip()
            for x in re.finditer(
                r" *(((.|\n){0," + str(self.tts_module.max_chars) + "})(\.|.$))", text
            )
        ]

        idy = None
        for idy, text_cut in enumerate(split_text):
            newtext = process_text(text_cut)
            # print(f"{filename}-{idy}: {newtext}\n")

            if not newtext or newtext.isspace():
                print("newtext was blank because sanitized split text resulted in none")
                continue
            else:
                is_last_entry = idy == len(split_text) - 1
                self.call_tts(f"{filename}-{idy}.part", newtext, add_silence=is_last_entry, voice=False)
                with open(f"{self.path}/list.txt", "w") as f:
                    for idz in range(0, len(split_text)):
                        f.write("file " + f"'{filename}-{idz}.part.mp3'" + "\n")
                    split_files.append(str(f"{self.path}/{filename}-{idy}.part.mp3"))
                    f.write("file " + f"'silence.mp3'" + "\n")

                os.system(
                    "ffmpeg -f concat -y -hide_banner -loglevel panic -safe 0 "
                    + "-i "
                    + f"{self.path}/list.txt "
                    + "-c copy "
                    + f"{self.path}/{filename}.mp3"
                )
        try:
            for i in range(0, len(split_files)):
                os.unlink(split_files[i])
        except FileNotFoundError as e:
            print("File not found: " + e.filename)
        except OSError:
            print("OSError")

    def delete_files(self, files):
        try:
            for f in files:
                os.unlink(f)
        except FileNotFoundError as e:
            print("File not found: " + e.filename)
        except OSError:
            print("OSError")

    def merge_audio_files(self, audio_files, output_file, b="192k"):
        needs_temp_file = output_file in audio_files
        if needs_temp_file:
            file_to_replace = audio_files[audio_files.index(output_file)]
            stem = Path(output_file).stem
            output_file = Path(output_file).with_stem(stem + '_temp').as_posix()
        try:
            inputs = map(ffmpeg.input, audio_files)
            cmd = ffmpeg.concat(*inputs, v=0, a=1).output(output_file, **{"b:a": b}).overwrite_output()
            cmd.run(
                quiet=True,
                overwrite_output=True,
                capture_stdout=False,
                capture_stderr=False,
            )
        except ffmpeg.Error as e:
            print(e.stderr.decode("utf8"))
            exit(1)
        # overwrite original output_file if needed
        if needs_temp_file:
            Path(output_file).replace(Path(file_to_replace))

    def call_tts(self, filename: str, text: str, voice=None, add_silence=False):
        texts = [text]
        if len(text) > self.tts_module.max_chars:  # Split the text if it is too long
            # texts = self.split_text(text)
            texts = self.split_text2(text)
        
        output_file = f"{self.path}/{filename}.mp3"
        
        num_parts = len(texts)
        parts = []
        if num_parts == 1:
            print_substep(f"  [bold white]\[TTS][reset] {escape(text)}")
            filepath = output_file
            parts.append(filepath)
            self.tts_module.run(
                text,
                filepath=filepath,
                voice=voice,
            )
        else:
            for part, text in enumerate(texts):

                if not text or text.isspace():
                    print("text was blank because sanitized split text resulted in none")
                    continue
                
                print_substep(f"  [bold white]\[splitted TTS][reset] {escape(text)}")
                suffix = f"_part{part}"
                filepath = f"{self.path}/{filename}{suffix}.mp3"
                parts.append(filepath)
                self.tts_module.run(
                    text,
                    filepath=filepath,
                    voice=voice,
                )
            
            self.merge_audio_files(parts, output_file=output_file)
            if len(parts) > 1:
                print(f"delete {parts}")
                # self.delete_files(parts)
                pass
            

        if add_silence:
            tts_file = output_file
            silence_file = f"{self.path}/silence.mp3"
            self.merge_audio_files([tts_file, silence_file], output_file=output_file)

        # try:
        #     self.length += MP3(f"{self.path}/{filename}.mp3").info.length
        # except (MutagenError, HeaderNotFoundError):
        #     self.length += sox.file_info.duration(f"{self.path}/{filename}.mp3")
        try:
            clip = AudioFileClip(output_file)
            self.last_clip_length = clip.duration
            self.length += clip.duration
            clip.close()
        except:
            self.length = 0

    def create_silence_mp3(self):
        silence_duration = settings.config["settings"]["tts"]["silence_duration"]
        silence = AudioClip(
            make_frame=lambda t: np.sin(440 * 2 * np.pi * t),
            duration=silence_duration,
            fps=44100,
        )
        silence = volumex(silence, 0)
        silence.write_audiofile(f"{self.path}/silence.mp3", fps=44100, verbose=False, logger=None)


def process_text(text: str, clean: bool = True):
    lang = settings.config["reddit"]["thread"]["post_lang"]
    
    def clean_text(text):
        text = unmark(text)  # remove markdown
        text = re.sub("\.+", ".", text)  # replace multiple dots with one
        text = cleantext.clean(text, no_urls=True, replace_with_url="", lower=False, to_ascii=False, no_emoji=True)  # clean
        text = self.add_periods(text)
        return text
    
    # new_text = sanitize_text(text) if clean else text
    new_text = clean_text(text) if clean else text
    #if lang:
    #    # print(f"new_text: {new_text}")
    #    translated_text = translators.translate_text(new_text, translator=settings.config["settings"]["translator"], to_language=lang)
    #    # print(f"translated_text: {translated_text}")
    #    # new_text = sanitize_text(translated_text) if clean else translated_text
    #    new_text = clean_text(translated_text) if clean else translated_text
    #    # new_text = translated_text
    # print(f"processed_text: {new_text}")
    return new_text
