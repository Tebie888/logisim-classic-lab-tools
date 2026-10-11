# Logisim Classic Lab MCP

This directory contains the local stdio MCP server. It uses Python 3.8+ standard library modules and requires a compatible classic Logisim executable plus Java for runtime-backed simulation, validation, and PNG export. The executable and JAR are not included.

Set `LOGISIM_HUST_EXE` to the full path of your own compatible Logisim executable. Despite the legacy variable name, the server accepts compatible classic builds. No whole-machine search happens by default; optionally set `LOGISIM_SEARCH_ROOT` to recursively search a directory for `logisim-hust-*.exe`. An explicit `exe` argument to `logisim_env_info` also overrides discovery.

Compile the Java 8 bridge classes once:

```powershell
$env:LOGISIM_HUST_EXE = 'C:/path/to/your/logisim.exe'
javac --release 8 -encoding UTF-8 -classpath $env:LOGISIM_HUST_EXE PortProbe.java CircuitImage.java
```

Start the server with `python server.py`, or run `python server.py --version` and `python server.py --print-config` to inspect the local install. The latter prints a generic client configuration; DeepSeek Harness requires its `@deepseek-ai/dsh-mcp-client` profile entry described in the repository's `docs/deepseek-harness.md`.

`simulate_tty` and `get_simulation_table` run the file's `<main>` circuit; neither accepts a `circuit` selector. If the file has no halt pin, `simulate_tty` may reach its timeout. The table tool parses output changes and does not enumerate inputs automatically.

Run the tests from this directory with `python -m unittest discover -s . -p "test*.py" -v`.
