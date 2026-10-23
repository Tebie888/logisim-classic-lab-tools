# Publication/privacy audit

The publication boundary is the explicit
[`publish-allowlist.txt`](../scripts/publish-allowlist.txt). The isolated release
checkout contains only public upstream content, individually selected generic
local source/Skill changes and the new source/docs/templates/tests. Original
local sources were checkpointed outside this checkout before integration.

## Included and excluded material

- Existing example circuits and the Skill halt fixture are anonymous synthetic
  demonstrations. Their original bytes are retained; the PNG shows a synthetic
  half-adder, not a desktop screenshot. No course project is substituted.
- The separate installed HUST/course Skill, its private defaults and launcher
  are not imported. The portable Skill's nonportable external documentation
  reference is replaced with a public link; its local resources stay bundled.
- Personal circuits, homework, reports, course packages and unrelated workspace
  folders are outside the publication checkout and are not staged.
- Java executables/JARs, compiled classes, raw client profiles, keys, credential
  stores, logs, raw AI sessions, machine identifiers and generated runtime
  evidence remain local. The ignored `.local/` area contains test outputs and
  client-specific absolute paths, and is not part of the public allowlist.
- Configuration templates contain placeholders. Setup-generated configurations
  include the user's actual paths and must not be published.
- New commit metadata uses a generic contributor identity; existing upstream
  GitHub attribution is preserved. No history rewrite or repository permission
  change is part of this update.

## Checks

`scripts/check_release.py` checks selected working files, staged blobs (`--staged`)
or an exact revision (`--revision`). It rejects files outside the allowlist,
unexpected file types, large files, publication symlinks/submodules and common
credential/private-home/email patterns. PNG chunks are checked for embedded
text/EXIF metadata and trailing data. It never stages or uploads files.

Manual review additionally checks code changes, example labels, references,
file ownership and local-specific content that a regular expression cannot
identify. Git blobs and the to-be-pushed commit are reviewed separately from
working files. Original public history is checked without modifying it.
Current counts/results are recorded in [`VALIDATION.json`](../VALIDATION.json).

These checks assist review; they cannot prove the absence of every secret or
piece of personal information. Future contributors must review allowlist
changes and file content before committing. Never use blanket staging for this
workspace. Keep bug reproductions synthetic and strip paths/identifiers before
sharing diagnostics.
