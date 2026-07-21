from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_public_tree", ROOT / "scripts" / "verify-public-tree.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load public tree verifier")
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class PublicRepositoryVerifierTest(unittest.TestCase):
    def test_ci_uses_repository_line_endings_and_event_scoped_verifier(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Restore canonical metadata line endings", workflow)
        sync = "uv sync --locked --python 3.13"
        contributor_verify = "--allow-release-pin-drift"
        strict_verify = "Verify strict publication boundary"
        tests = "uv run --locked python test/run_tests.py fast --verbose"
        self.assertIn("if: github.event_name == 'pull_request'", workflow)
        self.assertIn("if: github.event_name != 'pull_request'", workflow)
        self.assertLess(workflow.index(sync), workflow.index(contributor_verify))
        self.assertLess(
            workflow.index(contributor_verify), workflow.index(strict_verify)
        )
        self.assertLess(workflow.index(strict_verify), workflow.index(tests))

        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        for rule in (
            ".gitattributes text eol=lf",
            "*.css text eol=lf",
            "*.js text eol=lf",
            "*.py text eol=lf",
            "*.yml text eol=lf",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, attributes)

    def test_pages_workflow_separates_build_and_deploy_permissions(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(
            encoding="utf-8"
        )
        pre_jobs, separator, jobs = workflow.partition("\njobs:\n")
        self.assertTrue(separator)
        build_job, separator, deploy_job = jobs.partition("\n  deploy:\n")
        self.assertTrue(separator)

        self.assertIn("permissions: {}", pre_jobs)
        self.assertIn("contents: read", build_job)
        self.assertIn("pages: read", build_job)
        self.assertNotIn("pages: write", build_job)
        self.assertNotIn("id-token: write", build_job)
        self.assertIn("needs: build", deploy_job)
        self.assertIn("if: github.ref == 'refs/heads/main'", deploy_job)
        self.assertIn("pages: write", deploy_job)
        self.assertIn("id-token: write", deploy_job)

        action_references = re.findall(r"^\s*uses:\s*(\S+)", workflow, re.MULTILINE)
        self.assertTrue(action_references)
        self.assertTrue(
            all(
                re.fullmatch(r"[^@]+@[0-9a-f]{40}", reference)
                for reference in action_references
            )
        )

    def test_runtime_allowlist_matches_executable_contract(self) -> None:
        entries = VERIFY.verify_runtime_allowlist(ROOT)
        self.assertEqual(len(entries), 27)
        self.assertIn("src/public_apkg_builder.py", entries)
        self.assertNotIn("src/build_deck.py", entries)

    def test_filesystem_inventory_ignores_git_internals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git" / "objects").mkdir(parents=True)
            (root / ".git" / "objects" / "private").write_text(
                "ignored", encoding="utf-8"
            )
            (root / "LICENSE").write_text("license", encoding="utf-8")
            self.assertEqual(VERIFY.filesystem_inventory(root), ("LICENSE",))

    def test_filesystem_inventory_ignores_only_explicit_local_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".venv" / "bin").mkdir(parents=True)
            (root / ".venv" / "bin" / "python").write_bytes(b"local")
            (root / "src" / "__pycache__").mkdir(parents=True)
            (root / "src" / "__pycache__" / "module.pyc").write_bytes(b"cache")
            (root / ".DS_Store").write_bytes(b"local")
            (root / "LICENSE").write_text("license", encoding="utf-8")
            self.assertEqual(VERIFY.filesystem_inventory(root), ("LICENSE",))

            (root / "secret.pdf").write_bytes(b"private")
            with self.assertRaisesRegex(VERIFY.PublicTreeError, "secret.pdf"):
                VERIFY.verify_public_inventories(root, ("LICENSE",))

    def test_filesystem_inventory_fails_closed_on_walk_errors(self) -> None:
        def blocked_walk(*unused_args: object, **kwargs: object) -> tuple[()]:
            onerror = kwargs.get("onerror")
            if not callable(onerror):
                raise AssertionError("filesystem walk must install an error handler")
            onerror(PermissionError("blocked"))
            return ()

        with patch.object(VERIFY.os, "walk", side_effect=blocked_walk):
            with self.assertRaisesRegex(
                VERIFY.PublicTreeError, "cannot inspect public tree: blocked"
            ):
                VERIFY.filesystem_inventory(Path("fixture"))

    def test_exact_inventory_reports_missing_and_unexpected_files(self) -> None:
        with self.assertRaisesRegex(
            VERIFY.PublicTreeError, "missing: README.md; unexpected: secret.txt"
        ):
            VERIFY.verify_exact_inventory(
                ("LICENSE", "README.md"),
                ("LICENSE", "secret.txt"),
                source="fixture",
            )

    def test_git_inventory_must_exactly_match_the_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LICENSE").write_text("license", encoding="utf-8")
            with patch.object(VERIFY, "git_inventory", return_value=("LICENSE",)):
                files, source = VERIFY.verify_public_inventories(root, ("LICENSE",))
            self.assertEqual(files, ("LICENSE",))
            self.assertEqual(source, "git index + filesystem")

            with patch.object(VERIFY, "git_inventory", return_value=()):
                with self.assertRaisesRegex(
                    VERIFY.PublicTreeError,
                    r"public tree differs from allowlist \(git index\); missing: LICENSE",
                ):
                    VERIFY.verify_public_inventories(root, ("LICENSE",))

            with patch.object(
                VERIFY,
                "git_inventory",
                return_value=("LICENSE", "tracked-secret.txt"),
            ):
                with self.assertRaisesRegex(
                    VERIFY.PublicTreeError,
                    r"public tree differs from allowlist \(git index\); "
                    r"unexpected: tracked-secret.txt",
                ):
                    VERIFY.verify_public_inventories(root, ("LICENSE",))

    def test_path_policy_rejects_private_directories_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private_path = "data/records.json"
            (root / "data").mkdir()
            (root / private_path).write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(VERIFY.PublicTreeError, "forbidden directory"):
                VERIFY.verify_paths(root, (private_path,))

            artifact = "release" + ".apkg"
            (root / artifact).write_bytes(b"fixture")
            with self.assertRaisesRegex(VERIFY.PublicTreeError, "forbidden artifact"):
                VERIFY.verify_paths(root, (artifact,))

    def test_path_policy_allows_only_the_fixed_public_audio_demos(self) -> None:
        self.assertEqual(
            VERIFY.PUBLIC_AUDIO_DEMO_PATHS,
            frozenset(
                {
                    "site/assets/demo-dasu-example-2.mp3",
                    "site/assets/demo-dasu-example-3.mp3",
                    "site/assets/demo-dasu-example.mp3",
                    "site/assets/demo-dasu-word.mp3",
                }
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in VERIFY.PUBLIC_AUDIO_DEMO_PATHS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixed listening demo")

            VERIFY.verify_paths(root, sorted(VERIFY.PUBLIC_AUDIO_DEMO_PATHS))

            for relative in (
                "site/assets/demo-other.mp3",
                "demo-dasu-word.mp3",
                "site/assets/demo-dasu-word.MP3",
            ):
                with self.subTest(relative=relative):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"not an approved demo")
                    with self.assertRaisesRegex(
                        VERIFY.PublicTreeError, "forbidden artifact"
                    ):
                        VERIFY.verify_paths(root, (relative,))

    def test_directory_tree_rejects_an_empty_forbidden_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".codex").mkdir()
            with self.assertRaisesRegex(VERIFY.PublicTreeError, "forbidden directory"):
                VERIFY.verify_directory_tree(root)

    def test_private_token_scan_includes_public_prose_and_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "src").mkdir()
            token = "data/sources/" + "personal"
            (root / "docs" / "boundary.md").write_text(token, encoding="utf-8")
            with self.assertRaisesRegex(
                VERIFY.PublicTreeError, "non-public identifier"
            ):
                VERIFY.scan_private_tokens(root, ("docs/boundary.md",))

            (root / "src" / "leak.py").write_text(token, encoding="utf-8")
            with self.assertRaisesRegex(
                VERIFY.PublicTreeError, "non-public identifier"
            ):
                VERIFY.scan_private_tokens(root, ("src/leak.py",))

    def test_private_token_scan_includes_root_prose_and_metadata(self) -> None:
        root_files = (
            ".gitattributes",
            ".gitignore",
            "CONTRIBUTING.md",
            "LICENSE",
            "NOTICE",
            "README.md",
            "SECURITY.md",
            "pyproject.toml",
            "uv.lock",
        )
        self.assertTrue(all(VERIFY._scan_candidate(name) for name in root_files))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token = "data/sources/" + "personal"
            for name in root_files:
                with self.subTest(name=name):
                    path = root / name
                    path.write_text(token, encoding="utf-8")
                    with self.assertRaisesRegex(
                        VERIFY.PublicTreeError, "non-public identifier"
                    ):
                        VERIFY.scan_private_tokens(root, (name,))

    def test_private_token_scan_includes_textual_xml_fixtures(self) -> None:
        relative = "test/fixtures/source.xml"
        self.assertTrue(VERIFY._scan_candidate(relative))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / relative
            path.parent.mkdir(parents=True)
            path.write_text(
                "<path>/" + "Users/example/publisher.pdf</path>",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VERIFY.PublicTreeError, "absolute user path"):
                VERIFY.scan_private_tokens(root, (relative,))

    def test_documented_public_path_example_is_allowed_but_private_path_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "site").mkdir()
            path = root / "site" / "index.html"
            path.write_text(
                r"C:" + r"\Users\me\Documents\jlpt-pdfs", encoding="utf-8"
            )
            VERIFY.scan_private_tokens(root, ("site/index.html",))

            path.write_text(
                r"C:" + r"\Users\alice\Documents\publisher.pdf", encoding="utf-8"
            )
            with self.assertRaisesRegex(VERIFY.PublicTreeError, "absolute user path"):
                VERIFY.scan_private_tokens(root, ("site/index.html",))

    def test_absolute_user_path_is_rejected_in_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            value = "/" + "Users/example/book.pdf"
            (root / "src" / "leak.py").write_text(value, encoding="utf-8")
            with self.assertRaisesRegex(VERIFY.PublicTreeError, "absolute user path"):
                VERIFY.scan_private_tokens(root, ("src/leak.py",))

    def test_release_pin_binds_public_builder_source_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            digest = "a" * 64
            payload = {
                "archive_bytes": 1,
                "archive_sha256": digest,
                "bundle_manifest_sha256": digest,
                "policy_version": "public-release-pin-v1",
                "public_builder_source_hash": digest,
                "schema_version": 1,
                "status": "passed",
                "unresolved": 0,
            }
            (root / "config" / "public-release.json").write_text(
                json.dumps({**payload, "payload_hash": VERIFY._sha256_json(payload)}),
                encoding="utf-8",
            )
            self.assertEqual(
                VERIFY.verify_release_pin(
                    root, compute_source_hash=lambda unused_root: digest
                ),
                digest,
            )
            with self.assertRaisesRegex(
                VERIFY.PublicTreeError, "differs from config/public-release.json"
            ):
                VERIFY.verify_release_pin(
                    root, compute_source_hash=lambda unused_root: "b" * 64
                )

            self.assertEqual(
                VERIFY.verify_release_pin(
                    root,
                    compute_source_hash=lambda unused_root: "b" * 64,
                    allow_source_hash_drift=True,
                ),
                "b" * 64,
            )

    def test_release_pin_drift_mode_still_rejects_an_invalid_pin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            digest = "a" * 64
            invalid_pin = {
                "archive_bytes": 1,
                "archive_sha256": digest,
                "bundle_manifest_sha256": digest,
                "payload_hash": "b" * 64,
                "policy_version": "public-release-pin-v1",
                "public_builder_source_hash": digest,
                "schema_version": 1,
                "status": "passed",
                "unresolved": 0,
            }
            (root / "config" / "public-release.json").write_text(
                json.dumps(invalid_pin), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                VERIFY.PublicTreeError, "release pin is not passed and closed"
            ):
                VERIFY.verify_release_pin(
                    root,
                    compute_source_hash=lambda unused_root: "b" * 64,
                    allow_source_hash_drift=True,
                )

    def test_release_pin_drift_cli_is_opt_in(self) -> None:
        with patch.object(VERIFY.sys, "argv", ["verify-public-tree.py"]):
            self.assertFalse(VERIFY.parse_args().allow_release_pin_drift)
        with patch.object(
            VERIFY.sys,
            "argv",
            ["verify-public-tree.py", "--allow-release-pin-drift"],
        ):
            self.assertTrue(VERIFY.parse_args().allow_release_pin_drift)

    def test_main_forwards_the_contributor_drift_choice(self) -> None:
        args = type(
            "Args",
            (),
            {"root": ROOT, "allow_release_pin_drift": True},
        )()
        with (
            patch.object(VERIFY, "parse_args", return_value=args),
            patch.object(
                VERIFY,
                "verify",
                return_value=(98, "git index + filesystem", "a" * 64),
            ) as verify,
            patch("builtins.print"),
        ):
            self.assertEqual(VERIFY.main(), 0)
        verify.assert_called_once_with(ROOT, allow_release_pin_drift=True)


if __name__ == "__main__":
    unittest.main()
