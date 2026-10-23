# Logisim Classic Lab Tools

[中文](README.zh-CN.md) · [Install](docs/installation.md) · [Compatibility](docs/compatibility.md) · [Troubleshooting](docs/troubleshooting.md)

One local **stdio MCP server + one standard Agent Skill** for inspecting,
building, safely editing, validating, simulating and rendering classic Logisim
`.circ` projects. Server **1.4.1** exposes **29 tools**, retaining all 28 public
1.3.2 tool names and the newer local propagation feature.

Classic Logisim 2.3.x, 2.6.x, 2.7.x (`version="1.0"`) and the tested
Logisim-HUST 2.15.0.2 are the target. **Logisim-evolution 4.x is not supported.**
This independent community project is not affiliated with a university, the
original Logisim authors or any AI client vendor.

## What is included

- `mcp/`: standard-library Python server, Java port/image/propagation bridges,
  protected builders, connectivity checks, backups and regression tests.
- `skills/logisim-classic-lab-workflow/`: the canonical portable `SKILL.md`,
  references, a worked tutorial and optional Windows helpers.
- `examples/`: anonymous synthetic half-adder, full-adder and counter circuits.
- `configs/`: lightweight client formats; `scripts/setup.py` generates local
  entries, compiles bridges and installs the same Skill without overwriting.

The [tool inventory](docs/tools.md) explains each of the 29 tools. Newer local
features include native propagation traces, component/viewport PNGs, HUST GUI
source markers and smaller optional builder responses. The [audit](docs/audit.md)
records what was compared, retained and corrected.

## Client status

The linked official client docs describe supported standards; they do not
constitute certification of this toolkit. **Configuration examples are not
successful client tests.** The full [matrix](docs/compatibility.md) separates
Skill discovery, connection, tool listing, invocation and runtime execution.

| Client | Current project evidence |
| --- | --- |
| OpenAI Codex | Existing local 1.4.0 MCP environment call observed; 1.4.1 entry supplied, fresh Codex session not tested |
| Claude Code | Official-format configuration and Skill locations; session unverified |
| Cursor | Official-format configuration and Skill locations; session unverified |
| Gemini CLI | Official-format configuration and Skill locations; session unverified |
| OpenCode | Official-format configuration and Skill locations; session unverified |
| ZCode | Project Skill discovery verified in CLI 0.17.0; model-selection prerequisite blocked session MCP test |
| DeepSeek Harness | Real headless session loaded Skill, exposed 29 tools and called read-only MCP tools |
| VS Code / GitHub Copilot | Local/portable formats documented; session unverified |
| Other MCP / Agent Skills hosts | Standards-based entry example; host-specific support must be tested |

See [ZCode](docs/zcode.md) and [DeepSeek Harness](docs/deepseek-harness.md).
No per-client server fork or proprietary core dependency is introduced.

## Install MCP

Requires **Python 3.8+**, your own compatible **classic Logisim executable/JAR**,
and compatible **Java** for runtime operations. A **JDK** is needed to compile
bridges targeting Java 8. No pip install is required. **Logisim and third-party
JARs are not bundled.** XML inspection can run without Java.

Windows PowerShell quick start (replace the illustrative executable path):

```powershell
git clone https://github.com/Tebie888/logisim-classic-lab-tools.git
Set-Location logisim-classic-lab-tools
$env:LOGISIM_HUST_EXE = 'C:/path/to/your/logisim.exe'
python scripts/setup.py compile
python scripts/setup.py doctor
New-Item -ItemType Directory -Force .local/circuits | Out-Null
python scripts/setup.py install-skill --destination "$env:USERPROFILE/.agents/skills/logisim-classic-lab-workflow"
python scripts/setup.py config --client codex --workspace .local/circuits --output .local/codex.toml
```

Merge the generated entry into your client's configuration, reconnect MCP and
refresh Skills. For another client, change `--client` and choose its Skill
installation directory from [installation](docs/installation.md) and
[configuration destinations](configs/README.md). Generated entries contain
personal paths and must stay local. Existing installs/config files are never
replaced by the helper.

Linux/macOS use `python3`, a compatible JAR, `export LOGISIM_HUST_EXE=...` and
`$HOME` instead. Their current runtime verification status is explicitly
[documented](docs/compatibility.md); Windows GUI/Word helpers are not portable.

## First natural-language task

First ask your Agent to load `logisim-classic-lab-workflow`, list the MCP tools
and actually call `logisim_env_info(probe_version=true)`. Then:

> Create a new half-adder in my configured circuit workspace: A/B inputs,
> SUM=A XOR B and CARRY=A AND B. Query real ports, dry-run the build, then
> create without overwriting. Save the connection manifest, perform runtime
> validation and expected-net checks, and export four PNGs for 00, 01, 10, 11.
> Assert (SUM,CARRY) = (0,0), (1,0), (1,0), (0,1).

Read the [worked Chinese tutorial](skills/logisim-classic-lab-workflow/tutorial.md).
`simulate_tty` runs only the file's `<main>`; table tools record observed output
changes and **do not enumerate inputs**. A timeout is not a pass. Propagation
records actual engine events, not physical nanoseconds or a replacement model.

## Safety and verification

Edits validate candidate XML before byte backups and atomic replacement.
`dry_run` validates without committing. New projects, images and trace directories
refuse overwrite. Set `LOGISIM_MCP_WORKSPACE` to fence circuit/output paths and
external circuit libraries. External JARs in a fenced workspace require explicit
trust. This is a path boundary, **not an OS sandbox**; use trusted runtimes and
libraries. See [troubleshooting](docs/troubleshooting.md).

```sh
python -m unittest discover -s mcp -p "test*.py" -v
python mcp/build_examples.py .local/generated-examples
```

Runtime cases skip without a user-supplied runtime/compiled bridges. Fresh
results are in [VALIDATION.json](VALIDATION.json); original historical evidence
is distinguished from the current run. Before publishing, review the explicit
[file allowlist](scripts/publish-allowlist.txt), run `python scripts/check_release.py`
and inspect staged blobs with `--staged`. The [privacy audit](docs/privacy-audit.md)
records exclusions and scan limitations. Do not publish personal circuits,
reports, real client configurations, credentials or session logs.

## License

MIT for this repository's original source, documentation, scripts and synthetic
examples. Logisim and other third-party components remain under their own
licenses and must be obtained separately.
