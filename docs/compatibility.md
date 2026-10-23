# Compatibility and evidence matrix

Checked on 2026-10-23. **Documented** refers to vendor documentation;
**verified** means the action actually ran; **example only / unverified** means
no successful session test. Vendor support for a standard is not certification
of this toolkit. Results apply to the stated surface/version.

## AI clients

| Client | Vendor-documented capability | Skill discovery/load | MCP connection + listing | Model call | Runtime through client |
| --- | --- | --- | --- | --- | --- |
| OpenAI Codex | Skills, stdio MCP | Existing installed Skill visible | Existing 1.4.0 connection observed; 1.4.1 unverified | Existing 1.4.0 environment call verified | Existing HUST probe only; candidate entry supplied |
| Claude Code | Skills, stdio MCP | Example only | Example only | Unverified | Unverified |
| Cursor | Skills, stdio MCP | Example only | Example only | Unverified | Unverified |
| Gemini CLI | Skills, stdio MCP | Example only | Example only | Unverified | Unverified |
| OpenCode | Skills, local stdio MCP | Example only | Example only | Unverified | Unverified |
| ZCode CLI 0.17.0 | Skills, stdio MCP | Project discovery verified; model load unverified | Unverified, model-selection prerequisite blocked prompt | Unverified | Unverified |
| DeepSeek Harness headless 0.1.7-rc.2 | Skill plugins, stdio MCP bridge | Discovery and `skill` load verified | 29 model-facing Logisim tools verified | Environment/circuit read verified | Half-adder build/validate/4 vectors and halt TTY verified |
| VS Code / GitHub Copilot | Skills, MCP (format varies by harness) | Example only | Example only | Unverified | Unverified |
| Other compatible hosts | Host-dependent | Standard Skill supplied | Generic stdio example | Unverified | Unverified |

Harness used a real model/tool loop and an isolated headless profile, not a
shell JSON-RPC test. The inspected existing web composition had Skill plugins
but lacked the MCP mount. It was not overwritten. The Electron UI is unverified.
The earlier 2026-10-11 session exposed zero Logisim tools; its valid historical
findings remain in [session notes](harness-session-test.md).

ZCode's Skill listing does not prove MCP connection or model invocation. The
CLI stopped at `Select a model before sending a message`; see [details](zcode.md).

## Runtimes and platforms

| Target | Format handling | Execution evidence / limit |
| --- | --- | --- |
| Classic 2.3.x | `version="1.0"`; source-marker/read/edit tests | HUST migration exercised; separate 2.3 binary unverified |
| Classic 2.6.x | Accepted; #Base mapping tests | HUST exercised; separate 2.6 binary unverified |
| Classic 2.7.x | Accepted; old Counter/default geometry retained | HUST exercised; separate 2.7 binary unverified |
| HUST 2.15.0.2 | Includes GUI `.exe` source suffix without rewriting | Windows + JDK 17, bridges target Java 8 |
| Other classic forks | Diagnose rather than assume | Component/API differences may fail; unverified |
| Evolution 4.x | Rejected for editing/simulation | Unsupported; no format migration added |
| Windows | Native Python/Java, optional GUI/Word helpers | Current real runtime/client test host |
| Linux/macOS | Portable paths/classpath and installation instructions | Runtime execution unverified locally; CI reported separately |

Propagation uses internal engine fields/methods verified for HUST 2.15. Missing
APIs fail explicitly; no substitute simulator is used. Source compatibility
does not imply every tool works with every classic binary. Word automation is
Windows-only; optional report rendering needs Word and `pypdfium2`.

## Core protocol scope

UTF-8 newline-delimited stdio JSON-RPC 2.0; negotiated revisions 2024-11-05,
2025-03-26 and 2025-06-18. A newer proposal receives the legacy supported
revision, which the client must accept or reject. The server advertises tools,
not Resources, Prompts, HTTP or authentication. Calls execute sequentially with
bounded runtime operations; immediate cancellation of in-flight Java work is
not implemented. Python, Logisim and project files must exist on the client's
actual execution host; cloud clients cannot automatically use desktop paths.

## Official configuration references

- [Agent Skills](https://agentskills.io/specification)
- MCP [stdio](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
  and [lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle)
- Codex [Skills](https://developers.openai.com/codex/skills), [MCP](https://developers.openai.com/codex/mcp)
- Claude Code [Skills](https://code.claude.com/docs/en/skills), [MCP](https://code.claude.com/docs/en/mcp)
- Cursor [Skills](https://cursor.com/docs/skills), [MCP](https://cursor.com/docs/mcp)
- Gemini CLI [Skills](https://geminicli.com/docs/cli/skills/), [MCP](https://geminicli.com/docs/tools/mcp-server/)
- OpenCode [Skills](https://opencode.ai/docs/skills/), [MCP](https://opencode.ai/docs/mcp-servers/)
- ZCode [Skills](https://zcode.z.ai/en/docs/skill), [MCP](https://zcode.z.ai/en/docs/mcp-services)
- Harness [MCP client](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md)
  and [Skill provider](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md)
- VS Code [Skills](https://code.visualstudio.com/docs/agent-customization/agent-skills)
  and [MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers)

See [installation](installation.md), [configuration destinations](../configs/README.md)
and [VALIDATION.json](../VALIDATION.json). A new CI workflow is not a test pass
until it runs.
