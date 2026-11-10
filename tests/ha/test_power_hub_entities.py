import json
import struct
from pathlib import Path
from unittest.mock import Mock

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import PlatformData
from homeassistant.helpers.restore_state import RestoreEntity
from pytest_mock import MockerFixture

from custom_components.ef_ble.eflib.devices.power_hub import Device
from custom_components.ef_ble.eflib.packet import Packet
from custom_components.ef_ble.sensor import EcoflowNamedSensor
from custom_components.ef_ble.sensor import async_setup_entry as setup_sensors
from custom_components.ef_ble.switch import async_setup_entry as setup_switches


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


async def _metadata(panel: Device, name: str, icon_id: int, circuit: int = 1) -> None:
    payload = bytearray((0, circuit))
    for channel in range(1, circuit + 1):
        encoded = name.encode("utf-8") if channel == circuit else b""
        payload.extend(struct.pack("<IB", icon_id, len(encoded)))
        payload.extend(encoded)
    frame = Packet(0x54, 0x21, 0x54, 0x12, bytes(payload)).to_bytes()
    await panel.data_parse(await panel.packet_parse(frame))


async def _sensor(panel: Device, quantity: str) -> EcoflowNamedSensor:
    registry = Mock()
    registry.async_get_devices.return_value = []
    registry.async_get_device.return_value = None
    hass = Mock(spec=HomeAssistant, data={dr.DATA_REGISTRY: registry})
    entities: list[Entity] = []
    await setup_sensors(hass, Mock(runtime_data=panel, data={}), entities.extend)
    sensor = next(
        entity
        for entity in entities
        if entity.entity_description.key == f"dc_output_channel_1_{quantity}"
    )
    assert isinstance(sensor, EcoflowNamedSensor)
    platform_data = PlatformData(hass, domain="sensor", platform_name="ef_ble")
    path = (
        Path(__file__)
        .parents[2]
        .joinpath("custom_components", "ef_ble", "translations", "en.json")
    )
    translations = json.loads(path.read_text(encoding="utf-8"))["entity"]["sensor"]
    platform_data.platform_translations = {
        f"component.ef_ble.entity.sensor.{key}.name": value["name"]
        for key, value in translations.items()
        if "name" in value
    }
    sensor.platform_data = platform_data
    return sensor


@pytest.mark.parametrize(
    ("quantity", "label"), [("power", "Power"), ("current", "Current")]
)
async def test_dc_sensor_displays_circuit_name_and_icon_id(
    panel: Device, quantity: str, label: str
):
    sensor = await _sensor(panel, quantity)
    unique_id = sensor.unique_id
    assert sensor.name == f"DC Channel 1 {label}"
    assert sensor.extra_state_attributes == {}

    await _metadata(panel, "Lights", 0)

    assert sensor.name == f"DC Channel 1 Lights {label}"
    assert sensor.extra_state_attributes == {"ecoflow_icon_id": 0}
    assert sensor.unique_id == unique_id


async def test_switch_refreshes_icon_metadata_and_clears_its_name(
    panel: Device, mocker: MockerFixture
):
    await _metadata(panel, "Lights", 12, circuit=16)
    entities: list[Entity] = []
    await setup_switches(Mock(), Mock(runtime_data=panel), entities.extend)
    switch = next(
        entity
        for entity in entities
        if entity.entity_description.key == "dc_output_channel_16"
    )
    write_state = mocker.patch.object(Entity, "async_write_ha_state")
    await switch.async_added_to_hass()
    try:
        await _metadata(panel, "", 12, circuit=16)
        assert switch.name == "DC Channel 16"
        write_state.reset_mock()

        await _metadata(panel, "", 0, circuit=16)

        assert switch.extra_state_attributes == {"ecoflow_icon_id": 0}
        write_state.assert_called()
    finally:
        await switch.async_will_remove_from_hass()


async def test_ac_input_switch_is_discovered_alongside_existing_outputs(panel: Device):
    payload = bytes(49) + b"\x01" + bytes(10) + bytes((1, 230, 60, 15, 0))
    frame = Packet(0x04, 0x21, 0x04, 0x06, payload).to_bytes()
    await panel.data_parse(await panel.packet_parse(frame))
    entities: list[Entity] = []
    await setup_switches(Mock(), Mock(runtime_data=panel), entities.extend)
    switches = {entity.entity_description.key: entity for entity in entities}

    assert switches["ac_input"].is_on is True
    assert switches["ac_output"].is_on is True
    assert switches["ac_input"].unique_id == f"ef_{panel.serial_number}_ac_input"
    assert {
        "dc_ports",
        "dc_input",
        "pv1_input",
        "pv2_input",
        *(f"dc_output_channel_{n}" for n in range(1, 17)),
    } <= switches.keys()


async def test_cleared_sensor_name_replaces_restored_name(
    panel: Device, mocker: MockerFixture
):
    sensor = await _sensor(panel, "power")
    restored = Mock()
    restored.as_dict.return_value = {"name": "Old label"}
    mocker.patch.object(
        RestoreEntity, "async_get_last_extra_data", return_value=restored
    )
    mocker.patch.object(RestoreEntity, "async_added_to_hass")
    mocker.patch.object(RestoreEntity, "async_will_remove_from_hass")
    mocker.patch.object(Entity, "async_write_ha_state")
    await sensor.async_added_to_hass()
    try:
        assert sensor.name == "DC Channel 1 Old label Power"

        await _metadata(panel, "", 0)

        assert sensor.name == "DC Channel 1 Power"
        restored_data = sensor.extra_restore_state_data
        assert restored_data is not None
        assert restored_data.as_dict() == {"name": ""}
    finally:
        await sensor.async_will_remove_from_hass()
