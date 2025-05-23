import glob
import json
import os
from typing import Tuple, List, Union, Any, Dict

import gradio as gr
from pytesseract.pytesseract import get_tesseract_version, TesseractNotFoundError

from mugen import MusicVideoGenerator, VideoSourceList
from mugen.video.filters import VideoFilter


class BeatGroups:
    def __init__(self, count=100):
        self.count = count
        self.slices = gr.State(self.generate_slices_from_count(count))
        self.beats = None
        self.audio = None

        # Re-Render beat groups when self.slices is changed
        @gr.render(inputs=self.slices)
        def build(slices):
            intervals = []
            splitters = []
            removers = []
            sliders = []
            for i in range(len(slices)):
                with gr.Row(variant="compact"):
                    with gr.Column():
                        chunk_start = int(slices[i]['start_index'])
                        if i == len(slices) - 1:
                            self.end = chunk_end = chunk_value = int(slices[i]['end_index'])
                        else:
                            chunk_end = int(slices[i + 1]['end_index'] - 2)
                            chunk_value = int(slices[i]['end_index'])

                        with gr.Row():
                            gr.Markdown(f"# ({chunk_start}, {chunk_value})")
                        with gr.Row(equal_height=True):
                            intervals.append(gr.Slider(label="Beat Interval",
                                                       value=slices[i]['interval'],
                                                       minimum=-10,
                                                       maximum=(chunk_value - chunk_start) - 1,
                                                       step=1,
                                                       interactive=True))
                            splitters.append(gr.Button("Split", interactive=chunk_value - chunk_start > 4))
                            removers.append(gr.Button("Remove", interactive=(i != len(slices) - 1 and len(slices) > 2)))

                        with gr.Row(equal_height=True):
                            sliders.append(gr.Slider(label="End Of Slice",
                                                     minimum=chunk_start + 2,
                                                     maximum=chunk_end,
                                                     value=chunk_value,
                                                     step=1,
                                                     interactive=(chunk_value != chunk_end)))
                            if self.audio is not None:
                                subclip = self.audio.samples[int(slices[i]['start_time'] * self.audio.sample_rate):int(slices[i]['end_time'] * self.audio.sample_rate)]
                                gr.Audio(value=(self.audio.sample_rate, subclip))


            # Update self.slices when an interval is changed
            # noinspection PyTypeChecker
            @gr.on(triggers=[interval.release for interval in intervals], inputs=intervals + [self.slices],
                   outputs=self.slices)
            def update_intervals(*inputs):
                old_slices = inputs[-1]
                new_intervals = inputs[:-1]
                new_slices = []
                for i in range(len(new_intervals)):
                    new_slices.append(
                        {'start_index': old_slices[i]['start_index'], 'end_index': old_slices[i]['end_index'],
                         'start_time': old_slices[i]['start_time'], 'end_time': old_slices[i]['end_time'],
                         'interval': new_intervals[i]})
                return new_slices

            # Update self.slices when a split button is clicked
            for i, btn in enumerate(splitters):
                input_slices = [self.slices]
                if i > 0:
                    input_slices.append(sliders[i - 1])
                input_slices.append(sliders[i])

                @btn.click(inputs=input_slices, outputs=[self.slices])
                def split_slice(*slice_list):
                    slice_split = slice_list[1:]
                    old_slices = slice_list[0]
                    new_slices = []
                    if len(slice_split) == 1:
                        for j, s in enumerate(old_slices):
                            if j == 0:
                                s1_end = s['start_index'] + ((s['end_index'] - s['start_index']) // 2)
                                new_slices.append({'start_index': 0, 'end_index': int(s1_end),
                                                   'start_time': 0, 'end_time': self.beats[int(s1_end)].location,
                                                   'interval': min(s['interval'], int(s1_end - 1))})
                                new_slices.append({'start_index': int(s1_end + 1),
                                                   'end_index': int(s['end_index']),
                                                   'start_time': self.beats[int(s1_end)].location,
                                                   'end_time': self.beats[int(s['end_index'])].location,
                                                   'interval': min(s['interval'], int(s['end_index'] - s1_end))})
                            else:
                                new_slices.append(s)
                    else:
                        for s in old_slices:
                            if s['end_index'] == slice_split[1]:
                                slice_start = slice_split[0] + 1
                                slice_end = slice_split[1]
                                s1_end = slice_start + ((slice_end - slice_start) // 2)
                                new_slices.append({'start_index': int(slice_start),
                                                   'end_index': int(s1_end),
                                                   'start_time': self.beats[int(slice_start)].location,
                                                   'end_time': self.beats[int(s1_end)].location,
                                                   'interval': min(s['interval'], int(s1_end - slice_start - 1))})
                                new_slices.append({'start_index': int(s1_end + 1),
                                                   'end_index': int(slice_end),
                                                   'start_time': self.beats[int(s1_end)].location,
                                                   'end_time': -1 if int(slice_end) == len(self.beats) - 1 else
                                                   self.beats[int(slice_end)].location,
                                                   'interval': min(s['interval'], int(slice_end - s1_end))})
                            else:
                                new_slices.append(s)
                    return new_slices

            # Update self.slices when a remove button is clicked
            for i, btn in enumerate(removers):
                @btn.click(inputs=[self.slices, sliders[i]], outputs=[self.slices])
                def remove_slice(old_slices, slice_remove):
                    new_slices = []
                    skip = False
                    for j, s in enumerate(old_slices):
                        if s['end'] == slice_remove:
                            new_slices.append(
                                {'start_index': s['start_index'], 'end_index': old_slices[j + 1]['end_index'],
                                 'start_time': s['start_time'], 'end_time': old_slices[j + 1]['end_time'],
                                 'interval': max(s['interval'], old_slices[j + 1]['interval'])})
                            skip = True
                        elif skip:
                            skip = False
                        else:
                            new_slices.append(s)
                    return new_slices

            # Update self.slices when a slider is changed
            # noinspection PyTypeChecker
            @gr.on(triggers=[slider.release for slider in sliders], inputs=sliders + [self.slices], outputs=self.slices)
            def update_slices(*inputs):
                old_slices = inputs[-1]
                slice_ends = inputs[:-1]
                new_slices = []
                slice_end = -1
                for i in range(len(slice_ends)):
                    slice_start = int(slice_end + 1)
                    if i == 0:
                        start_time = 0
                    else:
                        start_time = self.beats[slice_end].location
                    slice_end = int(inputs[i])
                    if i == len(slice_ends) - 1:
                        end_time = -1
                    else:
                        end_time = self.beats[slice_end].location
                    new_slices.append({'start_index': slice_start, 'end_index': slice_end,
                                       'start_time': start_time, 'end_time': end_time,
                                       'interval': min(old_slices[i]['interval'], int(slice_end - slice_start - 1))})
                return new_slices

    def generate_slices_from_audio(self, audio):
        self.audio = audio
        self.beats = audio.beats()
        count = len(self.beats) - 1
        midpoint = int(count / 2)
        return [{'start_index': 0, 'end_index': midpoint, 'start_time': 0, 'end_time': self.beats[midpoint].location,
                 'interval': min(4, int(midpoint - 1))},
                {'start_index': int(midpoint + 1), 'end_index': int(count),
                 'start_time': self.beats[midpoint].location, 'end_time': -1,
                 'interval': min(4, int(count - midpoint))}]

    @staticmethod
    def generate_slices_from_count(count):
        count -= 1
        midpoint = int(count / 2)
        return [{'start_index': 0, 'end_index': midpoint, 'start_time': 0, 'end_time': midpoint,
                 'interval': min(4, int(midpoint - 1))},
                {'start_index': int(midpoint + 1), 'end_index': int(count),
                 'start_time': int(midpoint + 1), 'end_time': int(count),
                 'interval': min(4, int(count - midpoint))}]


class UI:
    def __init__(self):
        self.beat_groups = None
        self.group_accordian = None
        self.use_groups = None
        self.pre_process_clips = None
        self.clip_filters = None
        self.has_low_contrast = None
        self.has_cut = None
        self.has_text = None
        self.allow_repeats = None
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
        self.beat_interval = None
        self.audio = None
        self.default_settings = self.settings = {
            "beat_open": True,
            "beat_interval": 4,
            "filter_open": False,
            "pre_process_clips": False,
            "allow_repeats": False,
            "has_text": "Off",
            "has_cut": "Exclude",
            "has_low_contrast": "Exclude"
        }
        self.load_settings()

    def launch(self):
        with gr.Blocks(theme=gr.themes.Origin()) as self.demo:
            with gr.Row():
                self.audio = gr.File(file_types=["audio"], label="Music")
            with gr.Row():
                with gr.Accordion(label="Beat", open=self.settings["beat_open"]):
                    self.use_groups = gr.Checkbox(label="Use Groups", value=False, interactive=False)
                    self.beat_interval = gr.Number(label="Beat Interval",
                                                   value=4,
                                                   minimum=-10,
                                                   precision=0,
                                                   interactive=False)
                    self.group_accordian = gr.Accordion(label="Groups", visible=False)
                    with self.group_accordian:
                        self.beat_groups = BeatGroups()

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
                with gr.Accordion(label="Clip Filters", open=self.settings["filter_open"]) as acc:
                    self.clip_filters = acc
                    with gr.Row():
                        self.pre_process_clips = gr.Checkbox(label="Pre-Process Clips",
                                                             value=self.settings['pre_process_clips'])
                    with gr.Row():
                        self.allow_repeats = gr.Checkbox(label="Allow Repeats", value=self.settings['allow_repeats'])
                        filter_states = ['Include', 'Off', 'Exclude']
                        try:
                            version = get_tesseract_version()
                            print(f"Tesseract version: {version}")
                            tesseract_installed = True
                        except TesseractNotFoundError:
                            tesseract_installed = False
                            self.update_settings({"has_text": "Off"})
                        self.has_text = gr.Radio(choices=filter_states,
                                                 label="Has Text",
                                                 value=self.settings['has_text'],
                                                 interactive=tesseract_installed)
                        self.has_cut = gr.Radio(choices=filter_states,
                                                label="Has Cut",
                                                value=self.settings['has_cut'])
                        self.has_low_contrast = gr.Radio(choices=filter_states,
                                                         label="Has Low Contrast",
                                                         value=self.settings['has_low_contrast'])

            with gr.Row():
                self.generate_button = gr.Button("Generate", variant="primary", interactive=False)
            with gr.Row():
                self.output = gr.Video(value="output.mkv")

            self.audio.upload(self.init_video_gen,
                              inputs=[self.audio, self.use_groups, self.beat_interval, self.beat_groups.slices],
                              outputs=[
                                  self.use_groups,
                                  self.beat_interval,
                                  self.group_accordian,
                                  self.beat_groups.slices,
                                  self.preview_button,
                                  self.clips,
                                  self.generate_button
                              ])
            self.audio.clear(self.de_init_video_gen,
                             outputs=[
                                 self.beat_interval,
                                 self.use_groups,
                                 self.group_accordian,
                                 self.preview_button,
                                 self.clips,
                                 self.generate_button
                             ])

            self.use_groups.change(self.toggle_beat_groups,
                                   inputs=[self.use_groups, self.beat_interval, self.beat_groups.slices],
                                   outputs=[self.beat_interval, self.group_accordian])
            self.beat_groups.slices.change(self.init_beats_from_slices,
                                           inputs=[self.beat_groups.slices],
                                           outputs=[self.preview_button, self.generate_button])
            self.beat_interval.change(self.init_beats_from_speed,
                                      inputs=[self.beat_interval],
                                      outputs=[self.preview_button, self.generate_button])
            self.preview_button.click(self.generate_preview, outputs=[self.preview])

            self.clips_refresh_btn.click(lambda: gr.update(root_dir=""),
                                         outputs=[self.clips]).then(self.refresh_clips,
                                                                    outputs=[self.empty_clips_text, self.clips])
            self.clips.change(self.init_clips, [self.clips])

            self.pre_process_clips.change(lambda x: self.update_settings({'pre_process_clips': x}),
                                          inputs=self.pre_process_clips)
            if not tesseract_installed:
                self.clip_filters.expand(self.warn_tesseract)
            self.allow_repeats.change(self.change_allow_repeats, inputs=[self.allow_repeats])
            self.has_text.change(self.change_filters, inputs=[self.has_text, self.has_cut, self.has_low_contrast])
            self.has_cut.change(self.change_filters, inputs=[self.has_text, self.has_cut, self.has_low_contrast])
            self.has_low_contrast.change(self.change_filters,
                                         inputs=[self.has_text, self.has_cut, self.has_low_contrast])

            self.generate_button.click(self.generate, inputs=[self.pre_process_clips], outputs=[self.output])

        self.demo.launch(inbrowser=True)

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
        clip_glob = glob.glob(os.getcwd() + "\\Clips\\**\\*.[am][vpk][4vi]", recursive=True)
        return len(clip_glob) == 0

    def refresh_clips(self):
        empty = self.clips_is_empty()
        return gr.update(visible=empty), gr.update(root_dir=".\\Clips")

    def init_video_gen(self, file: str, use_groups: bool, interval: int, slices: List[Dict]):
        self.save_file = file.replace('/', '\\').split('\\')[-1][:-4]
        self.generator = MusicVideoGenerator(audio_file=file)
        self.init_beats(use_groups, interval, slices)
        return (gr.update(interactive=True),
                gr.update(interactive=True, visible=not use_groups),
                gr.update(visible=use_groups),
                self.beat_groups.generate_slices_from_audio(self.generator.audio),
                gr.update(interactive=True),
                gr.update(interactive=True),
                gr.update(interactive=True))

    @staticmethod
    def de_init_video_gen():
        return (gr.update(interactive=False),
                gr.update(interactive=False),
                gr.update(visible=False),
                gr.update(interactive=False),
                gr.update(interactive=False, value=[]),
                gr.update(interactive=False))

    def toggle_beat_groups(self, on: bool, interval: int, slices: List[Dict]):
        self.init_beats(on, interval, slices)
        return gr.update(visible=not on), gr.update(visible=on)

    @staticmethod
    def convert_interval(interval: int):
        if interval > 0:
            return 1 / interval
        else:
            return abs(interval)

    def init_beats(self, use_groups: bool, interval: int, slices: List[Dict]):
        if use_groups:
            self.init_beats_from_slices(slices)
        else:
            self.init_beats_from_speed(interval)

    def init_beats_from_speed(self, interval: int):
        self.update_settings({"beat_interval": interval})
        self.beats = self.generator.audio.beats()
        self.beats.speed_multiply(self.convert_interval(interval))
        return gr.skip()

    def init_beats_from_slices(self, slices: List[Dict]):
        beats = self.generator.audio.beats()
        indexes = [(gslice['start_index'], gslice['end_index'] + 1) for gslice in slices]
        beat_groups = beats.group_by_slices(indexes)
        intervals = [self.convert_interval(gslice['interval']) for gslice in slices]
        beat_groups.selected_groups.speed_multiply(intervals)
        self.beats = beat_groups.flatten()
        return gr.skip()

    def init_clips(self, clips: Union[VideoSourceList, List[str]]):
        self.generator.video_sources = VideoSourceList(clips)

    @staticmethod
    def warn_tesseract():
        gr.Warning("Has Text filter disabled.")
        gr.Warning("Tesseract is either not installed or not in your PATH.")

    def change_allow_repeats(self, allowed: bool):
        self.update_settings({"allow_repeats": allowed})

    def change_filters(self, text: bool, cut: bool, contrast: bool):
        self.update_settings({"has_text": text, "has_cut": cut, "has_low_contrast": contrast})

    def generate(self, pre_process_clips: bool, progress=gr.Progress(track_tqdm=True)):
        filters = []
        if not self.settings["allow_repeats"]:
            filters.append(VideoFilter.not_is_repeat.name)
        if self.settings["has_low_contrast"] == "Included":
            filters.append(VideoFilter.has_low_contrast.name)
        elif self.settings["has_low_contrast"] == "Excluded":
            filters.append(VideoFilter.not_has_low_contrast.name)
        if self.settings["has_cut"] == "Included":
            filters.append(VideoFilter.has_cut.name)
        elif self.settings["has_cut"] == "Excluded":
            filters.append(VideoFilter.not_has_cut.name)
        if self.settings["has_text"] == "Included":
            filters.append(VideoFilter.has_text.name)
        elif self.settings["has_text"] == "Excluded":
            filters.append(VideoFilter.not_has_text.name)
        self.generator.video_filters = filters
        try:
            video = self.generator.generate_from_events(events=self.beats, use_filtered_sources=pre_process_clips)
        except TesseractNotFoundError:
            raise gr.Error("Tesseract not installed to be able to run text filters")
        if not os.path.exists(os.getcwd() + "\\MusicVideos"):
            os.mkdir(os.getcwd() + "\\MusicVideos")
        video.save(os.getcwd() + f"\\MusicVideos\\{self.save_file}.pickle")
        return video.write_to_video_file(os.getcwd() + f"\\MusicVideos\\{self.save_file}.mkv")

    def generate_preview(self):
        preview = self.generator.preview_from_events(self.beats, size=(50, 50))
        preview.write_to_video_file("preview.mkv")
        return "preview.mkv"


UI().launch()
