from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = (ROOT / "src" / "usage_telemetry_client.js").read_text(
    encoding="utf-8"
)
REPORT_CLIENT = (ROOT / "src" / "error_report_client.js").read_text(
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
        self.assertIn("removePersistentValue(INSTALLATION_COOKIE);", CLIENT)
        self.assertIn("removePersistentValue(CURRENT_COUNTERS_COOKIE);", CLIENT)
        self.assertIn("removePersistentValue(PREVIOUS_COUNTERS_COOKIE);", CLIENT)
        self.assertIn("removeCookie(name);", CLIENT)
        self.assertIn("removeLocalStorage(name);", CLIENT)

    def test_public_source_uses_cookie_and_local_storage_persistence(self) -> None:
        self.assertIn("document.cookie", CLIENT)
        self.assertIn("globalThis.localStorage.getItem(name)", CLIENT)
        self.assertIn("globalThis.localStorage.setItem(name, value)", CLIENT)
        self.assertIn("writePersistentValue", CLIENT)
        self.assertIn("readPersistentValue", CLIENT)
        self.assertIn('var CONSENT_COOKIE = "jlpt_max_deck_usage_consent_v1";', CLIENT)
        self.assertIn('var CURRENT_COUNTERS_COOKIE = "jlpt_max_deck_usage_current_v1";', CLIENT)
        self.assertIn('var PREVIOUS_COUNTERS_COOKIE = "jlpt_max_deck_usage_previous_v1";', CLIENT)
        self.assertIn("retainCurrentAndPreviousDay(counters, today);", CLIENT)
        self.assertNotIn("window.name", CLIENT)


class ErrorReportClientSourceTests(unittest.TestCase):
    def test_public_source_exposes_only_the_explicit_report_contract(self) -> None:
        for field in (
            "category: category",
            "description: text",
            "content_ref: contentRef",
            "platform: detectPlatform()",
        ):
            self.assertIn(field, REPORT_CLIENT)
        self.assertIn('credentials: "omit"', REPORT_CLIENT)
        self.assertIn('referrerPolicy: "no-referrer"', REPORT_CLIENT)

    def test_report_source_excludes_usage_identity_and_review_data(self) -> None:
        self.assertNotIn("installation_id", REPORT_CLIENT)
        self.assertNotIn("review_history", REPORT_CLIENT)
        self.assertNotIn("answer_count", REPORT_CLIENT)
        self.assertNotIn("request.cf", REPORT_CLIENT)
        self.assertNotIn("navigator.userAgent", REPORT_CLIENT)


if __name__ == "__main__":
    unittest.main()
