# release-0.05a

Prepare the 0.05a release: validate the PyInstaller bundle end to end, make the
version bump safe, bump the version and update the release documents.

## Why

The repository is a preservation project whose deliverable is the downloadable
bundle, and the bundle is the only part of the recent work that was never
validated: pyInstaller is not installed on this machine, so only the `xcopy` step
added to `build/build.bat` could be checked in isolation.

There is also a hidden landmine in the version bump. `version.py` defines
`version_code = "0.04a"` and the `0.04a -> 0.05a` step is commented out, so raising
the version without uncommenting it makes `migrate_loaded_save` match no block,
return "modified", and have the loader rewrite every save on every startup while
the save's own version still says 0.04a. It never converges.

## Steps

- [ ] T1 Install pyInstaller (needed for the build).
- [ ] T2 Make the 0.04a -> 0.05a migration real, test-first.
- [ ] T3 Bump `version_name` / `version_code` to 0.05a.
- [ ] T4 Update `RELEASES.md` and the README release table.
- [ ] T5 Build the bundle and verify it end to end.
- [ ] T6 Commit and push; the zip and the GitHub release stay the user's decision.

## Verification plan

- Tests for the migration: a 0.04a save migrates to 0.05a and reports modified; a
  save already at the current version reports not modified and is not rewritten;
  the older chain (no version, 0.01a) still converges.
- The bundle: run `build.bat`, then start the packaged exe and check
  - `mods/` and `saves/` exist next to the exe,
  - the served config is the modded one (2,111,890 bytes, versus 2,111,190 without
    mods, which is the difference the author measured earlier),
  - the hardened fingerprints are live in the exe (`/null` 302, `command` 400 JSON,
    config gzipped 142,222 bytes).
- `pytest tests -q` and `ruff check .` stay clean.

## Risks

- The build writes about 1.3 GB into `build/dist` (gitignored) and takes minutes.
- Bumping the version rewrites the user's save once, on the next server start,
  through the migration: expected, and their save is backed up.

## Out of scope

- Publishing the release (tag, zip upload) and the offline Ruffle browser check:
  both are the user's.
