import json
from pathlib import Path
from typing import List, Optional

from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.io.ffmpeg_reader import FFMPEG_VideoReader
from moviepy.video.io.VideoFileClip import VideoFileClip

from mugen import Filter
from mugen.constants import TIME_FORMAT
from mugen.utilities import conversion, general, system
from mugen.utilities.conversion import convert_time_to_seconds
from mugen.video.segments.Segment import Segment


class VideoSegment(Segment, VideoFileClip):
    """
    A segment with video

    Attributes
    ----------
    source_start_time
        Start time of the video segment in the video file (seconds)
    """

    source_start_time: float
    _streams: List[dict]

    def __init__(self, file: str = None, **kwargs):
        """
        Parameters
        ----------
        file
            path to the video file.
            Supports any extension supported by ffmpeg, in addition to gifs.
        """
        super().__init__(file, **kwargs)

        self.source_start_time = 0
        if not self.fps:
            self.fps = Segment.DEFAULT_VIDEO_FPS
        self.duration -= 1 / self.fps
        self._streams = None

    def __repr__(self):
        return (
            f"<{self.__class__.__name__}: {self.name}, source_start_time: {self.source_start_time_time_code}, "
            f"duration: {self.duration}>"
        )

    def __getstate__(self):
        """
        Custom pickling
        """
        state = self.__dict__.copy()

        # Remove the video segment's audio and reader to allow pickling
        state["reader"] = None
        state["audio"] = None

        return state

    def __setstate__(self, newstate):
        """
        Custom unpickling
        """
        # Recreate the video segment's audio and reader
        newstate["reader"] = FFMPEG_VideoReader(newstate["filename"])
        newstate["audio"] = AudioFileClip(newstate["filename"]).subclip(
            newstate["source_start_time"],
            newstate["source_start_time"] + newstate["duration"],
        )
        self.__dict__.update(newstate)

    """ PROPERTIES """

    @property
    def file(self) -> str:
        return self.filename

    @property
    def name(self) -> str:
        return Path(self.file).stem

    @property
    def source_end_time(self) -> float:
        return self.source_start_time + self.duration

    @property
    def source_start_time_time_code(self) -> str:
        return conversion.seconds_to_time_code(self.source_start_time)

    @property
    def streams(self) -> List[dict]:
        if not self._streams:
            result = system.run_command(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    f"{self.file}",
                ]
            )
            self._streams = json.loads(result.stdout).get("streams", [])

        return self._streams

    @property
    def video_streams(self) -> List[dict]:
        return [stream for stream in self.streams if stream["codec_type"] == "video"]

    @property
    def audio_streams(self) -> List[dict]:
        return [stream for stream in self.streams if stream["codec_type"] == "audio"]

    @property
    def subtitle_streams(self) -> List[dict]:
        return [stream for stream in self.streams if stream["codec_type"] == "subtitle"]

    @property
    def video_stream(self) -> Optional[dict]:
        """Returns the primary video stream"""
        return self.video_streams[0] if len(self.video_streams) > 0 else None

    @property
    def audio_stream(self) -> Optional[dict]:
        """Returns the primary audio stream"""
        return self.audio_streams[0] if len(self.audio_streams) > 0 else None

    """ METHODS """

    @convert_time_to_seconds(["start_time", "end_time"])
    def subclip(
            self, start_time: TIME_FORMAT = 0, end_time: TIME_FORMAT = None
    ) -> "VideoSegment":
        """
        Returns a clip playing the content of the current clip
        between times ``start_time`` and ``end_time``, which can be expressed
        in seconds (15.35), in (min, sec), in (hour, min, sec), or as a
        string: '01:03:05.35'.
        If ``end_time`` is not provided, it is assumed to be the duration
        of the clip (potentially infinite).
        If ``end_time`` is a negative value, it is reset to
        ``clip.duration + end_time. ``. For instance: ::

            >>> # cut the last two seconds of the clip:
            >>> newclip = clip.subclip(0,-2)

        If ``end_time`` is provided or if the clip has a duration attribute,
        the duration of the returned clip is set automatically.

        The ``mask`` and ``audio`` of the resulting subclip will be
        subclips of ``mask`` and ``audio`` the original clip, if
        they exist.
        """
        if start_time < 0:
            # Make this more Python-like, a negative value means to move
            # backward from the end of the clip
            start_time = self.duration + start_time  # Remember start_time is negative

        if (self.duration is not None) and (start_time > self.duration):
            raise ValueError("start_time (%.02f) " % start_time +
                             "should be smaller than the clip's " +
                             "duration (%.02f)." % self.duration)

        newclip = self.time_transform(lambda t: t + start_time, apply_to=[])

        if (end_time is None) and (self.duration is not None):

            end_time = self.duration

        elif (end_time is not None) and (end_time < 0):

            if self.duration is None:

                print("Error: subclip with negative times (here %s)" % (str((start_time, end_time)))
                      + " can only be extracted from clips with a ``duration``")

            else:

                end_time = self.duration + end_time

        if end_time is not None:
            newclip.duration = end_time - start_time
            newclip.end = newclip.start + newclip.duration

        # Clear filter results which are otherwise copied over to the new subclip
        newclip.passed_filters = []
        newclip.failed_filters = []

        if start_time < 0:
            # Set relative to end
            start_time = self.duration + start_time

        newclip.source_start_time += start_time

        return newclip

    def trailing_buffer(self, duration) -> "VideoSegment":
        return VideoSegment(self.file).subclip(
            self.source_end_time, self.source_end_time + duration
        )

    def overlaps_segment(self, segment: "VideoSegment") -> bool:
        if not self.file == segment.file:
            return False

        return general.check_if_ranges_overlap(
            self.source_start_time,
            self.source_end_time,
            segment.source_start_time,
            segment.source_end_time,
        )

    def get_subtitle_stream_content(self, stream: int) -> str:
        """Returns the subtitle stream's content"""
        result = system.run_command(
            [
                "ffmpeg",
                "-v",
                "quiet",
                "-i",
                self.file,
                "-map",
                f"0:s:{stream}",
                "-f",
                "srt",
                "pipe:1",
            ]
        )
        return result.stdout


class FilteredVideoSegment:
    def __init__(self, file: str, start: float, end: float):
        self.file = file
        self.start = start
        self.end = end
        self.filters = {"is_repeat": False, "not_is_repeat": True}
        self.rejected = None

    def overlaps_segment(self, segment: "FilteredVideoSegment") -> bool:
        if not self.file == segment.file:
            return False

        return general.check_if_ranges_overlap(
            self.start,
            self.end,
            segment.start,
            segment.end,
        )

    def contains_segment(self, segment: "FilteredVideoSegment") -> bool:
        if not self.file == segment.file:
            return False

        return self.start <= segment.start and self.end >= segment.end

    def passes_filters(self, video_filters: List[Filter]):
        for video_filter in video_filters:
            if video_filter.name not in self.filters:
                self.reject()
                return False
            if not self.filters[video_filter.name]:
                self.reject()
                return False
        self.rejected = False
        return True

    def reject(self):
        if self.rejected is None:
            self.rejected = True

    @property
    def segment(self) -> "VideoSegment":
        return VideoSegment(self.file).subclip(self.start, self.end)

    def filter(self, video_filters: List[Filter]):
        for video_filter in video_filters:
            if video_filter.name not in self.filters:
                result = video_filter(self.segment)
                self.filters[video_filter.name] = result
                if video_filter.name.startswith("not_"):
                    self.filters[video_filter.name[4:]] = not result
                else:
                    self.filters["not_" + video_filter.name] = not result
