# Installation and first call

The architecture is one Python stdio MCP server, one standard Agent Skill, and
small client entries. Installing the Skill does not register the MCP server.
No account with this project is required. The server itself needs no API key.

## Dependencies

- Python 3.8+; server, setup helper and tests use the standard library. No pip
  package, Node.js, WSL or Docker is required for the server.
- Your own classic Logisim executable/JAR. **This repository does not include
  Logisim or third-party libraries.** Evolution 4.x is not supported.
- Java compatible with that runtime. A JDK is needed to compile three bridge
  classes. Java 8 bytecode is produced; the current Windows runtime test uses
  JDK 17. Compilation selects `-source 8 -target 8` on JDK 8 and `--release 8`
  on newer JDKs. A native macOS application wrapper is not a JAR; select the
  actual compatible Logisim JAR.

Structural reading/editing works without Java. Runtime port inspection,
building, connectivity checks, simulation, native PNGs and propagation require
Logisim and the relevant compiled bridges. See [runtime limits](compatibility.md).

## Windows PowerShell

```powershell
git clone https://github.com/Tebie888/logisim-classic-lab-tools.git
Set-Location logisim-classic-lab-tools
python --version
java -version
# Set your own installed executable or JAR; this is an illustrative path.
$env:LOGISIM_HUST_EXE = 'C:/path/to/your/logisim.exe'
python scripts/setup.py compile
python scripts/setup.py doctor
New-Item -ItemType Directory -Force .local/circuits | Out-Null
python scripts/setup.py install-skill --destination "$env:USERPROFILE/.agents/skills/logisim-classic-lab-workflow"
python scripts/setup.py config --client codex --workspace .local/circuits --output .local/codex.toml
```

If `python` launches the Microsoft Store, install Python or use `py -3` for the
commands. The generated client entry uses the running interpreter's absolute
path, avoiding the Store alias. If Java is missing from `PATH`, set `JAVA_HOME`
or `LOGISIM_MCP_JAVA` to your own Java executable before running setup.

`doctor` probes the runtime and reports missing bridge classes; a nonzero exit
means the full runtime setup is incomplete. Its output contains your paths:
keep it local. Environment assignments above affect this terminal only; the
generated entry includes the Logisim override so a separately launched client
does not need to inherit this terminal.

## Linux and macOS

```sh
git clone https://github.com/Tebie888/logisim-classic-lab-tools.git
cd logisim-classic-lab-tools
export LOGISIM_HUST_EXE='/path/to/your/classic-logisim.jar'
python3 scripts/setup.py compile
python3 scripts/setup.py doctor
mkdir -p .local/circuits
python3 scripts/setup.py install-skill --destination "$HOME/.agents/skills/logisim-classic-lab-workflow"
python3 scripts/setup.py config --client codex --workspace .local/circuits --output .local/codex.toml
```

Java is found through explicit `LOGISIM_MCP_JAVA`, `JAVA_HOME/bin/java` or
`PATH`; Windows additionally supports the Java registry. Python launches Java
with an argument array, and the classpath separator follows the host OS.
Windows GUI/Word helper scripts remain Windows-specific. Linux/macOS runtime
execution has not been verified in the current Windows-only test environment.

## Install the same Skill in another client

Use the same source `skills/logisim-classic-lab-workflow/`; do not maintain
client-specific instruction copies. Append `logisim-classic-lab-workflow` to
one of these roots and pass that complete destination to `install-skill`.
Replace `~` in command arguments with your shell's home-directory variable.

| Client | User Skill root | Project Skill root |
| --- | --- | --- |
| Codex | `~/.agents/skills/` | `.agents/skills/` |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Cursor | `~/.cursor/skills/` or `~/.agents/skills/` | `.cursor/skills/` or `.agents/skills/` |
| Gemini CLI | `~/.gemini/skills/` or `~/.agents/skills/` | `.gemini/skills/` or `.agents/skills/` |
| OpenCode | `~/.config/opencode/skills/` or `~/.agents/skills/` | `.opencode/skills/` or `.agents/skills/` |
| ZCode | `~/.zcode/skills/` | `.zcode/skills/` (also supports importing to a project) |
| DeepSeek Harness | `~/.agents/skills/` | `.agents/skills/` |
| VS Code / Copilot | `~/.copilot/skills/` or `~/.agents/skills/` | `.github/skills/`, `.claude/skills/` or `.agents/skills/` |

The installer refuses an existing destination. For an upgrade, compare the
existing install, preserve local changes and choose a new installation location
or move the old install yourself before copying. Clients supporting directory
links can instead link to this canonical source; ZCode offers an Import →
Symlink mode. Restart/refresh Skill discovery after installation. Loading is
controlled by each client's enabled state, policies and context limits.

## Register MCP, then verify each layer

Generate an entry with `config --client <client>` and merge it into the
[client's configuration destination](../configs/README.md). This helper never
edits a live client configuration. Keep other settings and server entries.
Do not commit generated entries containing local absolute paths. Config examples
are not automatically installed or activated when the repository is cloned.

Use the absolute Python command and script path from setup. Directly spawning
`.cmd` files varies by Windows client; `mcp/run-mcp.cmd` is a manual launcher.
Reconnect the MCP server after code/configuration changes, then start a fresh
chat if the client caches schemas.

1. Confirm the Skill appears and can load. Codex/ZCode can explicitly select
   `$logisim-classic-lab-workflow`; Claude Code uses its Skill slash menu.
2. Confirm the MCP server is connected and lists **29 tools**, including
   `build_project`, `check_connections`, `export_circuit_image` and
   `trace_propagation`. Some clients prefix names with the server namespace.
3. Ask the model to call `logisim_env_info(probe_version=true)` directly through
   MCP. Merely printing a command does not verify invocation.
4. Copy `examples/half-adder.circ` into your fenced circuit workspace, then ask
   the model to call `describe_circuit` and `validate_circuit` on that file.
   Use your own absolute path; the fence deliberately excludes other files.
5. Ask for runtime checks and the four half-adder vectors below.

> Use logisim-classic-lab-workflow. In my configured circuit workspace, create
> a new half-adder with A/B inputs and SUM/CARRY outputs. Query real component
> ports, preview with dry_run, then build without replacing an existing file.
> Preserve the connection manifest, validate with runtime=true, check the
> expected nets, and export four differently named PNGs for inputs 00, 01, 10,
> 11. Assert (SUM,CARRY) = (0,0), (1,0), (1,0), (0,1).

`get_truth_table` and `get_simulation_table` parse observed output changes; they
do not enumerate those vectors. `simulate_tty` runs the file's `<main>` and
needs a real stop condition. For a minimal TTY check, copy the Skill's
`assets/minimal-halt.circ` into the fenced workspace. No personal circuits are
needed. A worked Chinese example is in the [tutorial](../skills/logisim-classic-lab-workflow/tutorial.md).

## Local verification

```sh
python -m unittest discover -s mcp -p "test*.py" -v
python mcp/build_examples.py .local/generated-examples
```

The example generator refuses existing targets. Runtime tests skip when the
runtime/bridges are absent; that is not a runtime pass. Compilation, protocol
checks, actual model calls and privacy checks are recorded separately in
[`VALIDATION.json`](../VALIDATION.json). See [troubleshooting](troubleshooting.md),
[ZCode](zcode.md) and [Harness](deepseek-harness.md) for client-specific details.
