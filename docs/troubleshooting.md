# Troubleshooting

Check discovery, connection, tools, invocation and runtime separately. Do not
repeatedly retry an unchanged failing command. Keep diagnostics local: errors,
`doctor`, tool outputs and generated configurations can contain your paths.

| Symptom | Check and corrective action |
| --- | --- |
| Skill absent | Keep the exact folder and uppercase `SKILL.md`, `name`/`description` frontmatter, enable it and refresh. Use a supported user/project directory; cloning `skills/` alone is not registration. |
| Skill loads but no MCP tools | Skill discovery and MCP registration are separate. Merge the correct client format and reconnect. Harness needs a mounted Cordis entry, not just an installed package. |
| Python not found / Store opens | Use the full installed Python executable; `setup.py config` records the interpreter running it. A GUI client may inherit a different `PATH`. |
| Server starts but connection fails | Start `python mcp/server.py --version`; then check the exact script and args. Do not wrap stdio with a command printing banners to stdout. MCP uses one UTF-8 JSON object per line, not HTTP Content-Length headers. |
| Only 28 tools, no `trace_propagation` | An old process or entry is still in use. Confirm server version 1.4.1, reconnect, and restart the session if schemas are cached. |
| `exe_exists=false` | Set `LOGISIM_HUST_EXE` in the MCP entry to your classic executable/JAR. Optional `LOGISIM_SEARCH_ROOT` searches only `logisim-hust-*.exe` beneath the specified root. No whole-machine scan is performed. |
| `java` missing | Set `LOGISIM_MCP_JAVA`, `JAVA_HOME` or `PATH`. Runtime compatibility depends on your Logisim distribution. |
| Missing `.class` / class incompatibility | Run `python scripts/setup.py compile` against the same selected runtime. Recompile after updating Java bridge source or changing runtime. A JRE alone lacks `javac`. |
| Workspace error | The circuit, output, RAM image and transitive external circuit libraries must resolve inside `LOGISIM_MCP_WORKSPACE`. Use absolute paths or a deliberate client `cwd`. Symlinks resolve before checking. |
| External JAR refused | In a fenced workspace, review the library as executable code before setting `LOGISIM_MCP_ALLOW_JAR_LIBRARIES=1` in your local MCP entry. Its path must still be inside the fence. The fence is not an OS sandbox. |
| `-32602` | Invalid tool name/arguments. Compare the discovered schema; unexpected parameters and wrong nested types are rejected. `simulate_tty` has no `circuit` argument. |
| `isError=true` | A tool execution failed (missing file/runtime, invalid candidate, etc.). Read the text payload; a JSON-RPC response alone is not a successful circuit operation. |
| Simulation timeout | A missing/low `halt` Pin, load failure or oscillating design may not finish. Use a bounded run and inspect verdict/diagnostics. `halt` is a Pin label with an actual driven value of 1. |
| Table incomplete / E / legacy `Error！` | Inspect `complete`, `process_ok`, `verdict`, unknown diagnostics and E values. The exact legacy marker is summarized separately; it is not an oscillation verdict. Tables record output changes and do not prove input coverage. |
| PNG exists / trace directory exists | Choose a new destination. Exports and traces refuse replacement. Component and viewport options are mutually exclusive. |
| Propagation incomplete | Check `max_events`, `max_time` and timeout. Limits return `complete=false`; no final stability claim is made. Internal API compatibility is verified only for the tested HUST runtime. |
| Native image looks different from a GUI screenshot | It is rendered by Logisim's engine; there is no application chrome. Inspect actual `pin_values` and simulated `layout_report`. Complex layouts may still need explicit spacing. |
| Windows edit says access denied | Close competing GUI saves and retry after re-reading. Brief sharing locks get bounded retries, with an external-change check each time. Backups remain if a commit fails; persistent permission failures are not bypassed. |
| Optional Windows launcher returns the wrong status | Update the Skill launcher with this release; console options now return the actual child status, and argument detection no longer echoes filenames through a shell pipeline. Prefer the absolute Python entry for MCP. |
| ZCode CLI says select a model | Configure/select a model in the intended ZCode session. Skill discovery does not establish model availability. See the actual partial test in [ZCode](zcode.md). |
| Wrong AI sees your files | MCP processes run on the client's execution host. Install Python, Logisim and Skill resources there; a remote/cloud agent cannot use a local desktop executable path automatically. |

Before a public bug report, replace private paths and identifiers and remove
credentials, session logs and personal circuits. Reproduce using an included
synthetic example or a minimal anonymous circuit. Do not upload a third-party
Logisim executable/JAR. See the [publication audit](privacy-audit.md).

Optional Skill fallback scripts are standalone local diagnostics. They do not
inherit the MCP server's workspace fence or all runtime preflight checks; use
the server for the guarded workflow. Set the client tool-call timeout longer
than your requested runtime budget, with startup margin. The server's TTY cap
does not change a client's own timeout settings.
