## What changed

Describe the public builder boundary or user-visible behavior changed by this PR.

## Verification

- [ ] `python scripts/verify-public-tree.py`
- [ ] `uv sync --locked --python 3.13`
- [ ] `uv run --locked python test/run_tests.py fast`
- [ ] Relevant wrapper syntax check completed
- [ ] Actual macOS/Windows 17-PDF release acceptance completed, or not required

## Publication boundary

- [ ] No publisher files, generated decks, audio, archives, local databases, credentials, or personal paths are included
- [ ] `config/public-source-files.txt` exactly matches the tracked file set
- [ ] Public builder changes are bound to an updated release pin
- [ ] License and notice changes were reviewed
