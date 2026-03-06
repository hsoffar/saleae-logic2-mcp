# Saleae Logic 2 MCP Server

[Saleae Logic Analyzers](https://www.saleae.com/) are USB-connected tools used to inspect and decode digital signals (GPIO, UART, I2C, SPI) during hardware and firmware development.

This project brings Saleae Logic 2 into AI-assisted embedded debugging.
It exposes capture, decode, timing measurement, and export workflows as MCP tools for Claude, Codex, VS Code MCP agents, and other MCP hosts.

## Why Embedded Teams Use It

- Fast protocol bring-up and validation for UART, I2C, and SPI
- Repeatable capture and decode flows for firmware regression testing
- One-call signal checks for clocks, pulses, edges, and voltage thresholds
- Trigger-based capture for intermittent bugs and boot-sequence timing
- Clean CSV/table export for reports, CI artifacts, and traceability

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

## MCP Client Integration (Codex + Claude)

### Codex (easiest)

Edit `~/.codex/config.toml` and add:

```toml
[mcp_servers.saleae]
command = "/absolute/path/to/.venv/bin/saleae-mcp-server"

[mcp_servers.saleae.env]
SALEAE_HOST = "127.0.0.1"
SALEAE_PORT = "10430"
```

If your environment needs module execution instead of the script entrypoint, use:

```toml
[mcp_servers.saleae]
command = "/absolute/path/to/.venv/bin/python3"
args = ["-m", "saleae_mcp.server"]
cwd = "/absolute/path/to/repo"

[mcp_servers.saleae.env]
PYTHONPATH = "/absolute/path/to/repo/src"
SALEAE_HOST = "127.0.0.1"
SALEAE_PORT = "10430"
```

### Claude Desktop (and clients using `mcpServers` JSON)

Add this block in your MCP config:

```json
{
  "mcpServers": {
    "saleae": {
      "type": "stdio",
      "command": "/absolute/path/to/.venv/bin/saleae-mcp-server",
      "args": [],
      "env": {}
    }
  }
}
```

Restart Claude after saving config.

### VS Code and Other MCP Hosts

Use the same command and env values. Most MCP clients support the same `command` + `env` pattern.

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
