# Saleae Logic 2 MCP Server

MCP server for [Saleae Logic 2 Automation](https://saleae.github.io/logic2-automation/).  
It exposes logic analyzer actions (capture, decode, measure, export) as MCP tools for Claude, Codex, VS Code MCP clients, and other MCP hosts.

## What You Get

- Connect/disconnect to Logic 2
- Start/stop/wait/close/save/load captures
- Add analyzers and export analyzer tables
- Export raw CSV
- One-call reads (`read_digital`, `read_analog`, `read_mixed`)
- Signal measurements (frequency, pulse width, edge counts)
- One-call protocol decode (UART, I2C, SPI)
- Trigger/condition helpers (`read_on_trigger`, `wait_for_signal`, `wait_for_voltage`)

## Requirements

- Python 3.8+
- Saleae Logic 2 installed
- Logic 2 running with automation enabled:

```bash
Logic --automation
# or
Logic --automation --automationPort 10430
```

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## MCP Server Command

```bash
saleae-mcp-server
```

This is a stdio MCP server (launched by MCP clients, not as an HTTP server).

## MCP Client Integration

Use this server block in clients that support command-based MCP servers:

```json
{
  "mcpServers": {
    "saleae": {
      "command": "/absolute/path/to/.venv/bin/saleae-mcp-server",
      "env": {
        "SALEAE_HOST": "127.0.0.1",
        "SALEAE_PORT": "10430"
      }
    }
  }
}
```

### Claude (Desktop / MCP-capable clients)

Add the `mcpServers.saleae` block to your Claude MCP configuration and restart Claude.  
Use absolute paths for the virtualenv binary.

### Codex

Add the same `mcpServers.saleae` entry to your Codex MCP config, then reload the session.  
After startup, ask Codex to run `saleae.status` or `saleae.list_devices` to verify connectivity.

### VS Code and other MCP hosts

For VS Code MCP extensions/agents (and similar hosts), register the same command and env values.  
If the host supports JSON-based MCP server definitions, the snippet above works directly.

## Quick Verification Flow

1. Start Logic 2 with `--automation`.
2. Start your MCP client with this server configured.
3. Run:

```text
saleae.connect()
saleae.list_devices()
saleae.read_digital(channels=[0], duration_seconds=0.05)
```

## Tool Catalog

### Connection

`saleae.connect`, `saleae.disconnect`, `saleae.status`, `saleae.list_devices`, `saleae.get_device_info`

### Capture Lifecycle

`saleae.start_capture`, `saleae.wait_capture`, `saleae.stop_capture`, `saleae.close_capture`, `saleae.save_capture`, `saleae.load_capture`

### Analyzers & Export

`saleae.add_analyzer`, `saleae.export_data_table`, `saleae.export_raw_csv`

### Reads, Measurement, Decode, Trigger

`saleae.read_digital`, `saleae.read_analog`, `saleae.read_mixed`, `saleae.measure_frequency`, `saleae.measure_pulse_width`, `saleae.count_edges`, `saleae.decode_uart`, `saleae.decode_i2c`, `saleae.decode_spi`, `saleae.read_on_trigger`, `saleae.wait_for_signal`, `saleae.wait_for_voltage`

## Example Capture + Decode Workflow

```text
saleae.connect()
saleae.start_capture({ ...timed payload... })
saleae.wait_capture(capture_id="...")
saleae.add_analyzer(capture_id="...", analyzer_name="I2C", settings={"SDA": 0, "SCL": 1})
saleae.export_data_table(capture_id="...", analyzer_ids=["..."], path="/tmp/i2c.csv")
saleae.close_capture(capture_id="...")
```

## Project Structure

- `src/saleae_mcp/server.py`: MCP tool definitions and input shaping
- `src/saleae_mcp/adapter.py`: Saleae automation wrapper and state management
- `tests/`: pytest suite for server wrappers and adapter behavior

## Development

```bash
pytest -q
```

## License

This project is licensed under Apache-2.0. See `LICENSE` for full terms.  
Redistributions must preserve attribution notices in `NOTICE`.
