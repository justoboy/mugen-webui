import glob as globber
import os
import random
import re
from abc import ABC
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple, Union

from numpy.random import choice
from tqdm import tqdm

from mugen import Filter
from mugen.constants import TIME_FORMAT
from mugen.exceptions import ParameterError
from mugen.mixins.Taggable import Taggable
from mugen.mixins.Weightable import Weightable
from mugen.utilities import system
from mugen.utilities.conversion import convert_time_to_seconds
from mugen.video.exceptions import SegmentNotFoundError
from mugen.video.segments.VideoSegment import VideoSegment, FilteredVideoSegment
from mugen.video.sources.Source import Source, SourceList

GLOB_STAR = "*"


class TimeRangeBase(NamedTuple):
    start: float
    end: float


class TimeRange(TimeRangeBase):
    __slots__ = ()

    @convert_time_to_seconds(["start", "end"])
    def __new__(cls, start, end):
        self = super().__new__(cls, start, end)
        return self

    @property
    def duration(self):
        return self.end - self.start


class VideoSource(Source):
    """
    A video source for sampling video segments
    """

    time_boundaries: List[Tuple[(TIME_FORMAT, TIME_FORMAT)]]

    def __init__(
            self,
            file: str,
            *,
            time_boundaries: Optional[List[Tuple[(TIME_FORMAT, TIME_FORMAT)]]] = None,
            **kwargs,
    ):
        """
        Parameters
        ----------
        file
            video file to sample from

        time_boundaries
            the set of time ranges to sample from in the video.
            For supported formats, see :data:`~mugen.constants.TIME_FORMAT`.
        """
        super().__init__(**kwargs)
        self.segment = VideoSegment(file)
        self.time_boundaries = time_boundaries if time_boundaries else []

    def __repr__(self):
        return (
            f"<{self.__class__.__name__}: {self.name}, duration: {self.segment.duration_time_code}, "
            f"weight: {self.weight}>"
        )

    @property
    def file(self):
        return self.segment.file

    @property
    def name(self):
        return self.segment.name

    def sample(self, duration: float) -> VideoSegment:
        """
        Randomly samples a video segment with the specified duration.

        Parameters
        ----------
        duration
            duration of the video segment to sample
        """
        if self.time_boundaries:
            # Select a random time boundary to sample from, weighted by duration
            time_ranges = [TimeRange(*boundary) for boundary in self.time_boundaries]
            time_ranges = [
                time_range
                for time_range in time_ranges
                if time_range.duration >= duration
            ]
            total_duration = sum([time_range.duration for time_range in time_ranges])
            time_range_weights = [
                time_range.duration / total_duration for time_range in time_ranges
            ]
            time_range_to_sample = time_ranges[
                choice(len(time_ranges), p=time_range_weights)
            ]
        else:
            time_range_to_sample = TimeRange(0, self.segment.duration)
        start_time = random.uniform(
            time_range_to_sample.start, time_range_to_sample.end - duration
        )
        sampled_clip = self.segment.subclip(start_time, start_time + duration)
        return sampled_clip


class FilteredVideoSource(Taggable, Weightable, ABC):
    """
    A video source for sampling and filtered video segments
    """

    time_boundaries: List[Tuple[(TIME_FORMAT, TIME_FORMAT)]]

    def __init__(self, file: str, durations: List[float], *args, **kwargs):
        """
        Parameters
        ----------
        file
            video file to filter and sample from

        durations
            the durations that can be filtered and sampled
        """
        super().__init__(*args, **kwargs)
        if os.path.exists(file) and os.path.isfile(file):
            self.file = file
        else:
            raise FileNotFoundError(f"File {file} does not exist.")
        self.durations = list(set(durations))
        self.durations.sort(reverse=True)
        video_segment = VideoSegment(file)
        self.segments = {}

        for duration in durations:
            self.segments[duration] = []
            i = 0
            while i < video_segment.duration - duration:
                self.segments[duration].append(FilteredVideoSegment(file, i, i + duration))
                i += duration
            # if i < self.length:
            #     self.segments[duration].append(FilteredVideoSegment(self.length-duration, self.length))

    def filter_segments(self, filters: List[Filter]):
        for duration in self.segments.values():
            for segment in duration:
                segment.filter(filters)

    def get_filtered_segments(self, duration: float, filters: List[Filter])\
            -> List[FilteredVideoSegment]:
        filtered_segments = []
        if duration not in self.segments:
            return filtered_segments
        for segment in self.segments[duration]:
            if segment.passes_filters(filters):
                filtered_segments.append(segment)
        return filtered_segments

    def sample_segment(self, filtered_segment: FilteredVideoSegment):
        filtered_segment.filters.update({'is_repeat': True, 'not_is_repeat': False})
        for duration in self.segments.values():
            for segment in duration:
                if segment is not filtered_segment and segment.overlaps_segment(filtered_segment):
                    segment.filters.update({'is_repeat': True, 'not_is_repeat': False})
        return filtered_segment.segment

    def sample(self, duration: float, filters: List[Filter]) -> VideoSegment:
        """
        Randomly samples a segment with the specified duration

        Parameters
        ----------
        duration
            duration of the sample

        filters
            filters the sample must pass

        Returns
        -------
        A randomly sampled segment with the specified duration that passes all specified filters
        """
        segments = self.get_filtered_segments(duration, filters)
        selected_segment = choice(segments)
        sample = self.sample_segment(selected_segment)

        return sample

    def get_rejected_segments(self):
        rejected_segments = []
        for duration in self.segments.values():
            for segment in duration:
                if segment.rejected:
                    rejected_segments.append(segment.segment)
        return rejected_segments


class VideoSourceList(SourceList):
    """
    A list of video sources
    """

    name: Optional[str]

    def __init__(
            self,
            sources=Optional[Union[List[Union[str, Source, "VideoSourceList"]], str]],
            **kwargs,
    ):
        """
        Parameters
        ----------
        sources
            A list of sources.
            Accepts arbitrarily nested video files, directories, globs, Sources, VideoSources, and VideoSourceLists.
        """
        self.name = None
        video_sources = []

        if isinstance(sources, str):
            self.name = Path(sources).stem
            video_sources = self._get_sources_from_path(sources)
        else:
            video_sources = self._get_sources_from_list(sources)

        super().__init__(video_sources, **kwargs)

    def list_repr(self):
        """
        Repr for use in lists
        """
        if self.name:
            return f"<{self.__class__.__name__} ({len(self)}): {self.name}, weight: {self.weight}>"

        return super().list_repr()

    @staticmethod
    def _get_sources_from_path(
            path: str,
    ) -> List[Union[VideoSource, "VideoSourceList"]]:
        sources = []

        if GLOB_STAR in path:
            sources = VideoSourceList._get_sources_from_glob_path(path)
        elif os.path.isdir(path):
            sources = VideoSourceList._get_sources_from_directory(path)
        else:
            sources = [VideoSource(path)]

        if len(sources) == 0:
            raise IOError(f"No file(s) found for {path}")

        return sources

    @staticmethod
    def _get_sources_from_glob_path(
            glob_path: str,
    ) -> List[Union[VideoSource, "VideoSourceList"]]:
        sources = []
        # Escape square brackets, which are common in file names and affect glob
        paths = globber.glob(re.sub(r"([\[\]])", "[\\1]", glob_path))
        for path in paths:
            path_sources = VideoSourceList._get_sources_from_path(path)
            if os.path.isdir(path):
                sources.append(VideoSourceList(path_sources))
            else:
                sources.extend(path_sources)

        return sources

    @staticmethod
    def _get_sources_from_directory(
            directory: str,
    ) -> List[Union[VideoSource, "VideoSourceList"]]:
        sources = []
        for file in system.list_directory_files(directory):
            try:
                sources.append(VideoSource(file))
            except IOError:
                continue

        return sources

    @staticmethod
    def _get_sources_from_list(
            sources_list: List[Union[str, Source, "VideoSourceList"]],
    ) -> List[Union[Source, "VideoSourceList"]]:
        sources = []
        for source in sources_list:
            if isinstance(source, str) and os.path.isfile(source):
                sources.extend(VideoSourceList._get_sources_from_path(source))
            elif isinstance(source, str):
                sources.append(
                    VideoSourceList(VideoSourceList._get_sources_from_path(source))
                )
            elif isinstance(source, Source) or isinstance(source, VideoSourceList):
                sources.append(source)
            elif isinstance(source, list):
                sources.append(VideoSourceList(source))
            else:
                raise ParameterError(f"Unknown source type {source}")

        return sources


class FilteredVideoSourceList(SourceList):
    """
    A list of video sources
    """

    name: Optional[str]

    def __init__(
            self,
            sources: Union[
                    List[
                        Union[
                            str,
                            Source,
                            VideoSource,
                            FilteredVideoSource,
                            VideoSourceList,
                            "FilteredVideoSourceList"
                        ]
                    ],
                    str
                ],
            durations: List[float],
            filters: List[Filter],
            **kwargs,
    ):
        """
        Parameters
        ----------
        sources
            A list of sources.
            Accepts arbitrarily nested video files, directories, globs.
            As well as filtered and normal Sources, VideoSources, and VideoSourceLists.
        """
        self.name = None
        self.durations = durations
        self.filters = filters
        video_sources = []

        if isinstance(sources, str):
            self.name = Path(sources).stem
            video_sources = self._get_sources_from_path(sources)
        else:
            video_sources = self._get_sources_from_list(sources)

        super().__init__(video_sources, **kwargs)

    def list_repr(self):
        """
        Repr for use in lists
        """
        if self.name:
            return f"<{self.__class__.__name__} ({len(self)}): {self.name}, weight: {self.weight}>"

        return super().list_repr()

    def _get_sources_from_path(self, path: str) -> List[Union[FilteredVideoSource, "FilteredVideoSourceList"]]:
        sources = []

        if GLOB_STAR in path:
            sources = self._get_sources_from_glob_path(path)
        elif os.path.isdir(path):
            sources = self._get_sources_from_directory(path)
        else:
            sources = [FilteredVideoSource(path, self.durations)]

        if len(sources) == 0:
            raise IOError(f"No file(s) found for {path}")

        return sources

    def _get_sources_from_glob_path(self, glob_path: str)\
            -> List[Union[FilteredVideoSource, "FilteredVideoSourceList"]]:
        sources = []
        # Escape square brackets, which are common in file names and affect glob
        paths = globber.glob(re.sub(r"([\[\]])", "[\\1]", glob_path))
        for path in paths:
            path_sources = self._get_sources_from_path(path)
            if os.path.isdir(path):
                sources.append(FilteredVideoSourceList(path_sources, self.durations, self.filters))
            else:
                sources.extend(path_sources)

        return sources

    def _get_sources_from_directory(
            self,
            directory: str,
    ) -> List[Union[FilteredVideoSource, "FilteredVideoSourceList"]]:
        sources = []
        for file in system.list_directory_files(directory):
            try:
                sources.append(FilteredVideoSource(file, self.durations))
            except IOError:
                continue

        return sources

    def _get_sources_from_list(
            self,
            sources_list: Optional[
                List[
                    Union[
                        str,
                        Source,
                        VideoSource,
                        FilteredVideoSource,
                        VideoSourceList,
                        "FilteredVideoSourceList"
                    ]
                ]
            ],
    ) -> List[Union[FilteredVideoSource, "FilteredVideoSourceList"]]:
        sources = []
        for source in sources_list:
            if isinstance(source, str) and os.path.isfile(source):
                sources.extend(self._get_sources_from_path(source))
            elif isinstance(source, str):
                sources.append(
                    VideoSourceList(self._get_sources_from_path(source))
                )
            elif isinstance(source, VideoSource):
                sources.append(FilteredVideoSource(source.file, self.durations))
            elif isinstance(source, VideoSourceList):
                sources.append(FilteredVideoSourceList(source, self.durations, self.filters))
            elif isinstance(source, FilteredVideoSourceList):
                source.append(source)
            elif isinstance(source, list):
                sources.append(FilteredVideoSourceList(source, self.durations, self.filters))
            else:
                raise ParameterError(f"Unknown source type {source}")

        return sources

    def filter_sources(self, show_progress: bool = True):
        for source in tqdm(self, disable=not show_progress):
            source.filter_segments(self.filters)

    def get_filtered_sources(self, duration: float, filters: Optional[List[Filter]] = None)\
            -> List[FilteredVideoSource]:
        if filters is None:
            filters = self.filters
        filtered_sources = []
        for source in self:
            if len(source.get_filtered_segments(duration, filters)) > 0:
                filtered_sources.append(source)
        return filtered_sources

    def sample(self, duration: float, filters: Optional[List[Filter]] = None) -> VideoSegment:
        """
        Randomly samples a segment with the specified duration

        Parameters
        ----------
        duration
            duration of the sample

        filters
            filters the sample must pass

        Returns
        -------
        A randomly sampled segment with the specified duration that passes all specified filters
        """
        sources = self.get_filtered_sources(duration, filters)
        if len(sources) == 0:
            raise SegmentNotFoundError(f"Unable to find FilteredVideoSegment that passes given filters: {filters}\n"
                                       "Try adding more video sources or removing some filters "
                                       "(not_is_repeat and not_has_cut are the most likely to cause this)")
        weights = [source.weight for source in sources]
        weight_sum = sum(weights)
        normalized_weights = [weight / weight_sum for weight in weights]
        selected_source = choice(sources, p=normalized_weights)
        sample = selected_source.sample(duration, filters)

        return sample

    def get_rejected_segments(self) -> List[VideoSegment]:
        rejected_segments = []
        for source in self:
            rejected_segments.extend(source.get_rejected_segments())
        return rejected_segments
