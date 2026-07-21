"""Dependency-free validators for public deck audio."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class MediaCodecError(ValueError):
    """Raised when an audio file does not match the distribution contract."""


MP3_MAX_ENCODER_PADDING_SAMPLES = 3 * 1152


@dataclass(frozen=True)
class Mp3Info:
    bitrate_kbps: int
    channels: int
    frame_count: int
    sample_count: int
    sample_rate: int


_MPEG1_LAYER3_BITRATES = (
    0,
    32,
    40,
    48,
    56,
    64,
    80,
    96,
    112,
    128,
    160,
    192,
    224,
    256,
    320,
    0,
)
_MPEG1_SAMPLE_RATES = (44100, 48000, 32000)


def inspect_cbr_mp3(path: Path) -> Mp3Info:
    """Read a tag-free MPEG-1 Layer III stream and return its fixed format.

    The public bundle encoder deliberately emits one narrow contract: raw MP3
    frames, constant bitrate, and no ID3/APEv2 trailer.  Keeping the reader
    equally narrow makes Windows builds independent of ffmpeg, ffprobe, or a
    platform media API.
    """

    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise MediaCodecError(f"cannot read MP3: {path}: {exc}") from exc
    if len(payload) < 4:
        raise MediaCodecError(f"MP3 has no complete frame: {path}")

    offset = 0
    frame_count = 0
    bitrate_kbps: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    while offset < len(payload):
        if len(payload) - offset < 4:
            raise MediaCodecError(f"MP3 has trailing partial data: {path}")
        header = int.from_bytes(payload[offset : offset + 4], "big")
        if header >> 21 != 0x7FF:
            raise MediaCodecError(f"MP3 frame sync changed at byte {offset}: {path}")
        version_id = (header >> 19) & 0b11
        layer_id = (header >> 17) & 0b11
        bitrate_index = (header >> 12) & 0b1111
        sample_rate_index = (header >> 10) & 0b11
        padding = (header >> 9) & 0b1
        channel_mode = (header >> 6) & 0b11
        if version_id != 0b11 or layer_id != 0b01:
            raise MediaCodecError(f"MP3 is not MPEG-1 Layer III: {path}")
        if sample_rate_index >= len(_MPEG1_SAMPLE_RATES):
            raise MediaCodecError(f"MP3 sample-rate index is reserved: {path}")
        frame_bitrate = _MPEG1_LAYER3_BITRATES[bitrate_index]
        if frame_bitrate == 0:
            raise MediaCodecError(f"MP3 bitrate index is not fixed: {path}")
        frame_sample_rate = _MPEG1_SAMPLE_RATES[sample_rate_index]
        frame_channels = 1 if channel_mode == 0b11 else 2
        if bitrate_kbps is None:
            bitrate_kbps = frame_bitrate
            sample_rate = frame_sample_rate
            channels = frame_channels
        elif (
            frame_bitrate != bitrate_kbps
            or frame_sample_rate != sample_rate
            or frame_channels != channels
        ):
            raise MediaCodecError(f"MP3 stream format changes between frames: {path}")
        frame_bytes = (144 * frame_bitrate * 1000) // frame_sample_rate + padding
        if offset + frame_bytes > len(payload):
            raise MediaCodecError(f"MP3 frame is truncated at byte {offset}: {path}")
        offset += frame_bytes
        frame_count += 1

    assert bitrate_kbps is not None
    assert sample_rate is not None
    assert channels is not None
    return Mp3Info(
        bitrate_kbps=bitrate_kbps,
        channels=channels,
        frame_count=frame_count,
        sample_count=frame_count * 1152,
        sample_rate=sample_rate,
    )
