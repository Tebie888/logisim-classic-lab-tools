# Logisim Classic Lab Tools

A local MCP server and Codex skill for inspecting, validating, editing, simulating, and documenting classic Logisim `.circ` projects. The tools are independent, community-maintained software and are not affiliated with any university or with the original Logisim authors.

兼容经典 Logisim 2.3.x、2.6.x、2.7.x 工程；课程版分支的实测兼容版本为 Logisim-HUST 2.15.0.2。版本号仅说明测试环境，不代表官方支持。项目名和品牌不代表学校或原软件作者。

## Components

- `mcp/`: Python stdio MCP server (28 tools) with structural/runtime validation, connectivity analysis, safe edits, batch building, simulation, and PNG circuit export.
- `skills/logisim-classic-lab-workflow/`: Codex workflow skill with references and optional Windows helper scripts.
- `examples/`: small synthetic example circuits.

## Requirements

- Python 3.8 or newer; MCP server and tests use only the standard library.
- Java runtime compatible with the Logisim executable for simulation and runtime-backed validation/export. Java 8 bytecode is used for the bridge classes.
- Your own compatible classic Logisim executable or JAR. It is not included. Set `LOGISIM_HUST_EXE` to its full path. Logisim Evolution 4.x is not supported for editing or simulation.
- `javac` is only needed to compile the bridge classes; prebuilt `.class` files are generated locally and excluded from this repository.

## Install MCP

1. Clone this repository and build bridge classes against your locally installed Logisim executable:

   ```powershell
   cd mcp
   javac --release 8 -encoding UTF-8 -classpath "$env:LOGISIM_HUST_EXE" PortProbe.java CircuitImage.java
   ```

2. Add a stdio server entry to your MCP client. Use an absolute path to `mcp/server.py`:

   ```json
   {
     "mcpServers": {
       "logisim-classic-lab-mcp": {
         "command": "python",
         "args": ["<REPOSITORY_DIR>/mcp/server.py"],
         "env": { "LOGISIM_HUST_EXE": "<PATH_TO_LOGISIM_EXECUTABLE>" }
       }
     }
   }
   ```

   On Windows, `mcp/run-mcp.cmd` can be used as the command. Reconnect the MCP client after changing its configuration.

3. Verify discovery and the executable:

   ```powershell
   python mcp/server.py --version
   python mcp/server.py --print-config
   python mcp/server.py --self-test <PATH_TO_TEST_CIRCUIT>
   ```

The server can inspect project XML without Java, but simulation and image export require a compatible runtime. Set `LOGISIM_MCP_WORKSPACE` to restrict file operations to a workspace. `LOGISIM_MCP_MAX_TIMEOUT` controls the simulation timeout cap.

## Install the skill

Copy `skills/logisim-classic-lab-workflow/` to your Codex skills directory, preserving the directory name. Restart or refresh the Codex session so it discovers the skill. The scripts in that folder are optional; the MCP is preferred when connected. Windows Word automation and PDF page rendering are optional report-checking features and require Microsoft Word plus the Python package `pypdfium2`.

## Tests and examples

```powershell
python -m unittest discover -s mcp -p "test*.py" -v
python mcp/build_examples.py <EMPTY_OUTPUT_DIRECTORY>
```

Bridge compilation is separate from unit tests. The two example circuits are small synthetic smoke tests; the validation summary records the checks run for this release.

## Compatibility and limitations

The project supports classic Logisim XML (`version="1.0"`) with source versions 2.3.x, 2.6.x and 2.7.x, plus the tested Logisim-HUST 2.15.0.2 course fork. Other sources can be diagnosed read-only where possible. Logisim Evolution 4.x is a different project format and is not supported for edits or simulation.

Runtime layout reports are produced after simulation, when Probe display widths are known. Static layout checks can miss display overlap. Connectivity checks compare against declared expected nets; they cannot infer design intent when no expected network manifest is provided. The project is not affiliated with HUST, any university, or the original Logisim authors.

## License

MIT. The license applies to original source code, documentation, skill files, scripts, and included synthetic examples in this repository. Logisim itself and other third-party components are not included and remain under their respective licenses.
