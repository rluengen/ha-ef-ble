import asyncio
import struct
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from pytest_mock import MockerFixture

from custom_components.ef_ble.deprecated.switches import DEPRECATED_SWITCH_TYPES
from custom_components.ef_ble.eflib import connection as connection_module
from custom_components.ef_ble.eflib.devices.power_hub import Device
from custom_components.ef_ble.eflib.exceptions import (
    NotConnectedError,
    PacketParseError,
)
from custom_components.ef_ble.eflib.model.mm100 import (
    BbcOutData,
    BmsTotalData,
    SccData,
)
from custom_components.ef_ble.eflib.packet import Packet

# Raw decrypted BLE frames (payloads still XOR-obfuscated) captured from a live Power Hub;
# power_hub.packet_parse un-XORs them. One telemetry frame per sub-module.
FRAME_SCC = "aa038800c02c74b48300043e0521010005203945444d425939242420594642354647747474747474747427747570fabb74747474747474747474ca00747474747474747474747474747474747474747474745a757474d37574745774517474747576757575747474747474747474747474742c7674742c7674747474747474747474747474740f74f17475757675757474747474747474747474ec79"
FRAME_BBC_IN = "aa037400282c98a1a900023e502101005020d5abd0a9dba8a9aba0dfa0afa8a9abab88bf98989299999de7fe9898749c9898b9989898a1569898a0999898889898983e98989821989898bb98bc98be989998d80498984a9c98988d9b9898999f999a9999c09a98989898989898989898e39899989898989a98989898989898989898989898986f9e"
FRAME_BBC_OUT = "aa037400282cf6d14500033e512101005120bbc5bec7c3c6c7c4ceb1cec7c6c2c7c56eccf6f69ef6f7f36d3bf6f691f1f6f695f6f6f6dec3f6f61ee4f6f6b7f6f6f6eceef6f61bf4f6f6c5f6f6f6f6f6f4f7f6f6f6f6c1c6f6f67dc7f7f6f6f6f6f6f6f6f7f1f3f6f6f6f6f6f6f6f6f6fcf6f7f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6cb75"
FRAME_IC_HIGH = "aa036300142cf21d2001063e042101000406bfc3c2cbc7dfa2a1b6badfc1c6c4cbc1f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2d6f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f28acefdf3f3f2fdf2f2f2f2f2f2f2f2f2f202f2f3f2f3f3c0f2f2f2f2f2f2f2f2f2f2f2f2f2f2cc02"
FRAME_DC = "aa03d7000f0c00000000083e5421110154204d334c315a4142345a473752303239380000000000000000000000003d3500000000000000000000000000000000000000000000000000000000000000000000000000000302000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000700000000000000000000000000000024002200dedeff0000409c689c909cb89ce09c089d309d589d809da89dd09df89d609f0000000000000000000000000000000000000000000000000000000000000000209e489e709e989edeff0000010000005416"


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "M3H1ZAB4H3C0207")
    device._conn = mocker.AsyncMock()
    return device


@pytest.fixture
def panel() -> Device:
    serial = "M3H1TEST00000000"
    advertisement = AdvertisementData(
        local_name="Test Power Hub",
        manufacturer_data={
            Device.MANUFACTURER_KEY: b"\x03" + serial.encode("ascii") + bytes(6)
        },
        service_data={},
        service_uuids=[],
        tx_power=None,
        rssi=-60,
        platform_data=(),
    )
    return Device(
        BLEDevice("AA:BB:CC:DD:EE:FF", "Test Power Hub", {}),
        advertisement,
        serial,
    )


@pytest.fixture
async def connected_panel(
    panel: Device, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[Device, list[Packet]]]:
    commands: list[Packet] = []

    async def establish(*args: Any, **kwargs: Any) -> Mock:
        client = Mock(is_connected=True)
        notify: Callable[[object, bytearray], Awaitable[None]]

        async def subscribe(
            characteristic: object,
            callback: Callable[[object, bytearray], Awaitable[None]],
            **options: Any,
        ) -> None:
            nonlocal notify
            notify = callback

        async def write(
            characteristic: object, data: bytearray, **options: Any
        ) -> None:
            request = Packet.from_bytes(bytes(data))
            assert isinstance(request, Packet)
            if request.cmd_set != 0x35:
                commands.append(request)
            reply = Packet(
                request.dst, request.src, request.cmd_set, request.cmd_id, b"\x00"
            )
            await notify(characteristic, bytearray(reply.to_bytes()))

        async def disconnect() -> None:
            client.is_connected = False
            kwargs["disconnected_callback"](client)

        client.start_notify = AsyncMock(side_effect=subscribe)
        client.write_gatt_char = AsyncMock(side_effect=write)
        client.disconnect = AsyncMock(side_effect=disconnect)
        return client

    monkeypatch.setattr(connection_module, "establish_connection", establish)
    monkeypatch.setattr(
        connection_module, "close_stale_connections_by_address", AsyncMock()
    )
    panel.with_disabled_reconnect()
    try:
        await panel.connect(user_id="TEST_USER")
        await panel.wait_until_authenticated_or_error(raise_on_error=True)
        yield panel, commands
    finally:
        await panel.disconnect()


def _dc_metadata_payload(metadata: list[tuple[int, str]]) -> bytes:
    payload = bytearray((0, len(metadata)))
    for icon_id, name in metadata:
        encoded = name.encode("utf-8")
        payload.extend(struct.pack("<IB", icon_id, len(encoded)))
        payload.extend(encoded)
    return bytes(payload)


# No captures exist yet for the totals limits, module-state or pack frames, so these
# helpers build them from the app parser layouts (`p50.g.p0`, `p50.g.A`).
def _totals_payload(*, state: int, remain_min: int, chg_stop: int, dsg_stop: int):
    return struct.pack(
        "<BBiiIBBB", 54, state, 300, 0, remain_min, 0, chg_stop, dsg_stop
    ).ljust(BmsTotalData.SIZE, b"\x00")


def _module_record(sn: str, *, src_addr: int, custom: int, run_state: int = 1):
    return struct.pack(
        "<B16sbBB8sIbB", 0, sn.encode(), run_state, 0, 0, bytes(8), custom, src_addr, 0
    )


def _pack_payload(
    sn: str, *, soc: int = 80, chg_soc: int = 100, dsg_soc: int = 5, ptc_touch: int = 0
) -> bytes:
    return (
        sn.encode().ljust(16, b"\x00")
        + bytes(21)  # error code, versions, card/kit ids and BMS type
        + struct.pack("<BIib", soc, 52_340, 0, 25)
        + bytes(18)  # charge/BMS state, capacities and cycles
        + struct.pack("<II", 3_301, 3_288)
        + bytes(5)  # cell/MOS temperatures and fault flags
        + struct.pack("<iiI", 120, 7, 0)
        + struct.pack("<BBBbbb", 0, chg_soc, dsg_soc, 0, ptc_touch, 0)
        + bytes(10)  # rest of the 106-byte base struct
    )


async def _feed(device: Device, module: int, cmd_id: int, payload: bytes) -> bool:
    frame = Packet(module, 0x21, module, cmd_id, payload).to_bytes()
    return await device.data_parse(await device.packet_parse(frame))


@pytest.mark.parametrize(
    ("frame", "src", "cmd_set", "cmd_id"),
    [
        (FRAME_SCC, 0x05, 0x05, 0x20),
        (FRAME_BBC_IN, 0x50, 0x50, 0x20),
        (FRAME_BBC_OUT, 0x51, 0x51, 0x20),
        (FRAME_IC_HIGH, 0x04, 0x04, 0x06),
    ],
)
async def test_power_hub_routes_and_processes_frames(
    device, frame, src, cmd_set, cmd_id
):
    packet = await device.packet_parse(bytes.fromhex(frame))
    assert packet is not None
    assert (packet.src, packet.cmd_set, packet.cmd_id) == (src, cmd_set, cmd_id)
    assert await device.data_parse(packet) is True


async def test_power_hub_dc_input(device):
    packet = await device.packet_parse(bytes.fromhex(FRAME_BBC_IN))
    await device.data_parse(packet)

    # dcInputWatt=33 W, batteryVol=52793 mV, batteryCur=312 mA (scaled to V/A).
    assert device.get_value(Device.dc_input_power) == 33
    assert device.get_value(Device.battery_voltage) == pytest.approx(52.79, abs=0.01)
    assert device.get_value(Device.battery_current) == pytest.approx(0.31, abs=0.01)
    # chargePause=0 -> DC input charging allowed.
    assert device.dc_input is True


async def test_power_hub_pv_inputs(device):
    await device.data_parse(await device.packet_parse(bytes.fromhex(FRAME_SCC)))

    # pv1InVol=29886 mV with no current drawn; mppt1/2SwitchState=1 -> both inputs on.
    assert device.pv_voltage_1 == pytest.approx(29.89)
    assert device.pv_current_1 == 0
    assert device.pv1_input is True
    assert device.pv2_input is True


async def test_power_hub_solar_controller_temperatures(panel: Device):
    payload = bytes(72) + struct.pack("<hhh", -5, 37, 28)
    assert await _feed(panel, 0x05, 0x20, payload)

    assert panel.solar_heatsink_1_temperature == -5
    assert panel.solar_heatsink_2_temperature == 37
    assert panel.solar_pcb_temperature == 28


async def test_power_hub_dc_output(device):
    packet = await device.packet_parse(bytes.fromhex(FRAME_BBC_OUT))
    await device.data_parse(packet)

    # ldOutWatt=65 W, ldOutVol=13608 mV, ldOutCur=4840 mA (12 V nominal DC load bus).
    assert device.get_value(Device.dc_output_power) == 65
    assert device.get_value(Device.dc_output_voltage) == pytest.approx(13.61, abs=0.01)
    assert device.get_value(Device.dc_output_current) == pytest.approx(4.84, abs=0.01)
    # dcSwitchMode=1 -> DC output master reported on.
    assert device.dc_ports is True


@pytest.mark.parametrize(
    ("frame", "model", "field", "expected"),
    [
        (FRAME_SCC, SccData, "pv1_cable_length", 600),
        (FRAME_BBC_OUT, BbcOutData, "day_energy", 12343),
        (FRAME_BBC_OUT, BbcOutData, "total_energy", 78219),
    ],
)
async def test_power_hub_fields_after_reserved_gap_are_aligned(
    device, frame, model, field, expected
):
    packet = await device.packet_parse(bytes.fromhex(frame))
    assert getattr(model.from_bytes(packet.payload), field) == expected


async def test_power_hub_dc_ports_switch_sends_command(device):
    await device.enable_dc_ports(True)
    on_packet = device._conn.send_packet.call_args[0][0]
    assert (on_packet.src, on_packet.dst) == (0x21, 0x51)
    assert (on_packet.cmd_set, on_packet.cmd_id) == (0x50, 0x22)
    assert on_packet.payload[1] == 1

    await device.enable_dc_ports(False)
    assert device._conn.send_packet.call_args[0][0].payload[1] == 0


async def test_power_hub_ac_inverter(device):
    packet = await device.packet_parse(bytes.fromhex(FRAME_IC_HIGH))
    await device.data_parse(packet)

    # AC inverter idle: no input/output power, heat-sink at 36 C.
    assert device.get_value(Device.ac_input_power) == 0
    assert device.get_value(Device.ac_output_power) == 0
    assert device.get_value(Device.ac_inverter_temperature) == 36
    # invSwitchState=0 -> AC output reported off.
    assert device.ac_output is False
    assert device.ac_input is False


@pytest.mark.parametrize(
    ("disabled", "expected"), [(0, True), (1, False), (None, None)]
)
async def test_power_hub_ac_input_uses_charge_disable_not_output_state(
    panel: Device, disabled: int | None, expected: bool | None
):
    # App parser p50.g.j0: output state at 49, config at 60, charge-disable at 64.
    payload = bytes(49) + b"\x01" + bytes(10)
    if disabled is not None:
        payload += bytes((1, 230, 60, 15, disabled))

    assert await _feed(panel, 0x04, 0x06, payload)
    assert panel.ac_input is expected
    assert panel.ac_output is True


async def test_power_hub_daily_ac_energy_follows_device_reset(panel: Device):
    for input_wh, output_wh in ((1234, 5678), (0, 0)):
        payload = bytes(52) + struct.pack("<II", input_wh, output_wh)
        assert await _feed(panel, 0x04, 0x06, payload)
        assert panel.ac_input_energy_today == input_wh
        assert panel.ac_output_energy_today == output_wh


async def test_power_hub_ac_output_switch_sends_command(device):
    await device.enable_ac_output(True)
    on_packet = device._conn.send_packet.call_args[0][0]
    assert (on_packet.src, on_packet.dst) == (0x21, 0x02)
    assert (on_packet.cmd_set, on_packet.cmd_id) == (0x02, 0x07)
    assert on_packet.payload == bytes.fromhex("01ffffffffff01ffffff")

    await device.enable_ac_output(False)
    off_packet = device._conn.send_packet.call_args[0][0]
    assert off_packet.payload == bytes.fromhex("00ffffffffff01ffffff")


async def test_power_hub_solar_input_present(device):
    packet = await device.packet_parse(bytes.fromhex(FRAME_SCC))
    await device.data_parse(packet)

    assert Device.solar_input_power.public_name in device.updated_fields
    assert isinstance(device.get_value(Device.solar_input_power), (int, float))


async def test_power_hub_dc_channels(device):
    packet = await device.packet_parse(bytes.fromhex(FRAME_DC))
    assert (packet.src, packet.cmd_set, packet.cmd_id) == (0x54, 0x54, 0x20)
    assert await device.data_parse(packet) is True

    # 16 DC channels; channel 10 active at 7 W / 515 mA, rest idle. Channels 13-16 come
    # from the frame's V2 extension.
    assert device.dc_output_channel_10_power == 7
    assert device.dc_output_channel_10_current == 0.515
    assert device.dc_output_channel_1_power == 0
    assert device.dc_output_channel_16_power == 0
    assert device.dc_output_channel_16_current == 0
    assert not hasattr(device, "dc_output_channel_17_power")


@pytest.mark.parametrize("extension", [b"", bytes(31)], ids=["base", "extended"])
async def test_power_hub_ac_circuits(panel: Device, extension: bytes):
    # No AC panel capture exists yet, so this frame is built from the app parser layout
    # (`p50.g.d`); the extension is the optional 31-byte tail of newer firmware.
    currents_ma = (0, 0, 1234, 0, 0, 7)
    powers_w = (0, 0, 280, 0, 0, 1)
    payload = (
        bytes(25)  # serial, error code and firmware version
        + struct.pack("<i6i6ii", 230_000, *currents_ma, *powers_w, sum(powers_w))
        + struct.pack("<hhBB", 30, 31, 0b100100, 0b111111)
        + extension
    )
    frame = Packet(0x53, 0x21, 0x53, 0x20, payload).to_bytes()

    assert await panel.data_parse(await panel.packet_parse(frame))
    assert panel.ac_output_channel_3_power == 280
    assert panel.ac_output_channel_3_current == 1.234
    assert panel.ac_output_channel_6_power == 1
    assert panel.ac_output_channel_6_current == 0.007
    assert panel.ac_output_channel_1_current == 0


@pytest.mark.parametrize(
    ("state", "charging", "discharging"),
    [(2, 95, None), (1, None, 95), (0, None, None)],
)
async def test_power_hub_charge_limits_and_remaining_time(
    panel: Device, state: int, charging: int | None, discharging: int | None
):
    payload = _totals_payload(state=state, remain_min=95, chg_stop=90, dsg_stop=10)
    await _feed(panel, 0x03, 0x1C, payload)

    assert panel.battery_charge_limit_max == 90
    assert panel.battery_charge_limit_min == 10
    assert panel.remaining_time_charging == charging
    assert panel.remaining_time_discharging == discharging
    assert panel.is_charging is (state == 2)


async def test_power_hub_charge_limits_fall_back_to_pack_set_soc(panel: Device):
    await _feed(
        panel,
        0x03,
        0x1C,
        _totals_payload(state=0, remain_min=0, chg_stop=0, dsg_stop=0),
    )
    await _feed(panel, 0x03, 0x1A, _pack_payload("PACKTEST00000001"))

    assert panel.battery_charge_limit_max == 100
    assert panel.battery_charge_limit_min == 5


@pytest.mark.parametrize("module_state_first", [True, False])
async def test_power_hub_places_packs_in_slots(panel: Device, module_state_first: bool):
    module_states = (
        _module_record("PACKTEST00000001", src_addr=3, custom=0x0001)  # under the hub
        + _module_record("PACKTEST00000002", src_addr=3, custom=0x0203)  # group 2, #3
        + _module_record("M3H1TEST00000000", src_addr=0x35, custom=0)
    )
    frames = [
        (0x35, 0x11, module_states),
        (0x03, 0x1A, _pack_payload("PACKTEST00000001")),
    ]
    for module, cmd_id, payload in frames if module_state_first else frames[::-1]:
        assert await _feed(panel, module, cmd_id, payload)

    assert panel.battery_2_enabled is True
    assert panel.battery_2_sn == "PACKTEST00000001"
    assert panel.battery_2_battery_level == 80
    assert panel.battery_2_cell_temperature == 25
    assert panel.battery_2_voltage == 52.34
    assert panel.battery_2_max_cell_voltage == 3.301
    assert panel.battery_2_min_cell_voltage == 3.288
    assert panel.battery_2_input_power == 120
    assert panel.battery_2_output_power == 7
    assert panel.battery_6_enabled is True
    assert panel.battery_6_battery_level is None
    assert panel.battery_1_enabled is False


@pytest.mark.parametrize(
    ("module", "cmd_id", "payload"),
    [
        (
            0x35,
            0x11,
            _module_record("PACKTEST00000001", src_addr=3, custom=2, run_state=2),
        ),
        (0x35, 0x11, b"\x00" * 10),
        (0x03, 0x1A, _pack_payload("PACKTEST00000001", soc=10, ptc_touch=3)),
        (0x03, 0x1A, _pack_payload("PACKTEST00000001", soc=10)[:105]),
    ],
    ids=["bad-run-state", "short-module-state", "bad-ptc-flag", "short-pack"],
)
async def test_power_hub_ignores_invalid_pack_frames(
    panel: Device, module: int, cmd_id: int, payload: bytes
):
    await _feed(
        panel, 0x35, 0x11, _module_record("PACKTEST00000001", src_addr=3, custom=1)
    )
    await _feed(panel, 0x03, 0x1A, _pack_payload("PACKTEST00000001"))

    await _feed(panel, module, cmd_id, payload)

    assert panel.battery_2_enabled is True
    assert panel.battery_2_battery_level == 80
    assert panel.battery_5_enabled is False


@pytest.mark.parametrize(
    ("setter", "cmd_id", "limit"),
    [
        ("set_battery_charge_limit_max", 0x31, 90),
        ("set_battery_charge_limit_min", 0x33, 20),
    ],
)
async def test_power_hub_charge_limit_commands(
    connected_panel: tuple[Device, list[Packet]], setter: str, cmd_id: int, limit: int
):
    device, commands = connected_panel
    await getattr(device, setter)(limit)

    packet = commands[-1]
    assert (packet.dst, packet.ddst) == (0x03, 0)
    assert (packet.cmd_set, packet.cmd_id) == (0x20, cmd_id)
    assert packet.payload[0] == limit


@pytest.mark.parametrize(
    ("control", "command", "flag_byte", "on", "off"),
    [
        ("enable_pv1_input", (0x05, 0x05, 0x06), 0, 1, 0),
        ("enable_pv2_input", (0x05, 0x05, 0x06), 1, 1, 0),
        # The DC input flag is "charge paused", so on is 0.
        ("enable_dc_input", (0x50, 0x50, 0x21), 4, 0, 1),
        ("enable_ac_input", (0x02, 0x02, 0x07), 4, 0, 1),
    ],
)
async def test_power_hub_input_switch_commands(
    connected_panel: tuple[Device, list[Packet]],
    control: str,
    command: tuple[int, int, int],
    flag_byte: int,
    on: int,
    off: int,
):
    device, commands = connected_panel
    for enabled, expected in ((True, on), (False, off)):
        await getattr(device, control)(enabled)

        packet = commands[-1]
        assert (packet.dst, packet.cmd_set, packet.cmd_id) == command
        assert packet.payload[flag_byte] == expected


async def test_power_hub_ac_input_command_leaves_output_unchanged(
    connected_panel: tuple[Device, list[Packet]],
):
    device, commands = connected_panel
    await device.enable_ac_input(True)
    assert commands[-1].payload[0] == 0xFF
    assert commands[-1].payload[6] == 1


async def test_power_hub_dc_circuit_states(device):
    packet = await device.packet_parse(bytes.fromhex(FRAME_DC))
    await device.data_parse(packet)

    # chStates = 0xffde -> circuits 1 and 6 off, the rest on (16 circuits).
    assert device.dc_output_channel_1 is False
    assert device.dc_output_channel_2 is True
    assert device.dc_output_channel_6 is False
    assert device.dc_output_channel_16 is True
    assert hasattr(device, "dc_output_channel_16")
    assert not hasattr(device, "dc_output_channel_17")


async def test_power_hub_dc_circuit_switch_command(device):
    packet = await device.packet_parse(bytes.fromhex(FRAME_DC))
    await device.data_parse(packet)  # loads chStates = 0xffde

    # The switch entity turns circuits on/off via enable_dc_output_channel_{n}.
    # Circuit 1 on flips bit 0: 0xffde -> 0xffdf, sent as 2-byte LE to the panel.
    await device.enable_dc_output_channel_1(True)
    pkt = device._conn.send_packet.call_args[0][0]
    assert (pkt.src, pkt.dst) == (0x21, 0x54)
    assert (pkt.cmd_set, pkt.cmd_id) == (0x54, 0x10)
    assert pkt.payload == bytes.fromhex("dfff")

    # Circuit 2 off flips bit 1: 0xffde -> 0xffdc.
    await device.enable_dc_output_channel_2(False)
    assert device._conn.send_packet.call_args[0][0].payload == bytes.fromhex("dcff")


@pytest.mark.parametrize(
    ("enabled", "expected"),
    [
        (True, [(0x51, 0x50, 0x22), (0x54, 0x54, 0x10)]),
        (False, [(0x54, 0x54, 0x10)]),
    ],
)
async def test_power_hub_turning_circuit_on_enables_dc_ports_first(
    device, enabled, expected
):
    await device.data_parse(await device.packet_parse(bytes.fromhex(FRAME_DC)))
    device._conn.send_packet.reset_mock()

    await device.enable_dc_output_channel_1(enabled)

    sent = [call.args[0] for call in device._conn.send_packet.call_args_list]
    assert [(p.dst, p.cmd_set, p.cmd_id) for p in sent] == expected


async def test_power_hub_dc_circuit_switch_without_states_raises(device):
    with pytest.raises(RuntimeError):
        await device.enable_dc_output_channel_1(True)
    device._conn.send_packet.assert_not_called()


@pytest.mark.parametrize(
    "control",
    [
        "enable_ac_output",
        "enable_dc_ports",
        "enable_dc_output_channel_1",
        "enable_ac_input",
        "enable_dc_input",
        "enable_pv1_input",
        "enable_pv2_input",
    ],
)
async def test_power_hub_disconnected_control_raises(
    mocker: MockerFixture, control: str
) -> None:
    device = Device(
        mocker.Mock(address="AA:BB:CC:DD:EE:FF"),
        mocker.MagicMock(),
        "M3H1TEST_SERIAL",
    )
    await device.data_parse(await device.packet_parse(bytes.fromhex(FRAME_DC)))

    with pytest.raises(NotConnectedError):
        await getattr(device, control)(True)


async def test_power_hub_requests_dc_names(device):
    packet = await device.packet_parse(bytes.fromhex(FRAME_DC))
    await device.data_parse(packet)

    # Seeing the DC panel triggers a circuit-name request (empty read to 0x54/0x54/0x12).
    reqs = [
        c.args[0]
        for c in device._conn.send_packet.call_args_list
        if c.args[0].cmd_set == 0x54 and c.args[0].cmd_id == 0x12
    ]
    assert reqs, "no DC name request was sent"
    assert reqs[0].dst == 0x54
    assert reqs[0].payload == b""


async def test_power_hub_parses_dc_names(panel: Device):
    frame = Packet(
        0x54,
        0x21,
        0x54,
        0x12,
        _dc_metadata_payload([(5, "Water Pump"), (7, "Driver")]),
    ).to_bytes()
    assert await panel.data_parse(await panel.packet_parse(frame))
    assert panel.dc_output_channel_1_name == "Water Pump"
    assert panel.dc_output_channel_2_name == "Driver"
    assert panel.dc_channel_icons == {1: 5, 2: 7}


async def test_power_hub_metadata_publishes_all_circuit_icons(panel: Device):
    metadata = [(n, f"Circuit {n}") for n in range(1, 17)]
    metadata[0] = (5, "Caf\u00e9")
    metadata[-1] = (0, "Spare")
    updates: list[int] = []
    panel.register_state_update_callback(updates.append, "dc_output_channel_16_icon_id")
    for icon_id in (0, 27):
        metadata[-1] = (icon_id, "Spare")
        frame = Packet(
            0x54, 0x21, 0x54, 0x12, _dc_metadata_payload(metadata)
        ).to_bytes()
        await panel.data_parse(await panel.packet_parse(frame))

        for circuit, (expected_icon, name) in enumerate(metadata, start=1):
            assert panel.dc_channel_names[circuit] == name
            assert panel.dc_channel_icon_ids[circuit] == expected_icon

    assert updates == [0, 27]


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x00",
        b"\x00\x11",
        b"\x00\x01" + bytes(4),
        b"\x00\x01" + struct.pack("<IB", 1, 4) + b"ab",
        b"\x00\x01" + struct.pack("<IB", 1, 1) + b"\xff",
        b"\x00\x02"
        + _dc_metadata_payload([(2, "Changed")])[2:]
        + struct.pack("<IB", 3, 5)
        + b"x",
    ],
)
async def test_power_hub_rejects_metadata_without_partial_updates(
    panel: Device, payload: bytes
):
    original = Packet(
        0x54, 0x21, 0x54, 0x12, _dc_metadata_payload([(1, "Original")])
    ).to_bytes()
    await panel.data_parse(await panel.packet_parse(original))
    updates: list[str] = []
    panel.register_state_update_callback(updates.append, "dc_output_channel_1_name")
    malformed = Packet(0x54, 0x21, 0x54, 0x12, payload).to_bytes()

    with pytest.raises(PacketParseError):
        await panel.data_parse(await panel.packet_parse(malformed))

    assert panel.dc_output_channel_1_name == "Original"
    assert panel.dc_output_channel_1_icon_id == 1
    assert updates == []


async def test_power_hub_refreshes_circuit_metadata_after_reconnect(
    panel: Device, monkeypatch: pytest.MonkeyPatch
):
    panel_names = iter(("Lights", "Renamed lights"))

    async def establish(*args: Any, **kwargs: Any) -> Mock:
        panel_name = next(panel_names)
        client = Mock(is_connected=True)
        notify: Callable[[object, bytearray], Awaitable[None]]

        async def subscribe(
            characteristic: object,
            callback: Callable[[object, bytearray], Awaitable[None]],
            **options: Any,
        ) -> None:
            nonlocal notify
            notify = callback

        async def write(
            characteristic: object, data: bytearray, **options: Any
        ) -> None:
            request = Packet.from_bytes(bytes(data))
            assert isinstance(request, Packet)
            if request.cmd_set == 0x35:
                payload = b"\x00"
            elif (request.cmd_set, request.cmd_id) == (0x54, 0x12):
                payload = _dc_metadata_payload([(0, panel_name)])
            else:
                pytest.fail(f"Unexpected request: {request}")
            reply = Packet(
                request.dst, request.src, request.cmd_set, request.cmd_id, payload
            )
            await notify(characteristic, bytearray(reply.to_bytes()))

        async def disconnect() -> None:
            client.is_connected = False
            kwargs["disconnected_callback"](client)

        client.start_notify = AsyncMock(side_effect=subscribe)
        client.write_gatt_char = AsyncMock(side_effect=write)
        client.disconnect = AsyncMock(side_effect=disconnect)
        return client

    monkeypatch.setattr(connection_module, "establish_connection", establish)
    monkeypatch.setattr(
        connection_module, "close_stale_connections_by_address", AsyncMock()
    )
    received = asyncio.Event()
    panel.register_state_update_callback(
        lambda name: received.set(), "dc_output_channel_1_name"
    )
    panel.with_disabled_reconnect()
    try:
        async with asyncio.timeout(2):
            for name in ("Lights", "Renamed lights"):
                await panel.connect(user_id="TEST_USER")
                state = await panel.wait_until_authenticated_or_error(
                    raise_on_error=True
                )
                assert state.authenticated
                await panel.data_parse(
                    await panel.packet_parse(bytes.fromhex(FRAME_DC))
                )
                await received.wait()
                assert panel.dc_output_channel_1_name == name
                await panel.disconnect()
                assert panel.dc_output_channel_1_name == name
                received.clear()
    finally:
        if panel.is_connected:
            await panel.disconnect()


def test_power_hub_switch_entities_are_registered(device):
    # Guard against the switch platform silently dropping the Power Hub switches: every
    # deprecated switch key for this device must be backed by both a state property and
    # an enable_{key} writer (the path the deprecated switch platform uses).
    keys = {d.key for d in DEPRECATED_SWITCH_TYPES}
    for key in [
        "ac_output",
        "ac_input",
        "dc_ports",
        "pv1_input",
        "pv2_input",
        "dc_input",
        *[f"dc_output_channel_{n}" for n in range(1, 17)],
    ]:
        assert key in keys, f"{key} missing from DEPRECATED_SWITCH_TYPES"
        assert hasattr(device, key), f"{key} state property missing"
        assert hasattr(device, f"enable_{key}"), f"enable_{key} writer missing"


async def test_power_hub_field_types_numeric(device):
    for frame in (FRAME_SCC, FRAME_BBC_IN, FRAME_BBC_OUT, FRAME_IC_HIGH):
        packet = await device.packet_parse(bytes.fromhex(frame))
        await device.data_parse(packet)

    numeric_fields = [
        Device.solar_input_power,
        Device.dc_input_power,
        Device.dc_input_voltage,
        Device.dc_output_power,
        Device.dc_output_voltage,
        Device.dc_output_current,
        Device.ac_input_power,
        Device.ac_output_power,
        Device.battery_voltage,
        Device.battery_current,
        Device.ac_inverter_temperature,
    ]
    for field in numeric_fields:
        value = device.get_value(field)
        if value is not None:
            assert isinstance(value, (int, float)), (
                f"Field {field} has wrong type: {type(value)}"
            )
