import glob
import json
import os
from typing import Tuple, List, Union, Any

import gradio as gr
from pytesseract.pytesseract import TesseractNotFoundError

from mugen import MusicVideoGenerator, VideoSourceList, VideoSource
from mugen.video.filters import VideoFilter


class UI:
    def __init__(self):
        self.save_file = None
        self.beats = None
        self.generator = None
        self.clips_refresh_btn = None
        self.empty_clips_text = None
        self.clips_reload = None
        self.output = None
        self.generate_button = None
        self.clips = None
        self.preview = None
        self.preview_button = None
        self.beat = None
        self.audio = None
        self.default_settings = self.settings = {
            "beat_open": True,
            "beat_interval": 4,
        }
        self.load_settings()

    def launch(self):
        with gr.Blocks(theme=gr.themes.Origin()) as self.demo:
            with gr.Row():
                self.audio = gr.File(file_types=["audio"], label="Music")
            with gr.Row():
                with gr.Accordion(label="Beat", open=self.settings["beat_open"]):
                    self.beat = gr.Number(label="Beat Interval", value=4, minimum=1, precision=0)

                    self.preview_button = gr.Button("Generate Beat Preview", variant="primary", interactive=False)
                    with gr.Accordion(label="Preview", open=False):
                        self.preview = gr.Video()

            with gr.Row():
                with gr.Accordion(label="Video Clips", open=True):
                    self.empty_clips_text = gr.Text("Add video clips to the Clips folder and click 'refresh'",
                                                    visible=self.clips_is_empty(), show_label=False, container=False)
                    self.clips_refresh_btn = gr.Button("Refresh")
                    self.clips = gr.FileExplorer(label="Clips", ignore_glob="**/.*",
                                                 glob="**/*.[am][vpk][4vi]", root_dir=".\\Clips",
                                                 file_count="multiple", interactive=False)
            with gr.Row():
                self.generate_button = gr.Button("Generate", variant="primary", interactive=False)
            with gr.Row():
                self.output = gr.Video(value="output.mkv")

            self.audio.upload(self.init_video_gen, inputs=[self.audio, self.beat],
                              outputs=[self.preview_button, self.clips, self.generate_button])
            self.audio.clear(self.de_init_video_gen, outputs=[self.preview_button, self.clips, self.generate_button])

            self.beat.change(self.init_beats_from_speed, inputs=[self.beat])
            self.preview_button.click(self.generate_preview, outputs=[self.preview])

            self.clips_refresh_btn.click(lambda: gr.update(root_dir=""),
                                         outputs=[self.clips]).then(self.refresh_clips,
                                                                    outputs=[self.empty_clips_text, self.clips])
            self.clips.change(self.init_clips, [self.clips])

            self.generate_button.click(self.generate, outputs=[self.output])

        self.demo.launch()

    def load_settings(self):
        try:
            with open("settings.json", "r") as f:
                self.settings = json.load(f)
            # Ensure all keys in default_settings are present in settings
            settings_updated = False
            for key in self.default_settings:
                if key not in self.settings:
                    self.settings[key] = self.default_settings[key]
                    settings_updated = True
            if settings_updated:
                self.save_settings()

        except FileNotFoundError:
            self.save_settings()

    def update_settings(self, updates: dict):
        for setting, value in updates.items():
            if setting in self.settings:
                self.settings[setting] = value
            else:
                print(f"'{setting}' is not a valid setting, skipping...")
        self.save_settings()

    def save_settings(self):
        with open("settings.json", "w") as f:
            json.dump(self.settings, f)

    @staticmethod
    def clips_is_empty():
        clip_glob = glob.glob(os.getcwd()+"\\Clips\\**\\*.[am][vpk][4vi]", recursive=True)
        return len(clip_glob) == 0

    def refresh_clips(self):
        empty = self.clips_is_empty()
        return gr.update(visible=empty), gr.update(root_dir=".\\Clips")

    def init_video_gen(self, file: str, interval: int):
        self.save_file = file.replace('/', '\\').split('\\')[-1][:-4]
        self.generator = MusicVideoGenerator(audio_file=file)
        self.init_beats_from_speed(interval)
        return gr.update(interactive=True), gr.update(interactive=True), gr.update(interactive=True)

    @staticmethod
    def de_init_video_gen():
        return gr.update(interactive=False), gr.update(interactive=False, value=[]), gr.update(interactive=False)

    def init_beats_from_speed(self, interval: int):
        self.beats = self.generator.audio.beats()
        self.beats.speed_multiply(1 / interval)

    def init_beats_from_slices(self, slices: List[Tuple[int, int, float]]):
        beats = self.generator.audio.beats()
        beat_groups = beats.group_by_slices([(start, end) for start, end, _ in slices])
        beat_groups.selected_groups.speed_multiply([speed for _, _, speed in slices])
        self.beats = beat_groups.flatten()

    def init_clips(self, clips: Union[VideoSourceList, List[str]]):
        self.generator.video_sources = VideoSourceList(clips)

    def generate(self):
        try:
            video = self.generator.generate_from_events(self.beats)
        except TesseractNotFoundError:
            raise gr.Error("Tesseract not installed to be able to run text filters")
        video.save(f"MusicVideos\\{self.save_file}.pickle")
        return video.write_to_video_file(f"MusicVideos\\{self.save_file}.mkv")

    def generate_preview(self):
        preview = self.generator.preview_from_events(self.beats)
        preview.write_to_video_file("preview.mkv")
        return "preview.mkv"


UI().launch()
