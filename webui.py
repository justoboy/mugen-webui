import glob
import json
import os

import gradio as gr
from mugen import MusicVideoGenerator
from mugen.video.filters import VideoFilter


class UI:
    def __init__(self):
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

                    self.preview_button = gr.Button("Generate Beat Preview", variant="primary")
                    with gr.Accordion(label="Preview", open=False):
                        self.preview = gr.Video(value="preview.mkv")

            with gr.Row():
                with gr.Accordion(label="Video Clips", open=True):
                    self.empty_clips_text = gr.Text("Add video clips to the Clips folder and click 'refresh'",
                                                    visible=self.clips_is_empty(), show_label=False)
                    self.clips_refresh_btn = gr.Button("Refresh")
                    self.clips = gr.FileExplorer(label="Clips", ignore_glob="**/.*",
                                                 glob="**/*.[am][vpk][4vi]", root_dir=".\\Clips")
            with gr.Row():
                self.generate_button = gr.Button("Generate", variant="primary")
            with gr.Row():
                self.output = gr.Video(value="output.mkv")

            self.preview_button.click(generate_preview, [self.audio, self.beat], [self.preview])

            self.clips_refresh_btn.click(lambda: gr.update(root_dir=""),
                                         outputs=[self.clips]).then(self.refresh_clips,
                                                                    outputs=[self.empty_clips_text, self.clips])

            self.generate_button.click(generate, [self.audio, self.beat, self.clips], [self.output])

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
        clip_glob = glob.glob(os.getcwd()+"\\Clips\\**/*.[am][vpk][4vi]")
        return len(clip_glob) == 0

    def refresh_clips(self):
        empty = self.clips_is_empty()
        return gr.update(visible=empty), gr.update(root_dir=".\\Clips")


def generate_preview(audio_file, beat):
    if audio_file is not None:
        if beat is not None:
            generator = MusicVideoGenerator(audio_file)
            beats = generator.audio.beats()
            beats.speed_multiply(1 / beat)

            preview = generator.preview_from_events(beats)
            print(preview.write_to_video_file("preview.mkv"))
        else:
            gr.Warning("No beat interval given!")
    else:
        gr.Warning("No audio file chosen!")
    return "preview.mkv"


def generate(audio_file, beat, clips):
    if audio_file is not None:
        if beat is not None:
            generator = MusicVideoGenerator(audio_file, clips)
            generator.exclude_video_filters = [VideoFilter.not_is_repeat.name, VideoFilter.not_has_cut.name,
                                               VideoFilter.not_has_text.name]
            beats = generator.audio.beats()
            beats.speed_multiply(1 / beat)

            video = generator.generate_from_events(beats)
            save_name = audio_file.replace('/', '\\').split('\\')[-1][:-4]
            video.save(f"MusicVideos\\{save_name}.pickle")
            return video.write_to_video_file(f"MusicVideos\\{save_name}.mkv")
        else:
            raise gr.Error("No beat interval given!")
    else:
        raise gr.Error("No audio file chosen!")


UI().launch()
