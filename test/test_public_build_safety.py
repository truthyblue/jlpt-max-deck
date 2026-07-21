from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from typing import Any, cast
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import public_apkg_builder as apkg_builder  # noqa: E402
from public_hashing import sha256_file, sha256_json  # noqa: E402
from build_public_deck import (  # noqa: E402
    BUNDLE_MANIFEST,
    MATERIALIZATION_REPORT,
    PUBLIC_BUILD_POLICY_VERSION,
    PUBLIC_BUILD_REPORT,
    SOURCE_PROOF,
    PublicBuildError,
    _default_output_root,
    _publish_release,
    _validated_existing_public_output,
)
from public_materialization import (  # noqa: E402
    PUBLIC_MATERIALIZATION_POLICY_VERSION,
)
from public_source_proof import SOURCE_PROOF_POLICY_VERSION  # noqa: E402
from public_release import (  # noqa: E402
    RELEASE_MANIFEST,
    RELEASE_NOTES,
    UPDATE_REPORT_JSON,
    UPDATE_REPORT_TEXT,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _closed_report(policy_version: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "policy_version": policy_version,
        "schema_version": 1,
        "status": "passed",
        "unresolved": 0,
    }
    return {**payload, "payload_hash": sha256_json(payload)}


def _lexical_kanji_reading_fixture() -> dict[str, Any]:
    source_reference_id = "hackers-n1-wordbook:p0017:c1-r1"
    return {
        "answer_audio_filename": "fixture-answer.wav",
        "answer_jp": "しゅつば",
        "answer_ko": "「出馬」의 읽기는 「しゅつば」이다.",
        "answer_word_jp": "出馬",
        "answer_word_reading": "しゅつば",
        "answer_word_jp_ruby": (
            "<ruby><rb>出馬</rb><rt>しゅつば</rt></ruby>"
        ),
        "card_templates": ["어휘문제"],
        "choice_notes_ko": [
            "「しゅつば」는 「出馬」를 올바르게 읽은 형태이다.",
            "「しゅっば」는 「つ」를 촉음으로 잘못 읽은 형태이다.",
            "「でうま」는 두 한자의 읽기를 훈독으로 잘못 조합한 형태이다.",
            "「しゅつま」는 「馬」의 읽기에서 탁음을 빠뜨린 형태이다.",
        ],
        "choices": ["しゅつば", "しゅっば", "でうま", "しゅつま"],
        "correct_index": 0,
        "covered_targets": [
            {
                "candidate_id": source_reference_id,
                "canonical_forms": [
                    {"reading": "しゅつば", "surface": "出馬"}
                ],
                "canonical_meaning": "출마",
                "jlpt_level": "N1",
                "meaning": "출마",
                "page": 17,
                "question_type": "kanji_reading",
                "reading": "しゅつば",
                "source_id": "hackers-n1-wordbook",
                "surface": "出馬",
            }
        ],
        "deck_key": "practice:kanji_reading:N1",
        "explanation_ko": (
            "문맥에서 선거에 후보로 나선다는 뜻의 「出馬」는 "
            "「しゅつば」로 읽는다."
        ),
        "jlpt_level": "N1",
        "note_id": "lfq:kanji_reading:fixture",
        "note_kind": "practice_question",
        "prompt_instruction": "밑줄 친 단어의 올바른 읽기를 고르세요.",
        "prompt_jp": "来年の選挙に【出馬】する予定だ。",
        "prompt_jp_ruby": (
            "<ruby><rb>来年</rb><rt>らいねん</rt></ruby>の"
            "<ruby><rb>選挙</rb><rt>せんきょ</rt></ruby>に"
            "【<ruby><rb>出馬</rb><rt>しゅつば</rt></ruby>】する"
            "<ruby><rb>予定</rb><rt>よてい</rt></ruby>だ。"
        ),
        "prompt_ko": "내년 선거에 출마할 예정이다.",
        "prompt_ko_ruby": "내년 선거에 출마할 예정이다.",
        "question_id": "lfq:kanji_reading:fixture",
        "question_type": "kanji_reading",
        "sort_key": "lfq:kanji_reading:fixture",
        "source_id": "hackers-n1-wordbook",
        "source_page": 17,
        "source_reference_id": source_reference_id,
        "source_reference_ids": [source_reference_id],
        "source_references": [
            {
                "candidate_id": source_reference_id,
                "page": 17,
                "source_id": "hackers-n1-wordbook",
            }
        ],
    }


def _write_managed_public_output(root: Path, *, package_payload: bytes) -> None:
    root.mkdir(parents=True)
    package = "fixture.apkg"
    (root / package).write_bytes(package_payload)
    logical = {"fixture": package_payload.hex()}
    _write_json(root / apkg_builder.LOGICAL_MANIFEST, logical)
    build_report = {
        "logical_apkg_hash": sha256_json(logical),
        "package": package,
        "package_bytes": len(package_payload),
        "package_sha256": sha256_file(root / package),
        "policy_version": apkg_builder.APKG_POLICY_VERSION,
        "rendered_sample_files": 0,
        "schema_version": 1,
        "status": "passed",
        "unresolved": 0,
    }
    _write_json(root / apkg_builder.BUILD_REPORT, build_report)
    _write_json(
        root / apkg_builder.RENDERED_SAMPLE_INDEX,
        {"samples": [], "schema_version": 1},
    )
    _write_json(root / RELEASE_MANIFEST, {"fixture": True})
    (root / RELEASE_NOTES).write_text("", encoding="utf-8")
    _write_json(root / UPDATE_REPORT_JSON, {"fixture": True})
    (root / UPDATE_REPORT_TEXT).write_text("fixture\n", encoding="utf-8")

    artifact_names = {
        package,
        apkg_builder.BUILD_REPORT,
        apkg_builder.LOGICAL_MANIFEST,
        apkg_builder.RENDERED_SAMPLE_INDEX,
        RELEASE_MANIFEST,
        RELEASE_NOTES,
        UPDATE_REPORT_JSON,
        UPDATE_REPORT_TEXT,
    }
    artifacts = {
        name: sha256_file(root.joinpath(*PurePosixPath(name).parts))
        for name in sorted(artifact_names)
    }
    stage = {
        "output_artifacts": artifacts,
        "output_bundle_hash": sha256_json(artifacts),
        "policy_version": apkg_builder.APKG_POLICY_VERSION,
        "schema_version": 1,
        "stage_id": apkg_builder.STAGE_ID,
        "status": "passed",
        "unresolved": 0,
    }
    _write_json(root / apkg_builder.STAGE_MANIFEST, stage)

    source_proof = _closed_report(SOURCE_PROOF_POLICY_VERSION)
    materialization = _closed_report(PUBLIC_MATERIALIZATION_POLICY_VERSION)
    _write_json(root / SOURCE_PROOF, source_proof)
    _write_json(root / MATERIALIZATION_REPORT, materialization)
    public_payload = {
        "apkg": package,
        "apkg_sha256": artifacts[package],
        "bundle_manifest_sha256": "a" * 64,
        "expected_logical_apkg_hash": sha256_json(logical),
        "materialization_payload_hash": materialization["payload_hash"],
        "policy_version": PUBLIC_BUILD_POLICY_VERSION,
        "schema_version": 1,
        "source_proof_payload_hash": source_proof["payload_hash"],
        "status": "passed",
        "unresolved": 0,
    }
    _write_json(
        root / PUBLIC_BUILD_REPORT,
        {**public_payload, "payload_hash": sha256_json(public_payload)},
    )


class _FakeNote(dict[str, str]):
    guid = "fixture-guid"


class _FakeCard:
    nid = 1
    ord = 0

    def note_type(self) -> dict[str, object]:
        return {
            "css": ".card { color: black; }",
            "name": "Fixture note type",
            "tmpls": [{"name": "Fixture template"}],
        }

    def question(self) -> str:
        return "<main>question content</main>"

    def answer(self) -> str:
        return (
            "<main>answer content"
            '<audio class="click-audio-player"></audio>'
            '<section class="reference-group"></section>'
            '<section class="reference-group"></section>'
            '<section class="reference-group"></section>'
            "</main>"
        )


class _FakeCollection:
    note = _FakeNote(TableKind="calendar_grid")

    def get_note(self, unused_note_id: int) -> _FakeNote:
        return self.note


class RenderedSampleFilenameTest(unittest.TestCase):
    def test_keeps_safe_names_and_disambiguates_case_insensitively(self) -> None:
        self.assertEqual(
            apkg_builder._portable_rendered_sample_stem("vocabulary-N1"),
            "vocabulary-N1",
        )
        stems = apkg_builder._rendered_sample_filename_stems(
            ("Sample", "sample")
        )
        self.assertEqual(len({stem.casefold() for stem in stems.values()}), 2)

    def test_unsafe_label_uses_portable_path_but_stays_in_index(self) -> None:
        label = "reference-table-hackers-n5-wordbook:p0020:calendar_grid"
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            with mock.patch.object(
                apkg_builder,
                "_rendered_sample_candidates",
                return_value={label: _FakeCard()},
            ):
                records = apkg_builder.write_rendered_samples(
                    cast(Any, _FakeCollection()),
                    output_root,
                )

            self.assertEqual({record["label"] for record in records}, {label})
            for record in records:
                relative = str(record["path"])
                filename = PurePosixPath(relative).name
                self.assertNotRegex(filename, r"[<>:\"/\\|?*]")
                self.assertLessEqual(
                    len(filename),
                    apkg_builder.RENDERED_SAMPLE_STEM_MAX_LENGTH
                    + len("-question.html"),
                )
                self.assertTrue((output_root / relative).is_file())
            index = json.loads(
                (output_root / apkg_builder.RENDERED_SAMPLE_INDEX).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual({record["label"] for record in index["samples"]}, {label})
            self.assertIn(
                "question content", (output_root / records[0]["path"]).read_text()
            )
            self.assertIn(
                "answer content", (output_root / records[1]["path"]).read_text()
            )


class DefaultOutputRootTest(unittest.TestCase):
    def test_maintainer_checkout_keeps_default_output_under_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()

            self.assertEqual(
                _default_output_root(root),
                root / "build" / "public-release",
            )

    def test_extracted_bundle_writes_default_output_beside_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "public-bundle"
            root.mkdir()
            (root / BUNDLE_MANIFEST).write_text("{}\n", encoding="utf-8")

            self.assertEqual(
                _default_output_root(root),
                root.parent / "public-release",
            )

    def test_powershell_resolves_relative_output_before_changing_directory(
        self,
    ) -> None:
        script = (ROOT / "scripts" / "build-public.ps1").read_text(encoding="utf-8")

        self.assertLess(
            script.index("[System.IO.Path]::GetFullPath($OutputRoot)"),
            script.index("Push-Location $RepoRoot"),
        )


class PublicRuntimeClosureTest(unittest.TestCase):
    def test_lexical_explanation_does_not_repeat_answer_summary(self) -> None:
        fixture = _lexical_kanji_reading_fixture()
        values = apkg_builder._practice_question_field_values(fixture)

        for field in ("ExplanationHTML", "ExplanationRubyHTML"):
            with self.subTest(field=field):
                self.assertIn(fixture["explanation_ko"], values[field])
                self.assertNotIn(fixture["answer_ko"], values[field])
                self.assertNotIn("answer-summary", values[field])


class ExistingPublicOutputSafetyTest(unittest.TestCase):
    def test_accepts_exact_managed_inventory_and_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory) / "public-release"
            _write_managed_public_output(output_root, package_payload=b"old deck")

            report = _validated_existing_public_output(output_root)

            self.assertEqual(report["status"], "passed")

    def test_changed_managed_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory) / "public-release"
            _write_managed_public_output(output_root, package_payload=b"old deck")
            (output_root / RELEASE_NOTES).write_text("changed\n", encoding="utf-8")

            with self.assertRaisesRegex(PublicBuildError, "unmanaged output root"):
                _validated_existing_public_output(output_root)

    def test_publish_refuses_extra_file_without_deleting_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_root = root / "public-release"
            release_root = root / "staged-release"
            _write_managed_public_output(output_root, package_payload=b"old deck")
            _write_managed_public_output(release_root, package_payload=b"new deck")
            personal_file = output_root / "important-personal-file.txt"
            personal_file.write_text("keep me", encoding="utf-8")

            with self.assertRaisesRegex(PublicBuildError, "unmanaged output root"):
                _publish_release(release_root, output_root)

            self.assertEqual(personal_file.read_text(encoding="utf-8"), "keep me")
            self.assertTrue(release_root.is_dir())
            self.assertFalse((root / ".public-release.backup").exists())


if __name__ == "__main__":
    unittest.main()
