import pytest

from mugen import MusicVideo
from tests.integration.video.segments.test_VideoSegment import shinsekai_segment
from tests.integration.video.segments.test_ImageSegment import tatami_segment
from tests.unit.video.segments.test_ColorSegment import orange_segment


@pytest.fixture
def basic_music_video(shinsekai_segment, tatami_segment, orange_segment) -> MusicVideo:
    return MusicVideo([shinsekai_segment, tatami_segment, orange_segment])


def test_save_load(basic_music_video):
    music_video_file = basic_music_video.save()
    loaded_music_video = MusicVideo.load(music_video_file)

    assert len(loaded_music_video.segments) == len(basic_music_video.segments)
