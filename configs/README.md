# Client entries

Replace every `<...>` value before use. Each command starts the same Python
stdio server. These are **merge fragments**, not replacements for existing
settings. Forward slashes in absolute paths work on Windows as well as POSIX.
No shell expansion of `<...>`, `~`, `$HOME` or `%USERPROFILE%` is assumed.

Prefer generating a local entry from your actual Python/repository paths:

```sh
python scripts/setup.py config --client codex --workspace /path/to/circuits
```

Choose `claude`, `cursor`, `gemini`, `opencode`, `zcode`, `harness`, `vscode`,
`copilot` or `generic` as needed. On Windows, pass your own workspace path.
`--output .local/client-config.json` refuses to replace an existing file.
Generated entries contain personal absolute paths: keep them local.

| Client | Template | Project destination | User destination |
| --- | --- | --- | --- |
| Codex | `codex.toml` | `.codex/config.toml` (trusted project) | `~/.codex/config.toml` |
| Claude Code | `mcpServers.json` | `.mcp.json` | Register with `claude mcp add --scope user`; managed in `~/.claude.json` |
| Cursor | `mcpServers.json` | `.cursor/mcp.json` | `~/.cursor/mcp.json` |
| Gemini CLI | `mcpServers.json` | `.gemini/settings.json` | `~/.gemini/settings.json` |
| OpenCode | `opencode.json` | `opencode.json` | `~/.config/opencode/opencode.json` |
| ZCode | `zcode.json` | `.zcode/config.json` | `~/.zcode/cli/config.json` |
| DeepSeek Harness | `harness.cordis.yml` | Extra `--patch` overlay | `$DSH_HOME/profiles/<profile>/cordis.patch.yml` |
| VS Code Local harness | `vscode.json` | `.vscode/mcp.json` | User profile `mcp.json` via MCP commands |
| Copilot portable config | `mcpServers.json` | `.mcp.json` where enabled | `~/.copilot/mcp-config.json` or `$COPILOT_HOME/mcp-config.json` |
| Other stdio MCP hosts | `mcpServers.json` as a structural example | Host-specific | Host-specific |

VS Code's current docs prefer Copilot Global/portable configuration for Copilot
sessions. `servers` and `mcpServers` are different formats. Availability depends
on the selected harness/version. ZCode Full configuration UI also accepts the
`mcpServers` fragment; its native on-disk shape is `mcp.servers`.

Official references and actual test status: [compatibility](../docs/compatibility.md).
Scope-specific Skill installation is separate: [installation](../docs/installation.md).
