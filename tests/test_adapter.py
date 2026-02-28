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

    def export_raw_data_csv(self, *, directory, digital_channels):
        csv_path = os.path.join(directory, "digital.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["Time [s]", "Channel 0", "Channel 1"])
            writer.writeheader()
            writer.writerow({"Time [s]": "0", "Channel 0": "0", "Channel 1": "1"})


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

    class _DataTableFilter:
        def __init__(self, *, columns, query):
            self.columns = columns
            self.query = query

    fake = SimpleNamespace(
        Manager=_ManagerAPI,
        LogicDeviceConfiguration=_LogicDeviceConfiguration,
        TimedCaptureMode=_TimedCaptureMode,
        CaptureConfiguration=_CaptureConfiguration,
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
