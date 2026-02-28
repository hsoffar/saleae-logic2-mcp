from __future__ import annotations

import csv
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from saleae_mcp import adapter as adapter_mod


def test_call_first_uses_first_available_method():
    class Obj:
        def b(self, x):
            return x + 1

    out = adapter_mod._call_first(Obj(), ["a", "b"], 3)
    assert out == 4


def test_call_first_raises_when_methods_missing():
    with pytest.raises(AttributeError, match="None of"):
        adapter_mod._call_first(object(), ["a", "b"])


class _FakeCapture:
    def __init__(self):
        self.stopped = False
        self.closed = False
        self.waited = False
        self.export_kwargs = None
        self.added_analyzer = None

    def wait(self):
        self.waited = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True

    def add_analyzer(self, analyzer_name, **kwargs):
        self.added_analyzer = (analyzer_name, kwargs)
        return SimpleNamespace(kind=analyzer_name, label=kwargs.get("label"))

    def export_data_table(self, **kwargs):
        self.export_kwargs = kwargs

    def export_raw_data_csv(self, *, directory, digital_channels=None, analog_channels=None):
        self.export_kwargs = {
            "directory": directory,
            "digital_channels": digital_channels,
            "analog_channels": analog_channels,
        }
        os.makedirs(directory, exist_ok=True)
        csv_path = os.path.join(directory, "digital.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["Time [s]", "Channel 0", "Channel 1"])
            writer.writeheader()
            writer.writerow({"Time [s]": "0", "Channel 0": "0", "Channel 1": "1"})

    def save_capture(self, path):
        self.saved_path = path


class _FakeManager:
    def __init__(self):
        self.started_kwargs = None
        self.loaded_path = None
        self.capture = _FakeCapture()

    def get_app_info(self):
        return SimpleNamespace(app_version="x.y.z")

    def get_devices(self, include_simulation_devices=False):
        return [SimpleNamespace(device_id="D1", simulation=include_simulation_devices)]

    def start_capture(self, **kwargs):
        self.started_kwargs = kwargs
        return self.capture

    def load_capture(self, path):
        self.loaded_path = path
        return _FakeCapture()

    def close(self):
        return None


@pytest.fixture()
def fake_automation(monkeypatch: pytest.MonkeyPatch):
    manager = _FakeManager()
    launched = _FakeManager()
    calls: dict[str, object] = {}

    class _ManagerAPI:
        @staticmethod
        def connect(address, port, connect_timeout_seconds):
            calls["connect"] = {
                "address": address,
                "port": port,
                "connect_timeout_seconds": connect_timeout_seconds,
            }
            return manager

        @staticmethod
        def launch(port, application_path=None):
            calls["launch"] = {"port": port, "application_path": application_path}
            return launched

    class _LogicDeviceConfiguration:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _TimedCaptureMode:
        def __init__(self, *, duration_seconds):
            self.duration_seconds = duration_seconds

    class _CaptureConfiguration:
        def __init__(self, *, capture_mode):
            self.capture_mode = capture_mode

    class _DigitalTriggerCaptureMode:
        def __init__(
            self,
            *,
            trigger_type,
            trigger_channel_index,
            linked_channels,
            trim_data_seconds,
        ):
            self.trigger_type = trigger_type
            self.trigger_channel_index = trigger_channel_index
            self.linked_channels = linked_channels
            self.trim_data_seconds = trim_data_seconds

    class _DataTableFilter:
        def __init__(self, *, columns, query):
            self.columns = columns
            self.query = query

    fake = SimpleNamespace(
        Manager=_ManagerAPI,
        LogicDeviceConfiguration=_LogicDeviceConfiguration,
        TimedCaptureMode=_TimedCaptureMode,
        CaptureConfiguration=_CaptureConfiguration,
        DigitalTriggerCaptureMode=_DigitalTriggerCaptureMode,
        DigitalTriggerType=SimpleNamespace(RISING="RISING_ENUM", FALLING="FALLING_ENUM"),
        DataTableFilter=_DataTableFilter,
    )
    monkeypatch.setattr(adapter_mod, "automation", fake)
    return {"manager": manager, "launched": launched, "calls": calls}


def test_connect_uses_manager_connect(fake_automation):
    adapter = adapter_mod.SaleaeAdapter()
    out = adapter.connect(host="127.0.0.2", port=1111, timeout_seconds=2.0)
    assert out["connected"] is True
    assert fake_automation["calls"]["connect"] == {
        "address": "127.0.0.2",
        "port": 1111,
        "connect_timeout_seconds": 2.0,
    }


def test_connect_launches_when_requested(fake_automation):
    adapter = adapter_mod.SaleaeAdapter()
    out = adapter.connect(launch_if_needed=True, port=2222, logic2_binary="/opt/Logic")
    assert out["connected"] is True
    assert fake_automation["calls"]["launch"] == {"port": 2222, "application_path": "/opt/Logic"}


def test_capture_lifecycle(fake_automation, monkeypatch: pytest.MonkeyPatch):
    uuids = iter(["cap-1"])
    monkeypatch.setattr(adapter_mod.uuid, "uuid4", lambda: next(uuids))
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()

    started = adapter.start_capture(device_configuration="cfg")
    assert started == {"capture_id": "cap-1"}

    waited = adapter.wait_capture("cap-1")
    stopped = adapter.stop_capture("cap-1")
    closed = adapter.close_capture("cap-1")

    assert waited["state"] == "complete"
    assert stopped["state"] == "stopped"
    assert closed["state"] == "closed"
    assert adapter.status()["active_captures"] == 0


def test_add_analyzer_and_export_table(fake_automation, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    uuids = iter(["cap-1", "an-1"])
    monkeypatch.setattr(adapter_mod.uuid, "uuid4", lambda: next(uuids))
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    adapter.start_capture(device_configuration="cfg")

    add_out = adapter.add_analyzer("cap-1", "SPI", label="spi0", settings={"clk": 0})
    assert add_out["analyzer_id"] == "an-1"

    out_file = tmp_path / "table.csv"
    export_out = adapter.export_data_table(
        "cap-1",
        str(out_file),
        analyzer_ids=["an-1"],
        columns=["Time", "Data"],
        query="AA",
        query_columns=["Data"],
        iso8601_timestamp=True,
    )
    assert export_out["path"] == str(out_file.resolve())
    capture = fake_automation["manager"].capture
    assert capture.export_kwargs["filepath"] == str(out_file.resolve())
    assert capture.export_kwargs["columns"] == ["Time", "Data"]
    assert capture.export_kwargs["iso8601_timestamp"] is True
    assert capture.export_kwargs["filter"].query == "AA"
    assert capture.export_kwargs["filter"].columns == ["Data"]


def test_read_digital_returns_channel_states(fake_automation):
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    out = adapter.read_digital(channels=[0, 1], sample_rate=5_000_000, duration_seconds=0.02)
    assert out == {
        "channels": {
            0: {"value": 0, "state": "low"},
            1: {"value": 1, "state": "high"},
        }
    }


def test_read_digital_requires_connection():
    adapter = adapter_mod.SaleaeAdapter()
    with pytest.raises(RuntimeError, match="Not connected to Logic 2"):
        adapter.read_digital(channels=[0])


def test_save_and_load_capture(fake_automation, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    uuids = iter(["cap-1", "cap-2"])
    monkeypatch.setattr(adapter_mod.uuid, "uuid4", lambda: next(uuids))
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    adapter.start_capture(device_configuration="cfg")

    out_file = tmp_path / "capture.sal"
    saved = adapter.save_capture("cap-1", str(out_file))
    loaded = adapter.load_capture(str(out_file))

    assert saved["path"] == str(out_file.resolve())
    assert loaded["path"] == str(out_file.resolve())
    assert loaded["capture_id"] == "cap-2"


def test_export_raw_csv_passes_requested_channels(fake_automation, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    uuids = iter(["cap-1"])
    monkeypatch.setattr(adapter_mod.uuid, "uuid4", lambda: next(uuids))
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    adapter.start_capture(device_configuration="cfg")

    out_dir = tmp_path / "raw"
    out = adapter.export_raw_csv("cap-1", str(out_dir), digital_channels=[0], analog_channels=[1])

    assert out["path"] == str(out_dir.resolve())
    assert fake_automation["manager"].capture.export_kwargs == {
        "directory": str(out_dir.resolve()),
        "digital_channels": [0],
        "analog_channels": [1],
    }


def test_read_analog_returns_stats(fake_automation, monkeypatch: pytest.MonkeyPatch):
    class _AnalogCapture(_FakeCapture):
        def export_raw_data_csv(self, *, directory, digital_channels=None, analog_channels=None):
            csv_path = os.path.join(directory, "analog.csv")
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Time [s]", "Channel 2"])
                writer.writeheader()
                writer.writerow({"Time [s]": "0.0", "Channel 2": "1.0"})
                writer.writerow({"Time [s]": "0.1", "Channel 2": "3.0"})

    fake_automation["manager"].capture = _AnalogCapture()
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    out = adapter.read_analog(channels=[2])

    assert out == {"channels": {2: {"min_v": 1.0, "max_v": 3.0, "mean_v": 2.0, "samples": 2}}}


def test_read_analog_raises_when_no_samples(fake_automation):
    class _EmptyAnalogCapture(_FakeCapture):
        def export_raw_data_csv(self, *, directory, digital_channels=None, analog_channels=None):
            csv_path = os.path.join(directory, "analog.csv")
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Time [s]", "Channel 0"])
                writer.writeheader()

    fake_automation["manager"].capture = _EmptyAnalogCapture()
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    with pytest.raises(RuntimeError, match="No samples captured"):
        adapter.read_analog(channels=[0])


def test_read_mixed_returns_both_sets(fake_automation):
    class _MixedCapture(_FakeCapture):
        def export_raw_data_csv(self, *, directory, digital_channels=None, analog_channels=None):
            digital_path = os.path.join(directory, "digital.csv")
            with open(digital_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Time [s]", "Channel 0"])
                writer.writeheader()
                writer.writerow({"Time [s]": "0", "Channel 0": "1"})
            analog_path = os.path.join(directory, "analog.csv")
            with open(analog_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Time [s]", "Channel 2"])
                writer.writeheader()
                writer.writerow({"Time [s]": "0.0", "Channel 2": "0.5"})
                writer.writerow({"Time [s]": "0.1", "Channel 2": "1.5"})

    fake_automation["manager"].capture = _MixedCapture()
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    out = adapter.read_mixed(digital_channels=[0], analog_channels=[2])

    assert out == {
        "digital": {0: {"value": 1, "state": "high"}},
        "analog": {2: {"min_v": 0.5, "max_v": 1.5, "mean_v": 1.0, "samples": 2}},
    }


def test_parse_digital_edges(tmp_path: Path):
    csv_path = tmp_path / "digital.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Time [s]", "Channel 0"])
        writer.writeheader()
        writer.writerow({"Time [s]": "0.0", "Channel 0": "0"})
        writer.writerow({"Time [s]": "0.1", "Channel 0": "1"})
        writer.writerow({"Time [s]": "0.2", "Channel 0": "1"})
        writer.writerow({"Time [s]": "0.3", "Channel 0": "0"})

    adapter = adapter_mod.SaleaeAdapter()
    rising, falling, high_time, total_time = adapter._parse_digital_edges(str(csv_path), 0)
    assert rising == [0.1]
    assert falling == [0.3]
    assert high_time == pytest.approx(0.2)
    assert total_time == pytest.approx(0.3)


def test_measure_frequency_and_count_edges(fake_automation, monkeypatch: pytest.MonkeyPatch):
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    monkeypatch.setattr(adapter, "_start_timed_digital_capture", lambda *args, **kwargs: _FakeCapture())
    monkeypatch.setattr(
        adapter,
        "_parse_digital_edges",
        lambda *_args, **_kwargs: ([0.1, 0.3, 0.5], [0.2, 0.4], 0.2, 0.5),
    )

    freq = adapter.measure_frequency(channel=0)
    edges = adapter.count_edges(channel=0)

    assert freq == {
        "channel": 0,
        "frequency_hz": 5.0,
        "period_seconds": 0.2,
        "duty_cycle_pct": 40.0,
        "rising_edges": 3,
        "falling_edges": 2,
    }
    assert edges == {
        "channel": 0,
        "rising_edges": 3,
        "falling_edges": 2,
        "total_edges": 5,
        "duration_seconds": 0.5,
    }


def test_measure_frequency_requires_multiple_rising_edges(fake_automation, monkeypatch: pytest.MonkeyPatch):
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    monkeypatch.setattr(adapter, "_start_timed_digital_capture", lambda *args, **kwargs: _FakeCapture())
    monkeypatch.setattr(adapter, "_parse_digital_edges", lambda *_args, **_kwargs: ([0.1], [], 0.0, 0.2))
    with pytest.raises(RuntimeError, match="Not enough rising edges"):
        adapter.measure_frequency(channel=0)


def test_measure_pulse_width_success_and_error(fake_automation, monkeypatch: pytest.MonkeyPatch):
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    monkeypatch.setattr(adapter, "_start_timed_digital_capture", lambda *args, **kwargs: _FakeCapture())
    monkeypatch.setattr(
        adapter,
        "_parse_digital_edges",
        lambda *_args, **_kwargs: ([0.1, 0.4], [0.2, 0.7], 0.0, 0.0),
    )
    out = adapter.measure_pulse_width(channel=0)
    assert out == {
        "channel": 0,
        "pulse_count": 2,
        "min_seconds": 0.1,
        "max_seconds": 0.3,
        "mean_seconds": 0.2,
    }

    monkeypatch.setattr(adapter, "_parse_digital_edges", lambda *_args, **_kwargs: ([0.2], [0.1], 0.0, 0.0))
    with pytest.raises(RuntimeError, match="No complete pulses"):
        adapter.measure_pulse_width(channel=0)


def test_decode_protocol_and_wrappers(fake_automation):
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()

    def _fake_decode(channels, analyzer_name, analyzer_settings, device_id, sample_rate, duration_seconds):
        return [{"Name": analyzer_name, "ch": str(channels[0]), "s": str(analyzer_settings)}]

    adapter._decode_protocol = _fake_decode  # type: ignore[method-assign]

    uart = adapter.decode_uart(channel=1, baud_rate=115200)
    i2c = adapter.decode_i2c(sda_channel=2, scl_channel=3)
    spi = adapter.decode_spi(mosi_channel=0, miso_channel=1, clock_channel=2, enable_channel=3, bits_per_transfer=16)

    assert uart["frame_count"] == 1
    assert i2c["frame_count"] == 1
    assert spi["frame_count"] == 1
    assert "Bits per Transfer" in spi["frames"][0]["s"]


def test_decode_protocol_missing_table_returns_empty(fake_automation, monkeypatch: pytest.MonkeyPatch):
    class _NoTableCapture(_FakeCapture):
        def add_analyzer(self, analyzer_name, **kwargs):
            return {"kind": analyzer_name}

        def export_data_table(self, **kwargs):
            return None

    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    monkeypatch.setattr(adapter, "_start_timed_digital_capture", lambda *args, **kwargs: _NoTableCapture())

    out = adapter._decode_protocol(
        channels=[0],
        analyzer_name="I2C",
        analyzer_settings={"SDA": 0, "SCL": 1},
        device_id=None,
        sample_rate=1_000_000,
        duration_seconds=0.1,
    )
    assert out == []


def test_read_on_trigger_success_and_validation(fake_automation):
    class _TriggerCapture(_FakeCapture):
        def export_raw_data_csv(self, *, directory, digital_channels=None, analog_channels=None):
            csv_path = os.path.join(directory, "digital.csv")
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Time [s]", "Channel 0", "Channel 1"])
                writer.writeheader()
                writer.writerow({"Time [s]": "0", "Channel 0": "1", "Channel 1": "0"})

    fake_automation["manager"].capture = _TriggerCapture()
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()

    out = adapter.read_on_trigger(channels=[1], trigger_channel=0, trigger_type="rising")
    assert out == {
        "trigger_channel": 0,
        "trigger_type": "rising",
        "channels": {1: {"value": 0, "state": "low"}},
    }

    with pytest.raises(ValueError, match="Invalid trigger_type"):
        adapter.read_on_trigger(channels=[1], trigger_channel=0, trigger_type="invalid")


def test_wait_for_voltage_success_timeout_and_validation(fake_automation, monkeypatch: pytest.MonkeyPatch):
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    readings = iter([1.0, 1.3])
    monkeypatch.setattr(
        adapter,
        "read_analog",
        lambda **kwargs: {"channels": {0: {"mean_v": next(readings)}}},
    )
    times = iter([0.0, 0.05, 0.1, 0.15])
    monkeypatch.setattr("time.monotonic", lambda: next(times))

    out = adapter.wait_for_voltage(channel=0, threshold_v=1.2, timeout_seconds=1.0)
    assert out["channel"] == 0
    assert out["condition"] == "above"

    with pytest.raises(ValueError, match="condition must be"):
        adapter.wait_for_voltage(channel=0, threshold_v=1.0, condition="bad")

    monkeypatch.setattr(adapter, "read_analog", lambda **kwargs: {"channels": {0: {"mean_v": 0.1}}})
    timeout_times = iter([0.0, 0.2, 0.4, 0.6])
    monkeypatch.setattr("time.monotonic", lambda: next(timeout_times))
    with pytest.raises(TimeoutError, match="did not go above"):
        adapter.wait_for_voltage(channel=0, threshold_v=0.5, timeout_seconds=0.5)


def test_wait_for_signal_success_timeout_and_validation(fake_automation, monkeypatch: pytest.MonkeyPatch):
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    states = iter(["low", "high"])
    monkeypatch.setattr(
        adapter,
        "read_digital",
        lambda **kwargs: {"channels": {0: {"state": next(states)}}},
    )
    times = iter([0.0, 0.01, 0.03, 0.05])
    monkeypatch.setattr("time.monotonic", lambda: next(times))
    out = adapter.wait_for_signal(channel=0, target_state="high", timeout_seconds=1.0)
    assert out["state"] == "high"

    with pytest.raises(ValueError, match="target_state must be"):
        adapter.wait_for_signal(channel=0, target_state="bad")

    monkeypatch.setattr(adapter, "read_digital", lambda **kwargs: {"channels": {0: {"state": "low"}}})
    timeout_times = iter([0.0, 0.2, 0.4, 0.6])
    monkeypatch.setattr("time.monotonic", lambda: next(timeout_times))
    with pytest.raises(TimeoutError, match="did not reach"):
        adapter.wait_for_signal(channel=0, target_state="high", timeout_seconds=0.5)


def test_get_device_info_all_single_and_missing(fake_automation):
    adapter = adapter_mod.SaleaeAdapter()
    adapter.connect()
    all_devices = adapter.get_device_info()
    one = adapter.get_device_info("D1")
    assert "devices" in all_devices
    assert one["device_id"] == "D1"
    with pytest.raises(KeyError, match="not found"):
        adapter.get_device_info("nope")
