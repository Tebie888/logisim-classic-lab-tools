# Local-to-public audit

Baseline: public `main` at `816caaf`, server 1.3.2, 28 tools. The active local
launcher targets a standalone 1.4.0 server; its source changes match the local
Git checkout after normalizing line endings. That checkout is on `main` with
eight modified tracked files and three untracked feature files. No local
commit is ahead of the public branch. Private originals were backed up outside
the publication checkout before integration. Machine paths are intentionally
omitted here.

## Reusable local changes

- `trace_propagation` plus `PropagationTrace.java`: bounded native propagation
  event recording, CSV, signal stability/anchor summaries, optional event images.
- `export_circuit_image`: component selection or viewport, with matching layout
  report scope. Ordinary export still settles every stimulus.
- Builders: `include_details=false` suppresses repeated geometry;
  `include_manifest=false` optionally omits a previously saved manifest.
- Accept HUST's GUI-written `2.15.0.2.exe` source suffix without rewriting it.
- Skill guidance for propagation, report reuse and avoiding duplicate work.

The candidate retains all 28 original names and adds the one local tool (29
total). `get_truth_table` remains a compatibility alias, not an input enumerator.
The original circuit format, simulation engine and Java port bridge are retained.

## Skill/source ownership

One portable Skill belongs to this repository. Two installed copies of that
Skill have the same generic content. A separate course-specific HUST Skill is
also installed locally; it includes machine/course-specific material and belongs
to a separate toolkit. It is not merged or published here. Personal circuits,
reports, course materials, session archives, runtime binaries, compiled classes
and local verification logs are excluded.

## Minimal change boundary

Integrate the explicit Python/Java feature files above and their generic Skill
references. Fix demonstrated protocol, parsing, runtime path and portability
defects in their owning modules. Keep existing APIs and response defaults.
Add focused regressions, a standard-library setup/configuration helper, lightweight
client templates, installation/troubleshooting/compatibility documentation and
an explicit publication allowlist. Keep all live client profiles, credentials
and integration transcripts outside the publish set.

## Validation policy

The historical 47-test claim is not inherited. A fresh baseline ran 47 tests:
46 passed; one Windows atomic replacement failed with an access-denied error
while retaining the backup. Focused regressions and the final rerun are recorded
in `VALIDATION.json`. Discovery, connection, tool listing, model tool invocation
and circuit execution are separate evidence levels. An example configuration
does not imply a tested client. See [compatibility](compatibility.md).

## Demonstrated defects and minimal fixes

- Invalid initialize protocol versions raised an internal type error; they now
  receive an invalid-parameters reply and the session remains usable.
- A raw-byte DTD check missed UTF-16 XML. Parser-level rejection now covers
  those encodings before entity expansion.
- Pin-named subcircuits were counted as Pins, while built-ins sharing a circuit
  name were reported as subcircuits. Classification now follows library identity.
- JAVA_HOME only tried `bin/java.exe`; POSIX `bin/java` is also considered.
- Windows sharing/access locks could abort an otherwise valid atomic edit.
  Bounded retries recheck the original bytes before every replacement attempt.
- Runtime library paths were outside the original direct-file fence coverage.
  Fenced execution now preflights transitive `file#` libraries and requires
  explicit trust for in-fence external JAR libraries. Unfenced trusted-runtime
  behavior is retained; the fence is not a system sandbox.
- A builder endpoint check compared coordinates alone, missing an extra port
  at an intended endpoint. It now compares component/port identity.
- Runtime-dependent tests failed rather than skipped without Logisim; the
  fixture now clearly separates portable tests from real runtime checks.
- The new setup helper initially inherited an ASCII stdout setting. A failing
  Unicode-path test led to explicit UTF-8 output.
- An installed Skill's relative Harness-doc link escaped its bundle; it now
  points to public documentation. Existing local Skill resources remain local.

Focused regressions reproduced the defects before fixes. The final full suite
ran 76 tests with zero failures/errors/skips; the no-Logisim run executed 51 and
skipped 25. The original 28 tool schemas retain their required arguments and
property validation rules. All local 1.4 features have regression coverage.
Original source/Skill directories remain intact; edits are in the isolated
release checkout. The 59-file publication set and four public historical commits
passed the content scan; public examples/PNG were inspected as synthetic.

The optional Windows launcher also returned the parser pipeline status instead
of the child status for console options. A real child-process regression failed
before the fix; the launcher now preserves the exit code and avoids echo-based
argument detection/delayed expansion. The release scanner was additionally
regression-tested against JSON-escaped Windows home paths.
