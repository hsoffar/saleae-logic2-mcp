# Saleae MCP Server

MCP server that wraps the [Saleae Logic 2 Automation API](https://saleae.github.io/logic2-automation/), exposing logic analyzer capabilities as LLM-callable tools.

## Requirements

- Python 3.10+
- [Saleae Logic 2](https://www.saleae.com/downloads/) installed
- Logic 2 running with automation enabled:
  ```
  Logic --automation
  # or with a custom port:
  Logic --automation --automationPort 10430
  ```

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run as MCP server

```bash
saleae-mcp-server
```

Uses stdio transport — launched by an MCP client, not run standalone.

## MCP client config

```json
{
  "mcpServers": {
    "saleae": {
      "command": "/path/to/.venv/bin/saleae-mcp-server"
    }
  }
}
```

Environment variables (optional):
- `SALEAE_HOST` — Logic 2 host (default `127.0.0.1`)
- `SALEAE_PORT` — Logic 2 automation port (default `10430`)

---

## Tools

### Connection

| Tool | Description |
|------|-------------|
| `saleae.connect` | Connect to a running Logic 2 instance |
| `saleae.disconnect` | Disconnect from Logic 2 |
| `saleae.status` | Check connection state and active captures |
| `saleae.list_devices` | List available hardware and simulation devices |
| `saleae.get_device_info` | Return metadata for a specific device (or all devices) |

### Capture lifecycle

| Tool | Description |
|------|-------------|
| `saleae.start_capture` | Start a capture (returns `capture_id`) |
| `saleae.wait_capture` | Block until capture completes |
| `saleae.stop_capture` | Stop a running (manual) capture |
| `saleae.close_capture` | Free a capture and release its resources |
| `saleae.save_capture` | Save capture to a `.sal` file |
| `saleae.load_capture` | Load a capture from a `.sal` file |

### Analysis & export

| Tool | Description |
|------|-------------|
| `saleae.add_analyzer` | Add a protocol analyzer to a capture |
| `saleae.export_data_table` | Export analyzer results to CSV |
| `saleae.export_raw_csv` | Export raw digital/analog samples to CSV |

### Convenience — one-call reads

| Tool | Description |
|------|-------------|
| `saleae.read_digital` | Sample digital channels, return `high`/`low` state |
| `saleae.read_analog` | Sample analog channels, return `min`/`max`/`mean` voltage |
| `saleae.read_mixed` | Sample digital + analog simultaneously |

### Signal measurements

| Tool | Description |
|------|-------------|
| `saleae.measure_frequency` | Measure frequency (Hz), period, and duty cycle |
| `saleae.measure_pulse_width` | Measure min/max/mean pulse width |
| `saleae.count_edges` | Count rising and falling edges over a window |

### Protocol decoders — one-call

| Tool | Description |
|------|-------------|
| `saleae.decode_uart` | Capture + decode UART/async-serial frames |
| `saleae.decode_i2c` | Capture + decode I2C frames |
| `saleae.decode_spi` | Capture + decode SPI frames |

### Triggered & conditional

| Tool | Description |
|------|-------------|
| `saleae.read_on_trigger` | Start capture on a digital edge, return states after event |
| `saleae.wait_for_voltage` | Poll analog until voltage crosses a threshold |
| `saleae.wait_for_signal` | Poll digital until it reaches `high` or `low` |

---

## Usage examples

### Read analog channel 0 for 5 seconds

```
saleae.connect()
saleae.read_analog(channels=[0], duration_seconds=5)
```

Returns: `{ "channels": { "0": { "min_v": 0.024, "max_v": 0.028, "mean_v": 0.025, "samples": 3167511 } } }`

### Measure signal frequency

```
saleae.measure_frequency(channel=0, duration_seconds=0.5)
```

Returns: `{ "frequency_hz": 1000.0, "period_seconds": 0.001, "duty_cycle_pct": 50.0, ... }`

### Decode UART at 115200 baud

```
saleae.decode_uart(channel=0, baud_rate=115200, duration_seconds=2.0)
```

### Decode I2C

```
saleae.decode_i2c(sda_channel=0, scl_channel=1, duration_seconds=1.0)
```

### Decode SPI

```
saleae.decode_spi(mosi_channel=0, miso_channel=1, clock_channel=2, enable_channel=3)
```

### Wait for a voltage threshold

```
saleae.wait_for_voltage(channel=0, threshold_v=3.0, condition="above", timeout_seconds=10)
```

### Capture on a rising edge trigger

```
saleae.read_on_trigger(channels=[1, 2], trigger_channel=0, trigger_type="rising", after_trigger_seconds=0.5)
```

### Manual capture workflow

```
saleae.connect()
saleae.start_capture({ "device_configuration": { "enabled_digital_channels": [0,1], "digital_sample_rate": 10000000 }, "capture_configuration": { "capture_mode": { "kind": "timed", "duration_seconds": 1.0 } } })
# → { "capture_id": "..." }

saleae.wait_capture(capture_id="...")
saleae.add_analyzer(capture_id="...", analyzer_name="I2C", settings={"SDA": 0, "SCL": 1})
saleae.export_data_table(capture_id="...", analyzer_ids=["..."], path="/tmp/result.csv")
saleae.close_capture(capture_id="...")
```

### `saleae.start_capture` payload reference

```json
{
  "device_id": "F4241",
  "device_configuration": {
    "enabled_digital_channels": [0, 1, 2, 3],
    "enabled_analog_channels": [],
    "digital_sample_rate": 10000000,
    "analog_sample_rate": null,
    "digital_threshold_volts": 1.2,
    "glitch_filters": [
      { "channel_index": 0, "pulse_width_seconds": 0.000001 }
    ]
  },
  "capture_configuration": {
    "capture_mode": {
      "kind": "timed",
      "duration_seconds": 1.0
    }
  }
}
```

Supported capture modes: `manual`, `timed`, `digital_trigger`.

---

## Architecture

Two-file Python package (`src/saleae_mcp/`):

- **`server.py`** — FastMCP tool definitions. Each `@mcp.tool` validates inputs and delegates to `SaleaeAdapter`.
- **`adapter.py`** — `SaleaeAdapter` wraps the `saleae.automation` SDK, manages capture/analyzer state, and implements all convenience methods.

All tools return `{"ok": true, "data": ...}` on success or `{"ok": false, "error": {"type": ..., "message": ...}}` on failure.

## Known limitations

- API compatibility is best-effort across Saleae automation library versions. The adapter uses `_call_first()` to try multiple method names for cross-version support.
- `decode_uart` uses the analyzer named `"Async Serial"` (Logic 2 naming). Older Logic versions may differ.
- `wait_for_voltage` and `wait_for_signal` block until the condition is met or timeout expires.
