```
                                                  _           _ 
                                                 | |         (_)
  _ __ ___  _   _  __ _  ___ _ __   __      _____| |__  _   _ _ 
 | '_ ` _ \| | | |/ _` |/ _ \ '_ \  \ \ /\ / / _ \ '_ \| | | | |
 | | | | | | |_| | (_| |  __/ | | |  \ V  V /  __/ |_) | |_| | |
 |_| |_| |_|\__,_|\__, |\___|_| |_|   \_/\_/ \___|_.__/ \__,_|_|
                   __/ |                                        
                  |___/                                         
```

[![license](https://img.shields.io/github/license/justoboy/mugen-webui?color=blue)](https://github.com/justoboy/mugen-webui/blob/master/LICENSE)

A fork of [mugen](https://github.com/scherroman/mugen) that provides a web based user interface using [Gradio](https://www.gradio.app).

Use it to brainstorm AMVs, montages, and more! [Check it out](https://youtu.be/ZlTR6XULe5M).

Built with [moviepy](https://github.com/Zulko/moviepy) programmatic video editing and [librosa](https://github.com/librosa/librosa) audio analysis.

## Strategy

1. Provide an audio file and a set of video files

2. Perform rhythm analysis to identify beat locations

3. Generate a set of random video segments synced to the beat

4. Discard segments with scene changes, detectable text (e.g. credits), or low contrast (i.e. solid colors, very dark scenes)

5. Combine the segments in order, overlay the audio, and output the resulting music video

## Installation

**1. Install [Python 3.12](https://www.python.org/downloads/)**


**2. Download this repository**

```
git clone https://github.com/justoboy/mugen-webui
```

**3. Run the [setup.bat](https://github.com/justoboy/mugen-webui/blob/master/setup.bat) file**

## Features

**Gradio User Interface**

Creates a more user-friendly experience.

**Generate Preview**

Generates a preview video switching between a black and a white screen with an audible tone at each beat location.

**Video Filters**

Options for which video filters to use when choosing valid video clips.

**Pre-process Clips**

Force the pre-processing of video filters on selected video clips, throwing an error if there aren't enough valid clips to avoid the infinite process bug.


**Generate**

Generates a music video with the selected audio file, video clips, and generation options.

## Planned Features


**Use Beat Groups**

Option to allow groups of beats with different intervals, allowing for more dynamic control of how often scenes switch at different points of the video.

## Notes

### Subtitles

The videos generated by `create` and `preview` include a subtitle track which display segment types, numbers, and locations.

### Text detection

Text detection uses the [Tesseract](https://github.com/tesseract-ocr/tesseract) optical character recognition engine which is optional to install. It has been trained mainly on documents with standard type fonts. Credit sequences with nonstandard or skewed fonts will likely not be detected. It is also possible for Tesseract to occasionally falsely detect text in some images.

## Troubleshooting

### Progress is stuck

The most common reason progress gets stuck is that mugen is trying but can't find any more segments from your video source(s) that pass the default video filters. The `not_is_repeat` and `not_has_cut` filters in particular could be causing this if your video source is especially short and/or with little to no time between scene changes. The first one throws out segments that have already been used, and the latter throws out segments where there are scene changes detected. Try using one or more videos that are longer than your music.
