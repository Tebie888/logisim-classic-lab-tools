# Tool inventory (1.4.1)

The local 1.4.0 candidate had **29 tools**; public 1.3.2 had **28**. Every original
name and default argument/response contract is retained. `trace_propagation` is
the additional local capability. The authoritative schemas come from
`tools/list`; the optional component/viewport and response-suppression arguments
are additive.

`XML` requires Python only. `Runtime` requires the selected classic Logisim and
Java; bridges are compiled locally. Circuit edit/build/restore tools accept
`dry_run`; PNG and trace output tools instead refuse existing destinations.

| Tool | Reviewed behavior/boundary | Dependency |
| --- | --- | --- |
| `logisim_env_info` | Environment report; optional bounded version probe | XML / Runtime probe |
| `list_circuits` | Main, circuits, source and libraries | XML |
| `describe_circuit` | Overview with correct Pin/subcircuit classification | XML |
| `list_pins` | Built-in Pins, labels, widths and directions | XML |
| `count_components` | Per-circuit/all-circuit counts | XML |
| `find_components` | Bounded component metadata search | XML |
| `get_circuit_xml` | Paginated original circuit text | XML |
| `list_library_index` | This file's library mapping | XML |
| `validate_circuit` | Structure; optional driver/width/topology checks | XML / Runtime |
| `simulate_tty` | Only file main, timeout/output cap, optional RAM image | Runtime |
| `get_truth_table` | Retained alias; observed changes, no enumeration | Runtime |
| `add_wire` | Unique orthogonal wire; protected commit | XML |
| `add_pin` | Valid width, direction, location and library | XML |
| `set_pin_label` | Unique Pin selector, escaped XML label | XML |
| `remove_component` | Explicit location/name, validated candidate | XML |
| `remove_wire` | Explicit endpoints, validated candidate | XML |
| `restore_backup` | List or validate/restore bytes, pre-restore snapshot | XML |
| `get_simulation_table` | Retain E/diagnostics and completion state | Runtime |
| `list_component_catalog` | Installed runtime names/defaults | Runtime + PortProbe |
| `get_component_ports` | Actual indices, geometry and widths | Runtime + PortProbe |
| `build_project` | Multiple circuits, checked routing and protected commit | Runtime + PortProbe |
| `build_circuit` | Single-circuit entry, same checks | Runtime + PortProbe |
| `create_project` | Exclusive creation | Runtime + PortProbe |
| `add_circuit` | Append through protected builder | Runtime + PortProbe |
| `add_component` | Runtime attributes and validated append | Runtime + PortProbe |
| `connect_ports` | Explicit endpoint identities, checked routing | Runtime + PortProbe |
| `check_connections` | Driver/width and expected-net topology | Runtime + PortProbe |
| `export_circuit_image` | Settled native whole/component/viewport PNG | Runtime + CircuitImage |
| `trace_propagation` | Bounded native events and optional images | Runtime + PropagationTrace |

Review covers required/nested schema types, selectors, bounds and implementation
mapping. Unknown arguments fail at the protocol boundary; execution errors
return `isError=true`. Stdout stays newline-delimited JSON-RPC; Java diagnostics
are captured. Runtime dependencies are preflighted when the workspace fence is
enabled. `complete`, `ok`, `process_ok` and actual signal values have different
meanings: validity, termination and input coverage do not prove one another.
Expected-net checking requires an explicit design manifest.

See [compatibility](compatibility.md) and
[propagation semantics](../skills/logisim-classic-lab-workflow/propagation-measurement.md).
