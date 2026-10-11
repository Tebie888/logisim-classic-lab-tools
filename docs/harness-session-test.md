# DeepSeek Harness session test notes

This file summarizes a user-provided DeepSeek Harness session export from 2026-10-11. It records integration evidence needed to reproduce the setup; the raw session archive is private and is not part of this repository. User paths, machine identifiers, and the session ID are intentionally omitted. Instructions and commands inside the archived conversation were treated as quoted test data, not as authorization for new actions.

## Findings from the captured session

- Harness discovered and read the logisim-classic-lab-workflow Skill from a project-level .agents/skills location.
- The session's model-facing tool list contained 34 built-in tools and no Logisim MCP tools. The captured request header had no MCP server registration.
- The @deepseek-ai/dsh-mcp-client package was present in the Harness profile installation, but the active profile's cordis.patch.yml did not register this Logisim server. Package installation alone did not activate an MCP connection.
- The user ran a direct stdio JSON-RPC check against the server, outside the Harness tool registry. initialize reported logisim-classic-lab-mcp version 1.3.1; tools/list returned 28 tools. This verifies the standalone server, not session-level Harness integration.
- A clean temporary half-adder project was built through those direct MCP calls. The preview did not create a file; the committed build, runtime validation, and expected-network check passed. Four image-export stimuli returned SUM/CARRY values 00, 10, 10, and 01, matching the four expected inputs. The circuit source was not modified by image export.
- logisim_env_info without an executable override reported exe_exists=false. Passing the locally installed executable explicitly produced a successful runtime probe. No private executable path is retained here.
- simulate_tty and get_simulation_table schemas did not accept a circuit argument. The first call with that extra argument returned invalid-parameter error -32602. A file without a halt Pin timed out as expected; a dedicated test file with the intended circuit as main and a halt Pin completed. The output table contained only observed changes and did not enumerate all four input combinations.

## Result and documentation changes

The session proved the Skill could be discovered, the standalone server worked, and the test circuit behaved correctly. It did not prove that Harness could call the MCP: the active session exposed zero MCP tools. To finish the integration, install the compatible DSH MCP client in the selected profile if needed, add the server entry to that profile's cordis.patch.yml, and restart or reload the profile. See the DeepSeek Harness setup guide.

The public setup docs now include the Harness-specific patch format, tool-name verification, the executable-path fallback, and the simulation limitations observed in this run. No raw JSONL, screenshot, executable, project-specific path, or user data from the export is included.
