from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from public_apkg_builder import _valid_audio  # noqa: E402
from public_media import MediaCodecError, inspect_cbr_mp3  # noqa: E402


def _mp3_frame(*, bitrate_index: int = 9, padding: int = 0) -> bytes:
    header = (
        (0x7FF << 21)
        | (0b11 << 19)
        | (0b01 << 17)
        | (1 << 16)
        | (bitrate_index << 12)
        | (padding << 9)
        | (0b11 << 6)
    )
    bitrate_kbps = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160)[
        bitrate_index
    ]
    frame_bytes = (144 * bitrate_kbps * 1000) // 44100 + padding
    return header.to_bytes(4, "big") + bytes(frame_bytes - 4)


class PublicMediaTest(unittest.TestCase):
    def test_inspects_tag_free_mono_128k_cbr_mp3(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.mp3"
            path.write_bytes(_mp3_frame() + _mp3_frame(padding=1))

            info = inspect_cbr_mp3(path)

        self.assertEqual(info.bitrate_kbps, 128)
        self.assertEqual(info.channels, 1)
        self.assertEqual(info.frame_count, 2)
        self.assertEqual(info.sample_count, 2304)
        self.assertEqual(info.sample_rate, 44100)

    def test_rejects_trailing_or_mixed_format_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trailing = root / "trailing.mp3"
            trailing.write_bytes(_mp3_frame() + b"x")
            with self.assertRaisesRegex(MediaCodecError, "partial data"):
                inspect_cbr_mp3(trailing)

            mixed = root / "mixed.mp3"
            mixed.write_bytes(_mp3_frame() + _mp3_frame(bitrate_index=10))
            with self.assertRaisesRegex(MediaCodecError, "changes between frames"):
                inspect_cbr_mp3(mixed)

    def test_closed_deck_accepts_only_the_declared_public_mp3_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.mp3"
            path.write_bytes(_mp3_frame() + _mp3_frame(padding=1))
            inventory = {
                "bitrate_kbps": 128,
                "channels": 1,
                "codec": "mp3",
                "frame_count": 2,
                "sample_rate": 44100,
                "sample_count": 2304,
                "source_frame_count": 1000,
            }
            self.assertTrue(_valid_audio(path, inventory))
            inventory["bitrate_kbps"] = 64
            self.assertFalse(_valid_audio(path, inventory))
