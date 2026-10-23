# Logisim Classic Lab MCP

This directory contains the local stdio MCP server. It uses Python 3.8+ standard library modules and requires a compatible classic Logisim executable plus Java for runtime-backed simulation, validation, and PNG export. The executable and JAR are not included.

Set `LOGISIM_HUST_EXE` to the full path of your own compatible Logisim executable. Despite the legacy variable name, the server accepts compatible classic builds. No whole-machine search happens by default; optionally set `LOGISIM_SEARCH_ROOT` to recursively search a directory for `logisim-hust-*.exe`. An explicit `exe` argument to `logisim_env_info` also overrides discovery.

Compile the Java 8 bridge classes once:

```powershell
$env:LOGISIM_HUST_EXE = 'C:/path/to/your/logisim.exe'
javac --release 8 -encoding UTF-8 -classpath $env:LOGISIM_HUST_EXE PortProbe.java CircuitImage.java PropagationTrace.java
```

Start the server with `python server.py`, or run `python server.py --version` and `python server.py --print-config` to inspect the local install. The latter prints generic JSON and Codex TOML text, without registering a server. For a machine-readable client entry use `python scripts/setup.py config` from the repository root. DeepSeek Harness requires its `@deepseek-ai/dsh-mcp-client` profile entry described in the repository's `docs/deepseek-harness.md`.

`simulate_tty` and `get_simulation_table` run the file's `<main>` circuit; neither accepts a `circuit` selector. If the file has no halt pin, `simulate_tty` may reach its timeout. The table tool parses output changes and does not enumerate inputs automatically.

Run the tests from this directory with `python -m unittest discover -s . -p "test*.py" -v`.

Version 1.4 accepts the `2.15.0.2.exe` source marker written by the HUST GUI without changing the project. Builders support `include_details=false` to remove repeated port geometry while retaining the connection manifest; `include_manifest=false` also omits that manifest when the caller already saved it. Defaults preserve the full response.

`export_circuit_image` accepts either `component={name,loc}` to draw one actual component or `viewport={x,y,width,height}` to draw a circuit region. These produce native engine images, not GUI window screenshots.

`trace_propagation` records actual propagation events from stable `initial_inputs` to simultaneous `inputs`. It writes CSV and metadata to a new `output_dir`, supports optional event-time native PNGs, distinguishes output stability from queue completion, and can align delays to an actual `anchor_signal` edge. Limits produce incomplete results rather than a false pass. A full source checkout contains the [propagation reference](../skills/logisim-classic-lab-workflow/propagation-measurement.md); standalone installations can read that reference in the installed skill. The bridge API is verified against HUST 2.15; unsupported runtime internals fail explicitly.
