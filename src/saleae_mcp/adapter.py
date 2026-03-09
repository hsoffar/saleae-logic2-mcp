from __future__ import annotations

import csv
import os
import tempfile
import uuid
from dataclasses import dataclass
from typing import Any

from saleae import automation


def _call_first(obj: Any, method_names: list[str], /, *args: Any, **kwargs: Any) -> Any:
    for name in method_names:
        fn = getattr(obj, name, None)
        if callable(fn):
            return fn(*args, **kwargs)
    available = ", ".join(sorted(x for x in dir(obj) if not x.startswith("_")))
    raise AttributeError(f"None of {method_names} exist on {type(obj).__name__}. Available: {available}")


@dataclass
class CaptureRef:
    id: str
    capture: Any


class SaleaeAdapter:
    def __init__(self) -> None:
        self._manager: Any | None = None
        self._captures: dict[str, CaptureRef] = {}
        self._analyzers: dict[str, dict[str, Any]] = {}

    @property
    def is_connected(self) -> bool:
        return self._manager is not None

    def connect(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 10430,
        timeout_seconds: float = 5.0,
        launch_if_needed: bool = False,
        logic2_binary: str | None = None,
    ) -> dict[str, Any]:
        if self._manager is not None:
            return self.status()

        if launch_if_needed:
            kwargs: dict[str, Any] = {
                "port": port,
            }
            if logic2_binary:
                kwargs["application_path"] = logic2_binary
            self._manager = _call_first(
                automation.Manager,
                ["launch"],
                **kwargs,
            )
        else:
            self._manager = _call_first(
                automation.Manager,
                ["connect"],
                address=host,
                port=port,
                connect_timeout_seconds=timeout_seconds,
            )

        return self.status()

    def disconnect(self) -> dict[str, Any]:
        if self._manager is None:
            return {"connected": False, "active_captures": 0}

        _call_first(self._manager, ["close", "disconnect"])
        self._manager = None
        self._captures.clear()
        self._analyzers.clear()
        return {"connected": False, "active_captures": 0}

    def status(self) -> dict[str, Any]:
        app_info: Any = None
        if self._manager is not None:
            app_info = _call_first(self._manager, ["get_app_info"])
        return {
            "connected": self._manager is not None,
            "active_captures": len(self._captures),
            "app_info": self._to_dict(app_info),
        }

    def list_devices(self, include_simulation_devices: bool = False) -> list[dict[str, Any]]:
        self._require_manager()
        devices = _call_first(
            self._manager,
            ["get_devices"],
            include_simulation_devices=include_simulation_devices,
        )
        return [self._to_dict(d) for d in devices]

    def start_capture(self, **kwargs: Any) -> dict[str, Any]:
        self._require_manager()
        capture = _call_first(self._manager, ["start_capture"], **kwargs)
        capture_id = str(uuid.uuid4())
        self._captures[capture_id] = CaptureRef(id=capture_id, capture=capture)
        self._analyzers[capture_id] = {}
        return {"capture_id": capture_id}

    def wait_capture(self, capture_id: str) -> dict[str, Any]:
        capture = self._require_capture(capture_id)
        _call_first(capture, ["wait", "wait_for_completion"])
        return {"capture_id": capture_id, "state": "complete"}

    def stop_capture(self, capture_id: str) -> dict[str, Any]:
        capture = self._require_capture(capture_id)
        _call_first(capture, ["stop"])
        return {"capture_id": capture_id, "state": "stopped"}

    def close_capture(self, capture_id: str) -> dict[str, Any]:
        capture = self._require_capture(capture_id)
        _call_first(capture, ["close"])
        self._captures.pop(capture_id, None)
        self._analyzers.pop(capture_id, None)
        return {"capture_id": capture_id, "state": "closed"}

    def save_capture(self, capture_id: str, path: str) -> dict[str, Any]:
        capture = self._require_capture(capture_id)
        out_path = os.path.abspath(path)
        _call_first(capture, ["save_capture", "save"], out_path)
        return {"capture_id": capture_id, "path": out_path}

    def load_capture(self, path: str) -> dict[str, Any]:
        self._require_manager()
        in_path = os.path.abspath(path)
        capture = _call_first(self._manager, ["load_capture"], in_path)
        capture_id = str(uuid.uuid4())
        self._captures[capture_id] = CaptureRef(id=capture_id, capture=capture)
        self._analyzers[capture_id] = {}
        return {"capture_id": capture_id, "path": in_path}

    def add_analyzer(
        self,
        capture_id: str,
        analyzer_name: str,
        *,
        label: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        capture = self._require_capture(capture_id)
        kwargs: dict[str, Any] = {"settings": settings or {}}
        if label:
            kwargs["label"] = label
        analyzer = _call_first(capture, ["add_analyzer"], analyzer_name, **kwargs)
        analyzer_id = str(uuid.uuid4())
        self._analyzers.setdefault(capture_id, {})[analyzer_id] = analyzer
        return {
            "capture_id": capture_id,
            "analyzer_id": analyzer_id,
            "analyzer": self._to_dict(analyzer),
        }

    def export_data_table(
        self,
        capture_id: str,
        path: str,
        *,
        analyzer_ids: list[str],
        columns: list[str] | None = None,
        query: str | None = None,
        query_columns: list[str] | None = None,
        iso8601_timestamp: bool = False,
    ) -> dict[str, Any]:
        capture = self._require_capture(capture_id)
        out_path = os.path.abspath(path)
        analyzers = [self._require_analyzer(capture_id, a_id) for a_id in analyzer_ids]
        kwargs: dict[str, Any] = {"filepath": out_path, "analyzers": analyzers}
        if columns:
            kwargs["columns"] = columns
        if query is not None:
            kwargs["filter"] = automation.DataTableFilter(
                columns=query_columns or [],
                query=query,
            )
        kwargs["iso8601_timestamp"] = iso8601_timestamp
        _call_first(
            capture,
            ["export_data_table", "export_analyzer_table"],
            **kwargs,
        )
        return {"capture_id": capture_id, "path": out_path}

    def export_raw_csv(
        self,
        capture_id: str,
        path: str,
        *,
        digital_channels: list[int] | None = None,
        analog_channels: list[int] | None = None,
    ) -> dict[str, Any]:
        capture = self._require_capture(capture_id)
        out_path = os.path.abspath(path)
        kwargs: dict[str, Any] = {"directory": out_path}
        if digital_channels is not None:
            kwargs["digital_channels"] = digital_channels
        if analog_channels is not None:
            kwargs["analog_channels"] = analog_channels
        _call_first(capture, ["export_raw_data_csv"], **kwargs)
        return {"capture_id": capture_id, "path": out_path}

    def read_analog(
        self,
        channels: list[int],
        device_id: str | None = None,
        sample_rate: int = 625_000,
        duration_seconds: float = 0.1,
    ) -> dict[str, Any]:
        self._require_manager()
        cfg_kwargs: dict[str, Any] = {
            "device_configuration": automation.LogicDeviceConfiguration(
                enabled_digital_channels=[],
                enabled_analog_channels=channels,
                analog_sample_rate=sample_rate,
                glitch_filters=[],
            ),
            "capture_configuration": automation.CaptureConfiguration(
                capture_mode=automation.TimedCaptureMode(duration_seconds=duration_seconds)
            ),
        }
        if device_id is not None:
            cfg_kwargs["device_id"] = device_id

        capture = _call_first(self._manager, ["start_capture"], **cfg_kwargs)
        try:
            _call_first(capture, ["wait", "wait_for_completion"])
            with tempfile.TemporaryDirectory() as tmp:
                _call_first(capture, ["export_raw_data_csv"], directory=tmp, analog_channels=channels)
                csv_path = os.path.join(tmp, "analog.csv")
                with open(csv_path, newline="") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
        finally:
            _call_first(capture, ["close"])

        if not rows:
            raise RuntimeError("No samples captured — check device connection and channel config")

        result: dict[str, Any] = {}
        for ch in channels:
            key = f"Channel {ch}"
            values = [float(row[key]) for row in rows if key in row]
            if not values:
                raise RuntimeError(f"Column '{key}' not found in CSV.")
            result[ch] = {
                "min_v": round(min(values), 6),
                "max_v": round(max(values), 6),
                "mean_v": round(sum(values) / len(values), 6),
                "samples": len(values),
            }

        return {"channels": result}

    def read_digital(
        self,
        channels: list[int],
        device_id: str | None = None,
        sample_rate: int = 1_000_000,
        duration_seconds: float = 0.01,
    ) -> dict[str, Any]:
        self._require_manager()
        cfg_kwargs: dict[str, Any] = {
            "device_configuration": automation.LogicDeviceConfiguration(
                enabled_digital_channels=channels,
                enabled_analog_channels=[],
                digital_sample_rate=sample_rate,
                glitch_filters=[],
            ),
            "capture_configuration": automation.CaptureConfiguration(
                capture_mode=automation.TimedCaptureMode(duration_seconds=duration_seconds)
            ),
        }
        if device_id is not None:
            cfg_kwargs["device_id"] = device_id

        capture = _call_first(self._manager, ["start_capture"], **cfg_kwargs)
        try:
            _call_first(capture, ["wait", "wait_for_completion"])
            with tempfile.TemporaryDirectory() as tmp:
                _call_first(capture, ["export_raw_data_csv"], directory=tmp, digital_channels=channels)
                csv_path = os.path.join(tmp, "digital.csv")
                with open(csv_path, newline="") as f:
                    reader = csv.DictReader(f)
                    first_row = next(reader, None)
        finally:
            _call_first(capture, ["close"])

        if first_row is None:
            raise RuntimeError("No samples captured — check device connection and channel config")

        states: dict[str, Any] = {}
        for ch in channels:
            key = f"Channel {ch}"
            raw = first_row.get(key)
            if raw is None:
                raise RuntimeError(f"Column '{key}' not found in CSV. Available: {list(first_row.keys())}")
            val = int(raw)
            states[ch] = {"value": val, "state": "high" if val else "low"}

        return {"channels": states}

    def read_mixed(
        self,
        digital_channels: list[int],
        analog_channels: list[int],
        device_id: str | None = None,
        digital_sample_rate: int = 10_000_000,
        analog_sample_rate: int = 625_000,
        duration_seconds: float = 0.1,
    ) -> dict[str, Any]:
        self._require_manager()
        cfg_kwargs: dict[str, Any] = {
            "device_configuration": automation.LogicDeviceConfiguration(
                enabled_digital_channels=digital_channels,
                enabled_analog_channels=analog_channels,
                digital_sample_rate=digital_sample_rate,
                analog_sample_rate=analog_sample_rate,
                glitch_filters=[],
            ),
            "capture_configuration": automation.CaptureConfiguration(
                capture_mode=automation.TimedCaptureMode(duration_seconds=duration_seconds)
            ),
        }
        if device_id is not None:
            cfg_kwargs["device_id"] = device_id

        capture = _call_first(self._manager, ["start_capture"], **cfg_kwargs)
        try:
            _call_first(capture, ["wait", "wait_for_completion"])
            with tempfile.TemporaryDirectory() as tmp:
                _call_first(
                    capture, ["export_raw_data_csv"],
                    directory=tmp,
                    digital_channels=digital_channels,
                    analog_channels=analog_channels,
                )
                digital_result: dict[str, Any] = {}
                dig_path = os.path.join(tmp, "digital.csv")
                if os.path.exists(dig_path):
                    with open(dig_path, newline="") as f:
                        first_row = next(csv.DictReader(f), None)
                    if first_row:
                        for ch in digital_channels:
                            key = f"Channel {ch}"
                            raw = first_row.get(key)
                            if raw is not None:
                                val = int(raw)
                                digital_result[ch] = {"value": val, "state": "high" if val else "low"}

                analog_result: dict[str, Any] = {}
                ana_path = os.path.join(tmp, "analog.csv")
                if os.path.exists(ana_path):
                    with open(ana_path, newline="") as f:
                        rows = list(csv.DictReader(f))
                    for ch in analog_channels:
                        key = f"Channel {ch}"
                        values = [float(r[key]) for r in rows if key in r]
                        if values:
                            analog_result[ch] = {
                                "min_v": round(min(values), 6),
                                "max_v": round(max(values), 6),
                                "mean_v": round(sum(values) / len(values), 6),
                                "samples": len(values),
                            }
        finally:
            _call_first(capture, ["close"])

        return {"digital": digital_result, "analog": analog_result}

    def _parse_digital_edges(
        self,
        csv_path: str,
        channel: int,
    ) -> tuple[list[float], list[float], float, float]:
        """Stream digital CSV and return (rising_times, falling_times, high_time, total_time)."""
        key = f"Channel {channel}"
        rising: list[float] = []
        falling: list[float] = []
        high_time = 0.0
        total_time = 0.0
        prev_t: float | None = None
        prev_v: int | None = None

        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                t = float(row["Time [s]"])
                v = int(row[key])
                if prev_t is not None and prev_v is not None:
                    dt = t - prev_t
                    total_time += dt
                    if prev_v == 1:
                        high_time += dt
                    if prev_v == 0 and v == 1:
                        rising.append(t)
                    elif prev_v == 1 and v == 0:
                        falling.append(t)
                prev_t = t
                prev_v = v

        return rising, falling, high_time, total_time

    def _start_timed_digital_capture(
        self,
        channels: list[int],
        device_id: str | None,
        sample_rate: int,
        duration_seconds: float,
    ) -> Any:
        cfg_kwargs: dict[str, Any] = {
            "device_configuration": automation.LogicDeviceConfiguration(
                enabled_digital_channels=channels,
                enabled_analog_channels=[],
                digital_sample_rate=sample_rate,
                glitch_filters=[],
            ),
            "capture_configuration": automation.CaptureConfiguration(
                capture_mode=automation.TimedCaptureMode(duration_seconds=duration_seconds)
            ),
        }
        if device_id is not None:
            cfg_kwargs["device_id"] = device_id
        return _call_first(self._manager, ["start_capture"], **cfg_kwargs)

    def measure_frequency(
        self,
        channel: int,
        device_id: str | None = None,
        sample_rate: int = 4_000_000,
        duration_seconds: float = 0.25,
    ) -> dict[str, Any]:
        self._require_manager()
        capture = self._start_timed_digital_capture([channel], device_id, sample_rate, duration_seconds)
        try:
            _call_first(capture, ["wait", "wait_for_completion"])
            with tempfile.TemporaryDirectory() as tmp:
                _call_first(capture, ["export_raw_data_csv"], directory=tmp, digital_channels=[channel])
                rising, falling, high_time, total_time = self._parse_digital_edges(
                    os.path.join(tmp, "digital.csv"), channel
                )
        finally:
            _call_first(capture, ["close"])

        if len(rising) < 2:
            raise RuntimeError(
                f"Not enough rising edges detected ({len(rising)}) — check signal and increase duration"
            )

        periods = [rising[i + 1] - rising[i] for i in range(len(rising) - 1)]
        mean_period = sum(periods) / len(periods)
        return {
            "channel": channel,
            "frequency_hz": round(1.0 / mean_period, 4),
            "period_seconds": round(mean_period, 9),
            "duty_cycle_pct": round(high_time / total_time * 100, 2) if total_time > 0 else 0.0,
            "rising_edges": len(rising),
            "falling_edges": len(falling),
        }

    def measure_pulse_width(
        self,
        channel: int,
        device_id: str | None = None,
        sample_rate: int = 4_000_000,
        duration_seconds: float = 0.25,
    ) -> dict[str, Any]:
        self._require_manager()
        capture = self._start_timed_digital_capture([channel], device_id, sample_rate, duration_seconds)
        try:
            _call_first(capture, ["wait", "wait_for_completion"])
            with tempfile.TemporaryDirectory() as tmp:
                _call_first(capture, ["export_raw_data_csv"], directory=tmp, digital_channels=[channel])
                rising, falling, _, _ = self._parse_digital_edges(
                    os.path.join(tmp, "digital.csv"), channel
                )
        finally:
            _call_first(capture, ["close"])

        pulse_widths: list[float] = []
        fi = 0
        for r_t in rising:
            while fi < len(falling) and falling[fi] <= r_t:
                fi += 1
            if fi < len(falling):
                pulse_widths.append(falling[fi] - r_t)
                fi += 1

        if not pulse_widths:
            raise RuntimeError("No complete pulses found — check signal and increase duration")

        return {
            "channel": channel,
            "pulse_count": len(pulse_widths),
            "min_seconds": round(min(pulse_widths), 9),
            "max_seconds": round(max(pulse_widths), 9),
            "mean_seconds": round(sum(pulse_widths) / len(pulse_widths), 9),
        }

    def count_edges(
        self,
        channel: int,
        device_id: str | None = None,
        sample_rate: int = 4_000_000,
        duration_seconds: float = 1.0,
    ) -> dict[str, Any]:
        self._require_manager()
        capture = self._start_timed_digital_capture([channel], device_id, sample_rate, duration_seconds)
        try:
            _call_first(capture, ["wait", "wait_for_completion"])
            with tempfile.TemporaryDirectory() as tmp:
                _call_first(capture, ["export_raw_data_csv"], directory=tmp, digital_channels=[channel])
                rising, falling, _, total_time = self._parse_digital_edges(
                    os.path.join(tmp, "digital.csv"), channel
                )
        finally:
            _call_first(capture, ["close"])

        return {
            "channel": channel,
            "rising_edges": len(rising),
            "falling_edges": len(falling),
            "total_edges": len(rising) + len(falling),
            "duration_seconds": round(total_time, 6),
        }

    def _decode_protocol(
        self,
        channels: list[int],
        analyzer_name: str,
        analyzer_settings: dict[str, Any],
        device_id: str | None,
        sample_rate: int,
        duration_seconds: float,
    ) -> list[dict[str, Any]]:
        self._require_manager()
        capture = self._start_timed_digital_capture(channels, device_id, sample_rate, duration_seconds)
        try:
            _call_first(capture, ["wait", "wait_for_completion"])
            analyzer = _call_first(capture, ["add_analyzer"], analyzer_name, settings=analyzer_settings)
            with tempfile.TemporaryDirectory() as tmp:
                table_path = os.path.join(tmp, "decoded.csv")
                _call_first(
                    capture,
                    ["export_data_table", "export_analyzer_table"],
                    filepath=table_path,
                    analyzers=[analyzer],
                )
                if not os.path.exists(table_path):
                    return []
                with open(table_path, newline="") as f:
                    return list(csv.DictReader(f))
        finally:
            _call_first(capture, ["close"])

    def decode_uart(
        self,
        channel: int,
        baud_rate: int = 9600,
        device_id: str | None = None,
        sample_rate: int = 4_000_000,
        duration_seconds: float = 1.0,
    ) -> dict[str, Any]:
        rows = self._decode_protocol(
            channels=[channel],
            analyzer_name="Async Serial",
            analyzer_settings={"Input Channel": channel, "Bit Rate": baud_rate},
            device_id=device_id,
            sample_rate=sample_rate,
            duration_seconds=duration_seconds,
        )
        return {"channel": channel, "baud_rate": baud_rate, "frame_count": len(rows), "frames": rows}

    def decode_i2c(
        self,
        sda_channel: int,
        scl_channel: int,
        device_id: str | None = None,
        sample_rate: int = 4_000_000,
        duration_seconds: float = 1.0,
    ) -> dict[str, Any]:
        rows = self._decode_protocol(
            channels=[sda_channel, scl_channel],
            analyzer_name="I2C",
            analyzer_settings={"SDA": sda_channel, "SCL": scl_channel},
            device_id=device_id,
            sample_rate=sample_rate,
            duration_seconds=duration_seconds,
        )
        return {"sda_channel": sda_channel, "scl_channel": scl_channel, "frame_count": len(rows), "frames": rows}

    def decode_spi(
        self,
        mosi_channel: int,
        miso_channel: int,
        clock_channel: int,
        enable_channel: int | None = None,
        bits_per_transfer: int = 8,
        device_id: str | None = None,
        sample_rate: int = 10_000_000,
        duration_seconds: float = 1.0,
    ) -> dict[str, Any]:
        channels = list(dict.fromkeys([mosi_channel, miso_channel, clock_channel]))
        bits_label = f"{bits_per_transfer} Bits per Transfer (Standard)" if bits_per_transfer == 8 else f"{bits_per_transfer} Bits per Transfer"
        settings: dict[str, Any] = {
            "MOSI": mosi_channel,
            "MISO": miso_channel,
            "Clock": clock_channel,
            "Bits per Transfer": bits_label,
        }
        if enable_channel is not None:
            channels.append(enable_channel)
            settings["Enable"] = enable_channel
        rows = self._decode_protocol(
            channels=channels,
            analyzer_name="SPI",
            analyzer_settings=settings,
            device_id=device_id,
            sample_rate=sample_rate,
            duration_seconds=duration_seconds,
        )
        return {
            "mosi_channel": mosi_channel,
            "miso_channel": miso_channel,
            "clock_channel": clock_channel,
            "enable_channel": enable_channel,
            "frame_count": len(rows),
            "frames": rows,
        }

    def read_on_trigger(
        self,
        channels: list[int],
        trigger_channel: int,
        trigger_type: str = "rising",
        after_trigger_seconds: float = 1.0,
        device_id: str | None = None,
        sample_rate: int = 10_000_000,
    ) -> dict[str, Any]:
        self._require_manager()
        trigger_enum = getattr(automation.DigitalTriggerType, trigger_type.upper(), None)
        if trigger_enum is None:
            raise ValueError(f"Invalid trigger_type '{trigger_type}'. Use 'rising' or 'falling'.")

        all_channels = list(dict.fromkeys([trigger_channel] + channels))
        linked = [c for c in all_channels if c != trigger_channel]
        cfg_kwargs: dict[str, Any] = {
            "device_configuration": automation.LogicDeviceConfiguration(
                enabled_digital_channels=all_channels,
                enabled_analog_channels=[],
                digital_sample_rate=sample_rate,
                glitch_filters=[],
            ),
            "capture_configuration": automation.CaptureConfiguration(
                capture_mode=automation.DigitalTriggerCaptureMode(
                    trigger_type=trigger_enum,
                    trigger_channel_index=trigger_channel,
                    linked_channels=linked,
                    trim_data_seconds=after_trigger_seconds,
                )
            ),
        }
        if device_id is not None:
            cfg_kwargs["device_id"] = device_id

        capture = _call_first(self._manager, ["start_capture"], **cfg_kwargs)
        try:
            _call_first(capture, ["wait", "wait_for_completion"])
            with tempfile.TemporaryDirectory() as tmp:
                _call_first(capture, ["export_raw_data_csv"], directory=tmp, digital_channels=all_channels)
                with open(os.path.join(tmp, "digital.csv"), newline="") as f:
                    first_row = next(csv.DictReader(f), None)
        finally:
            _call_first(capture, ["close"])

        if first_row is None:
            raise RuntimeError("No samples captured after trigger")

        states: dict[str, Any] = {}
        for ch in channels:
            key = f"Channel {ch}"
            raw = first_row.get(key)
            if raw is not None:
                val = int(raw)
                states[ch] = {"value": val, "state": "high" if val else "low"}

        return {"trigger_channel": trigger_channel, "trigger_type": trigger_type, "channels": states}

    def wait_for_voltage(
        self,
        channel: int,
        threshold_v: float,
        condition: str = "above",
        device_id: str | None = None,
        sample_rate: int = 625_000,
        poll_duration: float = 0.1,
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        import time
        if condition not in ("above", "below"):
            raise ValueError("condition must be 'above' or 'below'")
        self._require_manager()
        start = time.monotonic()
        while True:
            result = self.read_analog(
                channels=[channel], device_id=device_id,
                sample_rate=sample_rate, duration_seconds=poll_duration,
            )
            mean_v = result["channels"][channel]["mean_v"]
            met = (condition == "above" and mean_v > threshold_v) or \
                  (condition == "below" and mean_v < threshold_v)
            if met:
                return {
                    "channel": channel,
                    "voltage": mean_v,
                    "condition": condition,
                    "threshold_v": threshold_v,
                    "elapsed_seconds": round(time.monotonic() - start, 3),
                }
            if time.monotonic() - start > timeout_seconds:
                raise TimeoutError(
                    f"Channel {channel} voltage ({mean_v:.4f}V) did not go {condition} "
                    f"{threshold_v}V within {timeout_seconds}s"
                )

    def wait_for_signal(
        self,
        channel: int,
        target_state: str = "high",
        device_id: str | None = None,
        sample_rate: int = 1_000_000,
        poll_duration: float = 0.01,
        timeout_seconds: float = 10.0,
    ) -> dict[str, Any]:
        import time
        if target_state not in ("high", "low"):
            raise ValueError("target_state must be 'high' or 'low'")
        self._require_manager()
        start = time.monotonic()
        while True:
            result = self.read_digital(
                channels=[channel], device_id=device_id,
                sample_rate=sample_rate, duration_seconds=poll_duration,
            )
            state = result["channels"][channel]["state"]
            if state == target_state:
                return {
                    "channel": channel,
                    "state": state,
                    "elapsed_seconds": round(time.monotonic() - start, 3),
                }
            if time.monotonic() - start > timeout_seconds:
                raise TimeoutError(
                    f"Channel {channel} did not reach '{target_state}' within {timeout_seconds}s"
                )

    def triggered_spi_capture(
        self,
        trigger_channel: int,
        clock_channel: int,
        mosi_channel: int,
        miso_channel: int,
        enable_channel: int | None = None,
        after_trigger_seconds: float = 1.0,
        bits_per_transfer: int = 8,
        sample_rate: int = 10_000_000,
        save_dir: str = ".",
        device_id: str | None = None,
    ) -> dict[str, Any]:
        from datetime import datetime

        self._require_manager()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_dir = os.path.abspath(os.path.expanduser(save_dir))
        os.makedirs(save_dir, exist_ok=True)
        sal_path = os.path.join(save_dir, f"spi_capture_{ts}.sal")
        csv_path = os.path.join(save_dir, f"spi_decoded_{ts}.csv")

        all_channels = list(dict.fromkeys(
            [trigger_channel, clock_channel, mosi_channel, miso_channel]
            + ([enable_channel] if enable_channel is not None else [])
        ))
        cfg_kwargs: dict[str, Any] = {
            "device_configuration": automation.LogicDeviceConfiguration(
                enabled_digital_channels=all_channels,
                enabled_analog_channels=[],
                digital_sample_rate=sample_rate,
                glitch_filters=[],
            ),
            "capture_configuration": automation.CaptureConfiguration(
                capture_mode=automation.DigitalTriggerCaptureMode(
                    trigger_type=automation.DigitalTriggerType.RISING,
                    trigger_channel_index=trigger_channel,
                    linked_channels=[],
                    trim_data_seconds=after_trigger_seconds,
                )
            ),
        }
        if device_id is not None:
            cfg_kwargs["device_id"] = device_id

        capture = _call_first(self._manager, ["start_capture"], **cfg_kwargs)
        capture_id = str(uuid.uuid4())
        self._captures[capture_id] = CaptureRef(id=capture_id, capture=capture)
        self._analyzers[capture_id] = {}

        _call_first(capture, ["wait", "wait_for_completion"])

        bits_label = f"{bits_per_transfer} Bits per Transfer (Standard)" if bits_per_transfer == 8 else f"{bits_per_transfer} Bits per Transfer"
        analyzer_settings: dict[str, Any] = {
            "MOSI": mosi_channel,
            "MISO": miso_channel,
            "Clock": clock_channel,
            "Bits per Transfer": bits_label,
        }
        if enable_channel is not None:
            analyzer_settings["Enable"] = enable_channel

        analyzer = _call_first(
            capture, ["add_analyzer"], "SPI",
            settings=analyzer_settings, label="SPI",
        )
        analyzer_id = str(uuid.uuid4())
        self._analyzers[capture_id][analyzer_id] = analyzer

        _call_first(
            capture, ["export_data_table", "export_analyzer_table"],
            filepath=csv_path, analyzers=[analyzer], iso8601_timestamp=True,
        )
        _call_first(capture, ["save_capture", "save"], sal_path)

        return {
            "capture_id": capture_id,
            "analyzer_id": analyzer_id,
            "trigger_channel": trigger_channel,
            "clock_channel": clock_channel,
            "mosi_channel": mosi_channel,
            "miso_channel": miso_channel,
            "enable_channel": enable_channel,
            "sal_path": sal_path,
            "csv_path": csv_path,
            "timestamp": ts,
        }

    def get_device_info(self, device_id: str | None = None) -> dict[str, Any]:
        self._require_manager()
        devices = _call_first(self._manager, ["get_devices"], include_simulation_devices=True)
        device_list = [self._to_dict(d) for d in devices]
        if device_id is not None:
            matches = [d for d in device_list if d.get("device_id") == device_id]
            if not matches:
                raise KeyError(f"Device '{device_id}' not found")
            return matches[0]
        return {"devices": device_list}

    def _require_manager(self) -> None:
        if self._manager is None:
            raise RuntimeError("Not connected to Logic 2. Call saleae.connect first.")

    def _require_capture(self, capture_id: str) -> Any:
        ref = self._captures.get(capture_id)
        if ref is None:
            raise KeyError(f"Unknown capture_id: {capture_id}")
        return ref.capture

    def _require_analyzer(self, capture_id: str, analyzer_id: str) -> Any:
        analyzers = self._analyzers.get(capture_id, {})
        analyzer = analyzers.get(analyzer_id)
        if analyzer is None:
            raise KeyError(f"Unknown analyzer_id for capture {capture_id}: {analyzer_id}")
        return analyzer

    @staticmethod
    def _to_dict(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool, list, dict)):
            return value
        if hasattr(value, "__dict__"):
            out: dict[str, Any] = {}
            for k, v in vars(value).items():
                if k.startswith("_"):
                    continue
                out[k] = SaleaeAdapter._to_dict(v)
            return out
        try:
            return str(value)
        except Exception:
            return {"repr": repr(value)}
