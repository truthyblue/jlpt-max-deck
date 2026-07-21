# Contributing

Thanks for helping make the public builder safer and easier to reproduce.

## Start with the publication boundary

This repository contains only the public runtime, configuration, portable tests
and wrappers, documentation, and project site. Do not commit books, extracted
book content, generated decks, release archives, local databases, credentials,
machine-specific paths, or authoring and review artifacts outside the declared
public release contract.

Every tracked file must appear in `config/public-source-files.txt`. Run this
before opening a pull request:

```console
python scripts/verify-public-tree.py
uv sync --locked --python 3.13
uv run --locked python test/run_tests.py fast
```

`config/public-runtime-files.txt` is the smaller, exact file set copied into
release bundles. It must match `PUBLIC_BUILD_FILES` in
`src/public_build_contract.py`; the verifier checks this automatically.

The first command deliberately fails on an unlisted file, a symlink, a blocked
artifact type, a non-public identifier in source or documentation, or a
builder-source hash that differs from the pinned public release.

## Keep changes reviewable

- Add a synthetic regression test for behavior changes.
- Keep source parsing deterministic and offline during the deck build.
- Do not add a dependency unless the same result cannot reasonably be achieved
  with the standard library or an existing locked dependency.
- Update the source allowlist and release pin together when public builder files
  change.
- Use a short, imperative commit subject.

CI runs the public synthetic test set on macOS and Windows. Actual release
acceptance also requires a local build from the maintainer's 17 matching PDFs on
both platforms; those inputs never enter CI.

By contributing, you agree that your contribution is licensed under
AGPL-3.0-or-later, as described in `LICENSE`.
