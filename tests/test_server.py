from __future__ import annotations

from types import SimpleNamespace

import pytest

from saleae_mcp import server


class _ManualCaptureMode:
    pass


class _TimedCaptureMode:
    def __init__(self, duration_seconds: float):
        self.duration_seconds = duration_seconds


class _DigitalTriggerCaptureMode:
    def __init__(
        self,
        *,
        trigger_type: object,
        trigger_channel_index: int,
        linked_channels: list[int],
        trim_data_seconds: float,
    ):
        self.trigger_type = trigger_type
        self.trigger_channel_index = trigger_channel_index
        self.linked_channels = linked_channels
        self.trim_data_seconds = trim_data_seconds


class _GlitchFilterEntry:
    def __init__(self, *, channel_index: int, pulse_width_seconds: float):
        self.channel_index = channel_index
        self.pulse_width_seconds = pulse_width_seconds


class _LogicDeviceConfiguration:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _CaptureConfiguration:
    def __init__(self, *, capture_mode: object):
        self.capture_mode = capture_mode


@pytest.fixture()
def fake_automation(monkeypatch: pytest.MonkeyPatch):
    fake = SimpleNamespace(
        ManualCaptureMode=_ManualCaptureMode,
        TimedCaptureMode=_TimedCaptureMode,
        DigitalTriggerCaptureMode=_DigitalTriggerCaptureMode,
        GlitchFilterEntry=_GlitchFilterEntry,
        LogicDeviceConfiguration=_LogicDeviceConfiguration,
        CaptureConfiguration=_CaptureConfiguration,
        DigitalTriggerType=SimpleNamespace(RISING="RISING_ENUM"),
    )
    monkeypatch.setattr(server, "automation", fake)
    return fake


def test_capture_mode_manual(fake_automation):
    mode = server._capture_mode({"kind": "manual"})
    assert isinstance(mode, _ManualCaptureMode)


def test_capture_mode_timed(fake_automation):
    mode = server._capture_mode({"kind": "timed", "duration_seconds": "1.5"})
    assert isinstance(mode, _TimedCaptureMode)
    assert mode.duration_seconds == 1.5


def test_capture_mode_digital_trigger_from_string(fake_automation):
    mode = server._capture_mode(
        {
            "kind": "digital_trigger",
            "trigger_type": "rising",
            "channel": 3,
            "linked_channels": [1, 2],
            "after_trigger_seconds": 0.25,
        }
    )
    assert isinstance(mode, _DigitalTriggerCaptureMode)
    assert mode.trigger_type == "RISING_ENUM"
    assert mode.trigger_channel_index == 3
    assert mode.linked_channels == [1, 2]
    assert mode.trim_data_seconds == 0.25


def test_capture_mode_invalid_kind_raises(fake_automation):
    with pytest.raises(ValueError, match="Unsupported capture mode kind"):
        server._capture_mode({"kind": "wat"})


def test_build_start_capture_kwargs_requires_device_configuration(fake_automation):
    with pytest.raises(ValueError, match="device_configuration is required"):
        server._build_start_capture_kwargs({})


def test_build_start_capture_kwargs_builds_device_and_capture(fake_automation):
    payload = {
        "device_id": "ABC123",
        "device_configuration": {
            "enabled_digital_channels": [0, 1],
            "enabled_analog_channels": [2],
            "digital_sample_rate": 10_000_000,
            "analog_sample_rate": 1_000_000,
            "digital_threshold_volts": 1.2,
            "glitch_filters": [{"channel_index": 0, "pulse_width_seconds": 0.000001}],
        },
        "capture_configuration": {"capture_mode": {"kind": "manual"}},
    }

    out = server._build_start_capture_kwargs(payload)
    assert out["device_id"] == "ABC123"
    assert isinstance(out["device_configuration"], _LogicDeviceConfiguration)
    dev_cfg = out["device_configuration"].kwargs
    assert dev_cfg["enabled_digital_channels"] == [0, 1]
    assert dev_cfg["enabled_analog_channels"] == [2]
    assert dev_cfg["digital_sample_rate"] == 10_000_000
    assert dev_cfg["analog_sample_rate"] == 1_000_000
    assert dev_cfg["digital_threshold_volts"] == 1.2
    assert len(dev_cfg["glitch_filters"]) == 1
    assert isinstance(dev_cfg["glitch_filters"][0], _GlitchFilterEntry)
    assert isinstance(out["capture_configuration"], _CaptureConfiguration)


def test_saleae_start_capture_wraps_adapter_success(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server, "_build_start_capture_kwargs", lambda payload: {"foo": "bar"})

    class _FakeAdapter:
        def start_capture(self, **kwargs):
            assert kwargs == {"foo": "bar"}
            return {"capture_id": "cid"}

    monkeypatch.setattr(server, "adapter", _FakeAdapter())
    out = server.saleae_start_capture({"any": "payload"})
    assert out == {"ok": True, "data": {"capture_id": "cid"}}


def test_saleae_start_capture_wraps_adapter_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server, "_build_start_capture_kwargs", lambda payload: {"foo": "bar"})

    class _FakeAdapter:
        def start_capture(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(server, "adapter", _FakeAdapter())
    out = server.saleae_start_capture({"any": "payload"})
    assert out["ok"] is False
    assert out["error"]["type"] == "RuntimeError"
    assert out["error"]["message"] == "boom"


@pytest.mark.parametrize(
    ("fn_name", "args", "kwargs"),
    [
        ("saleae_connect", [], {}),
        ("saleae_disconnect", [], {}),
        ("saleae_status", [], {}),
        ("saleae_list_devices", [], {}),
        ("saleae_wait_capture", ["cap-1"], {}),
        ("saleae_stop_capture", ["cap-1"], {}),
        ("saleae_close_capture", ["cap-1"], {}),
        ("saleae_save_capture", ["cap-1", "/tmp/x.sal"], {}),
        ("saleae_load_capture", ["/tmp/x.sal"], {}),
        ("saleae_add_analyzer", ["cap-1", "SPI"], {}),
        ("saleae_export_data_table", ["cap-1", "/tmp/t.csv", ["an-1"]], {}),
        ("saleae_read_analog", [[0]], {}),
        ("saleae_read_digital", [[0]], {}),
        ("saleae_export_raw_csv", ["cap-1", "/tmp/raw"], {}),
        ("saleae_read_mixed", [[0], [1]], {}),
        ("saleae_measure_frequency", [0], {}),
        ("saleae_measure_pulse_width", [0], {}),
        ("saleae_count_edges", [0], {}),
        ("saleae_decode_uart", [0], {}),
        ("saleae_decode_i2c", [0, 1], {}),
        ("saleae_decode_spi", [0, 1, 2], {}),
        ("saleae_read_on_trigger", [[1], 0], {}),
        ("saleae_wait_for_voltage", [0, 1.2], {}),
        ("saleae_wait_for_signal", [0], {}),
        ("saleae_get_device_info", [], {}),
    ],
)
def test_tool_wrappers_return_ok(monkeypatch: pytest.MonkeyPatch, fn_name: str, args: list, kwargs: dict):
    adapter_method = fn_name.replace("saleae_", "")

    class _FakeAdapter:
        def __getattr__(self, _name):
            return lambda *a, **k: {"m": _name, "args": list(a), "kwargs": k}

    monkeypatch.setattr(server, "adapter", _FakeAdapter())
    out = getattr(server, fn_name)(*args, **kwargs)
    assert out["ok"] is True
    assert out["data"]["m"] == adapter_method


@pytest.mark.parametrize(
    ("fn_name", "args", "kwargs"),
    [
        ("saleae_connect", [], {}),
        ("saleae_disconnect", [], {}),
        ("saleae_status", [], {}),
        ("saleae_list_devices", [], {}),
        ("saleae_wait_capture", ["cap-1"], {}),
        ("saleae_stop_capture", ["cap-1"], {}),
        ("saleae_close_capture", ["cap-1"], {}),
        ("saleae_save_capture", ["cap-1", "/tmp/x.sal"], {}),
        ("saleae_load_capture", ["/tmp/x.sal"], {}),
        ("saleae_add_analyzer", ["cap-1", "SPI"], {}),
        ("saleae_export_data_table", ["cap-1", "/tmp/t.csv", ["an-1"]], {}),
        ("saleae_read_analog", [[0]], {}),
        ("saleae_read_digital", [[0]], {}),
        ("saleae_export_raw_csv", ["cap-1", "/tmp/raw"], {}),
        ("saleae_read_mixed", [[0], [1]], {}),
        ("saleae_measure_frequency", [0], {}),
        ("saleae_measure_pulse_width", [0], {}),
        ("saleae_count_edges", [0], {}),
        ("saleae_decode_uart", [0], {}),
        ("saleae_decode_i2c", [0, 1], {}),
        ("saleae_decode_spi", [0, 1, 2], {}),
        ("saleae_read_on_trigger", [[1], 0], {}),
        ("saleae_wait_for_voltage", [0, 1.2], {}),
        ("saleae_wait_for_signal", [0], {}),
        ("saleae_get_device_info", [], {}),
    ],
)
def test_tool_wrappers_return_err(monkeypatch: pytest.MonkeyPatch, fn_name: str, args: list, kwargs: dict):
    class _FakeAdapter:
        def __getattr__(self, _name):
            def _raise(*_a, **_k):
                raise RuntimeError(f"{_name} boom")

            return _raise

    monkeypatch.setattr(server, "adapter", _FakeAdapter())
    out = getattr(server, fn_name)(*args, **kwargs)
    assert out["ok"] is False
    assert out["error"]["type"] == "RuntimeError"
