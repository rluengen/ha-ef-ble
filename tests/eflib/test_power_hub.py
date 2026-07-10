import pytest
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.power_hub import Device

# Raw decrypted BLE frames (payloads still XOR-obfuscated) captured from a live Power Hub;
# power_hub.packet_parse un-XORs them. One telemetry frame per sub-module.
FRAME_SCC = "aa038800c02c74b48300043e0521010005203945444d425939242420594642354647747474747474747427747570fabb74747474747474747474ca00747474747474747474747474747474747474747474745a757474d37574745774517474747576757575747474747474747474747474742c7674742c7674747474747474747474747474740f74f17475757675757474747474747474747474ec79"
FRAME_BBC_IN = "aa037400282c98a1a900023e502101005020d5abd0a9dba8a9aba0dfa0afa8a9abab88bf98989299999de7fe9898749c9898b9989898a1569898a0999898889898983e98989821989898bb98bc98be989998d80498984a9c98988d9b9898999f999a9999c09a98989898989898989898e39899989898989a98989898989898989898989898986f9e"
FRAME_BBC_OUT = "aa037400282cf6d14500033e512101005120bbc5bec7c3c6c7c4ceb1cec7c6c2c7c56eccf6f69ef6f7f36d3bf6f691f1f6f695f6f6f6dec3f6f61ee4f6f6b7f6f6f6eceef6f61bf4f6f6c5f6f6f6f6f6f4f7f6f6f6f6c1c6f6f67dc7f7f6f6f6f6f6f6f6f7f1f3f6f6f6f6f6f6f6f6f6fcf6f7f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6cb75"
FRAME_IC_HIGH = "aa036300142cf21d2001063e042101000406bfc3c2cbc7dfa2a1b6badfc1c6c4cbc1f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2d6f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f28acefdf3f3f2fdf2f2f2f2f2f2f2f2f2f202f2f3f2f3f3c0f2f2f2f2f2f2f2f2f2f2f2f2f2f2cc02"


@pytest.fixture
def device(mocker: MockerFixture):
    ble_dev = mocker.Mock()
    ble_dev.address = "AA:BB:CC:DD:EE:FF"
    adv_data = mocker.MagicMock()
    device = Device(ble_dev, adv_data, "M3H1ZAB4H3C0207")
    device._conn = mocker.AsyncMock()
    return device


@pytest.mark.parametrize(
    ("frame", "src", "cmd_set", "cmd_id"),
    [
        (FRAME_SCC, 0x05, 0x05, 0x20),
        (FRAME_BBC_IN, 0x50, 0x50, 0x20),
        (FRAME_BBC_OUT, 0x51, 0x51, 0x20),
        (FRAME_IC_HIGH, 0x04, 0x04, 0x06),
    ],
)
async def test_power_hub_routes_and_processes_frames(device, frame, src, cmd_set, cmd_id):
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


async def test_power_hub_dc_output(device):
    packet = await device.packet_parse(bytes.fromhex(FRAME_BBC_OUT))
    await device.data_parse(packet)

    # ldOutWatt=65 W, ldOutVol=13608 mV, ldOutCur=4840 mA (12 V nominal DC load bus).
    assert device.get_value(Device.dc_output_power) == 65
    assert device.get_value(Device.dc_output_voltage) == pytest.approx(13.61, abs=0.01)
    assert device.get_value(Device.dc_output_current) == pytest.approx(4.84, abs=0.01)


async def test_power_hub_ac_inverter(device):
    packet = await device.packet_parse(bytes.fromhex(FRAME_IC_HIGH))
    await device.data_parse(packet)

    # AC inverter idle: no input/output power, heat-sink at 36 C.
    assert device.get_value(Device.ac_input_power) == 0
    assert device.get_value(Device.ac_output_power) == 0
    assert device.get_value(Device.ac_inverter_temperature) == 36


async def test_power_hub_solar_input_present(device):
    packet = await device.packet_parse(bytes.fromhex(FRAME_SCC))
    await device.data_parse(packet)

    assert Device.solar_input_power.public_name in device.updated_fields
    assert isinstance(device.get_value(Device.solar_input_power), (int, float))


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
