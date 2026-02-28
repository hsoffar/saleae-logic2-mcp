from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from saleae import automation

from saleae_mcp.adapter import SaleaeAdapter


mcp = FastMCP("saleae-mcp-server")
adapter = SaleaeAdapter()


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _err(exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
        },
    }


def _capture_mode(mode: dict[str, Any] | None) -> Any:
    if not mode:
        return None
    kind = mode.get("kind", "manual")
    if kind == "manual":
        return automation.ManualCaptureMode()
    if kind == "timed":
        duration_seconds = float(mode["duration_seconds"])
        return automation.TimedCaptureMode(duration_seconds=duration_seconds)
    if kind == "digital_trigger":
        trigger_type = mode["trigger_type"]
        if isinstance(trigger_type, str):
            trigger_type = getattr(automation.DigitalTriggerType, trigger_type.upper())
        channel = int(mode["channel"])
        linked_channels = mode.get("linked_channels", [])
        after_trigger_seconds = float(mode.get("after_trigger_seconds", 0))
        return automation.DigitalTriggerCaptureMode(
            trigger_type=trigger_type,
            trigger_channel_index=channel,
            linked_channels=linked_channels,
            trim_data_seconds=after_trigger_seconds,
        )
    raise ValueError(f"Unsupported capture mode kind: {kind}")


def _build_start_capture_kwargs(payload: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}

    for key in ["device_id"]:
        if key in payload and payload[key] is not None:
            kwargs[key] = payload[key]

    device_cfg = payload.get("device_configuration")
    if not device_cfg:
        raise ValueError("payload.device_configuration is required")
    if device_cfg:
        glitch_filters: list[Any] | None = None
        raw_glitch_filters = device_cfg.get("glitch_filters")
        if raw_glitch_filters is not None:
            glitch_filters = [
                automation.GlitchFilterEntry(
                    channel_index=int(item["channel_index"]),
                    pulse_width_seconds=float(item["pulse_width_seconds"]),
                )
                for item in raw_glitch_filters
            ]
        kwargs["device_configuration"] = automation.LogicDeviceConfiguration(
            enabled_digital_channels=device_cfg.get("enabled_digital_channels") or [],
            enabled_analog_channels=device_cfg.get("enabled_analog_channels") or [],
            digital_sample_rate=device_cfg.get("digital_sample_rate"),
            analog_sample_rate=device_cfg.get("analog_sample_rate"),
            digital_threshold_volts=device_cfg.get("digital_threshold_volts"),
            glitch_filters=glitch_filters or [],
        )

    capture_cfg = payload.get("capture_configuration")
    if capture_cfg:
        mode = _capture_mode(capture_cfg.get("capture_mode"))
        kwargs["capture_configuration"] = automation.CaptureConfiguration(capture_mode=mode)

    return kwargs


@mcp.tool(name="saleae.connect")
def saleae_connect(
    host: str = os.environ.get("SALEAE_HOST", "127.0.0.1"),
    port: int = int(os.environ.get("SALEAE_PORT", "10430")),
    timeout_seconds: float = 5.0,
    launch_if_needed: bool = False,
    logic2_binary: str | None = None,
) -> dict[str, Any]:
    try:
        return _ok(
            adapter.connect(
                host=host,
                port=port,
                timeout_seconds=timeout_seconds,
                launch_if_needed=launch_if_needed,
                logic2_binary=logic2_binary,
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.disconnect")
def saleae_disconnect() -> dict[str, Any]:
    try:
        return _ok(adapter.disconnect())
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.status")
def saleae_status() -> dict[str, Any]:
    try:
        return _ok(adapter.status())
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.list_devices")
def saleae_list_devices(include_simulation_devices: bool = True) -> dict[str, Any]:
    try:
        return _ok(adapter.list_devices(include_simulation_devices=include_simulation_devices))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.start_capture")
def saleae_start_capture(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        kwargs = _build_start_capture_kwargs(payload)
        return _ok(adapter.start_capture(**kwargs))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.wait_capture")
def saleae_wait_capture(capture_id: str) -> dict[str, Any]:
    try:
        return _ok(adapter.wait_capture(capture_id))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.stop_capture")
def saleae_stop_capture(capture_id: str) -> dict[str, Any]:
    try:
        return _ok(adapter.stop_capture(capture_id))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.close_capture")
def saleae_close_capture(capture_id: str) -> dict[str, Any]:
    try:
        return _ok(adapter.close_capture(capture_id))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.save_capture")
def saleae_save_capture(capture_id: str, path: str) -> dict[str, Any]:
    try:
        return _ok(adapter.save_capture(capture_id, path))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.load_capture")
def saleae_load_capture(path: str) -> dict[str, Any]:
    try:
        return _ok(adapter.load_capture(path))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.add_analyzer")
def saleae_add_analyzer(
    capture_id: str,
    analyzer_name: str,
    label: str | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        return _ok(
            adapter.add_analyzer(
                capture_id=capture_id,
                analyzer_name=analyzer_name,
                label=label,
                settings=settings,
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.export_data_table")
def saleae_export_data_table(
    capture_id: str,
    path: str,
    analyzer_ids: list[str],
    columns: list[str] | None = None,
    query: str | None = None,
    query_columns: list[str] | None = None,
    iso8601_timestamp: bool = False,
) -> dict[str, Any]:
    try:
        return _ok(
            adapter.export_data_table(
                capture_id=capture_id,
                path=path,
                analyzer_ids=analyzer_ids,
                columns=columns,
                query=query,
                query_columns=query_columns,
                iso8601_timestamp=iso8601_timestamp,
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.read_analog")
def saleae_read_analog(
    channels: list[int],
    device_id: str | None = None,
    sample_rate: int = 625_000,
    duration_seconds: float = 0.1,
) -> dict[str, Any]:
    """Sample analog channels and return min/max/mean voltage in one call."""
    try:
        return _ok(
            adapter.read_analog(
                channels=channels,
                device_id=device_id,
                sample_rate=sample_rate,
                duration_seconds=duration_seconds,
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.read_digital")
def saleae_read_digital(
    channels: list[int],
    device_id: str | None = None,
    sample_rate: int = 1_000_000,
    duration_seconds: float = 0.01,
) -> dict[str, Any]:
    """Sample digital channels and return their current state (high/low) in one call."""
    try:
        return _ok(
            adapter.read_digital(
                channels=channels,
                device_id=device_id,
                sample_rate=sample_rate,
                duration_seconds=duration_seconds,
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.export_raw_csv")
def saleae_export_raw_csv(
    capture_id: str,
    path: str,
    digital_channels: list[int] | None = None,
    analog_channels: list[int] | None = None,
) -> dict[str, Any]:
    try:
        return _ok(
            adapter.export_raw_csv(
                capture_id=capture_id,
                path=path,
                digital_channels=digital_channels,
                analog_channels=analog_channels,
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.read_mixed")
def saleae_read_mixed(
    digital_channels: list[int],
    analog_channels: list[int],
    device_id: str | None = None,
    digital_sample_rate: int = 10_000_000,
    analog_sample_rate: int = 625_000,
    duration_seconds: float = 0.1,
) -> dict[str, Any]:
    """Capture digital and analog channels simultaneously, returning states and voltage stats."""
    try:
        return _ok(adapter.read_mixed(
            digital_channels=digital_channels,
            analog_channels=analog_channels,
            device_id=device_id,
            digital_sample_rate=digital_sample_rate,
            analog_sample_rate=analog_sample_rate,
            duration_seconds=duration_seconds,
        ))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.measure_frequency")
def saleae_measure_frequency(
    channel: int,
    device_id: str | None = None,
    sample_rate: int = 4_000_000,
    duration_seconds: float = 0.25,
) -> dict[str, Any]:
    """Measure frequency, period, and duty cycle of a digital signal."""
    try:
        return _ok(adapter.measure_frequency(
            channel=channel, device_id=device_id,
            sample_rate=sample_rate, duration_seconds=duration_seconds,
        ))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.measure_pulse_width")
def saleae_measure_pulse_width(
    channel: int,
    device_id: str | None = None,
    sample_rate: int = 4_000_000,
    duration_seconds: float = 0.25,
) -> dict[str, Any]:
    """Measure min/max/mean pulse width (high time) of a digital signal."""
    try:
        return _ok(adapter.measure_pulse_width(
            channel=channel, device_id=device_id,
            sample_rate=sample_rate, duration_seconds=duration_seconds,
        ))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.count_edges")
def saleae_count_edges(
    channel: int,
    device_id: str | None = None,
    sample_rate: int = 4_000_000,
    duration_seconds: float = 1.0,
) -> dict[str, Any]:
    """Count rising and falling edges on a digital channel over a capture window."""
    try:
        return _ok(adapter.count_edges(
            channel=channel, device_id=device_id,
            sample_rate=sample_rate, duration_seconds=duration_seconds,
        ))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.decode_uart")
def saleae_decode_uart(
    channel: int,
    baud_rate: int = 9600,
    device_id: str | None = None,
    sample_rate: int = 4_000_000,
    duration_seconds: float = 1.0,
) -> dict[str, Any]:
    """Capture and decode UART/async serial frames in one call."""
    try:
        return _ok(adapter.decode_uart(
            channel=channel, baud_rate=baud_rate, device_id=device_id,
            sample_rate=sample_rate, duration_seconds=duration_seconds,
        ))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.decode_i2c")
def saleae_decode_i2c(
    sda_channel: int,
    scl_channel: int,
    device_id: str | None = None,
    sample_rate: int = 4_000_000,
    duration_seconds: float = 1.0,
) -> dict[str, Any]:
    """Capture and decode I2C frames in one call."""
    try:
        return _ok(adapter.decode_i2c(
            sda_channel=sda_channel, scl_channel=scl_channel,
            device_id=device_id, sample_rate=sample_rate, duration_seconds=duration_seconds,
        ))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.decode_spi")
def saleae_decode_spi(
    mosi_channel: int,
    miso_channel: int,
    clock_channel: int,
    enable_channel: int | None = None,
    bits_per_transfer: int = 8,
    device_id: str | None = None,
    sample_rate: int = 10_000_000,
    duration_seconds: float = 1.0,
) -> dict[str, Any]:
    """Capture and decode SPI frames in one call."""
    try:
        return _ok(adapter.decode_spi(
            mosi_channel=mosi_channel, miso_channel=miso_channel,
            clock_channel=clock_channel, enable_channel=enable_channel,
            bits_per_transfer=bits_per_transfer, device_id=device_id,
            sample_rate=sample_rate, duration_seconds=duration_seconds,
        ))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.read_on_trigger")
def saleae_read_on_trigger(
    channels: list[int],
    trigger_channel: int,
    trigger_type: str = "rising",
    after_trigger_seconds: float = 1.0,
    device_id: str | None = None,
    sample_rate: int = 10_000_000,
) -> dict[str, Any]:
    """Start capture on a digital trigger edge, then return channel states after the event."""
    try:
        return _ok(adapter.read_on_trigger(
            channels=channels, trigger_channel=trigger_channel,
            trigger_type=trigger_type, after_trigger_seconds=after_trigger_seconds,
            device_id=device_id, sample_rate=sample_rate,
        ))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.wait_for_voltage")
def saleae_wait_for_voltage(
    channel: int,
    threshold_v: float,
    condition: str = "above",
    device_id: str | None = None,
    sample_rate: int = 625_000,
    poll_duration: float = 0.1,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Poll an analog channel until its voltage goes above or below a threshold."""
    try:
        return _ok(adapter.wait_for_voltage(
            channel=channel, threshold_v=threshold_v, condition=condition,
            device_id=device_id, sample_rate=sample_rate,
            poll_duration=poll_duration, timeout_seconds=timeout_seconds,
        ))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.wait_for_signal")
def saleae_wait_for_signal(
    channel: int,
    target_state: str = "high",
    device_id: str | None = None,
    sample_rate: int = 1_000_000,
    poll_duration: float = 0.01,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Poll a digital channel until it reaches the target state (high or low)."""
    try:
        return _ok(adapter.wait_for_signal(
            channel=channel, target_state=target_state, device_id=device_id,
            sample_rate=sample_rate, poll_duration=poll_duration,
            timeout_seconds=timeout_seconds,
        ))
    except Exception as exc:
        return _err(exc)


@mcp.tool(name="saleae.get_device_info")
def saleae_get_device_info(device_id: str | None = None) -> dict[str, Any]:
    """Return info about connected devices. Pass device_id to get info for a specific device."""
    try:
        return _ok(adapter.get_device_info(device_id=device_id))
    except Exception as exc:
        return _err(exc)


def main() -> None:
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
