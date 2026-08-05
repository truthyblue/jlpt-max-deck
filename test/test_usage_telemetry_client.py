from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = (ROOT / "src" / "usage_telemetry_client.js").read_text(
    encoding="utf-8"
)


class UsageTelemetryClientSourceTests(unittest.TestCase):
    def test_public_source_exposes_the_controlled_payload_contract(self) -> None:
        self.assertIn("installation_id: installationId", CLIENT)
        self.assertIn("platform: context.platform", CLIENT)
        self.assertIn("deck_version: parts[0]", CLIENT)
        self.assertIn("answer_count: day.buckets[key]", CLIENT)
        self.assertIn('credentials: "omit"', CLIENT)
        self.assertIn('referrerPolicy: "no-referrer"', CLIENT)

    def test_public_source_excludes_raw_identity_and_review_fields(self) -> None:
        self.assertNotIn("navigator.userAgent", CLIENT)
        self.assertNotIn("card_id", CLIENT)
        self.assertNotIn("note_id", CLIENT)
        self.assertNotIn("review_history", CLIENT)
        self.assertNotIn("request.cf", CLIENT)
        self.assertNotIn("hmac", CLIENT.lower())

    def test_opt_out_clears_installation_and_unsent_counters(self) -> None:
        self.assertIn("clearTransmittedUsageState();", CLIENT)
        self.assertIn("removeStorage(INSTALLATION_KEY);", CLIENT)
        self.assertIn("removeStorage(COUNTERS_KEY);", CLIENT)


if __name__ == "__main__":
    unittest.main()
