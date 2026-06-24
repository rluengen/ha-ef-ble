"""
EcoFlow Power Hub (MM100 / "Power Kit") device - WORK IN PROGRESS / SKELETON.

The Power Hub speaks the standard EcoFlow BLE framing (handled by ``Packet``) but, unlike
the protobuf devices, reports each internal sub-module as a packed fixed-width binary
payload. The struct layouts live in ``..model.mm100`` and were recovered from the EcoFlow
Android app parser; see that module for caveats.

STATUS - this is a scaffold to be finalised against a live decrypted capture:
  * ``data_parse`` currently logs every frame and routes sub-module payloads by their
    (distinct) byte length as a TEMPORARY heuristic. The real routing is by
    ``(src, cmd_set, cmd_id)`` and must be filled in from a capture (see the ``match``
    template in ``data_parse``).
  * Sensor values are raw (un-scaled). Real units/scaling (mV/mA -> V/A, etc.) need to be
    confirmed from the capture and applied via ``transform`` (e.g. ``pround``/``pdiv``).
  * Only a representative subset of fields is surfaced; multiple SCC/BBC/BMS instances are
    addressed by ``dsrc`` and need per-address handling (not yet implemented).
  * No write/command support yet (``cmd_set``/``cmd_id`` unknown until capture).
  * Entity descriptions (sensor.py registration, translations, icons) are a follow-up.
"""

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..commands import TimeCommands
from ..devicebase import DeviceBase
from ..logging_util import LogOptions
from ..model.mm100 import (
    BbcInData,
    BbcOutData,
    BmsData,
    BmsTotalData,
    IcHighData,
    InvData,
    SccData,
)
from ..packet import Packet
from ..props import Field
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps

scc = dataclass_attr_mapper(SccData)
bbc_in = dataclass_attr_mapper(BbcInData)
bbc_out = dataclass_attr_mapper(BbcOutData)
inv = dataclass_attr_mapper(InvData)
bms = dataclass_attr_mapper(BmsData)
ic = dataclass_attr_mapper(IcHighData)
total = dataclass_attr_mapper(BmsTotalData)

# TEMP: sub-module payloads have distinct lengths, so until the (src, cmd_set, cmd_id)
# routing is confirmed from a capture we tentatively dispatch by exact payload size.
# (InvData/IcHighData are omitted: their real payloads are longer than the partial structs
# currently defined, so an exact-size match would never fire for them.)
_SIZE_TO_MODEL = {
    SccData.SIZE: SccData,
    BbcInData.SIZE: BbcInData,
    BbcOutData.SIZE: BbcOutData,
    BmsData.SIZE: BmsData,
    BmsTotalData.SIZE: BmsTotalData,
}


class Device(DeviceBase, RawDataProps):
    """EcoFlow Power Hub (Power Kit)."""

    SN_PREFIX = (b"M3H1",)
    NAME_PREFIX = "EF-M35"

    # --- System totals (BmsTotalData) ---
    battery_level = raw_field(total.total_soc)
    input_power = raw_field(total.total_input_watt)
    output_power = raw_field(total.total_output_watt)
    remaining_time = raw_field(total.total_remain_time)

    # --- Solar / MPPT (SccData) ---
    solar_pv1_power = raw_field(scc.pv1_in_watt)
    solar_pv2_power = raw_field(scc.pv2_in_watt)
    solar_input_power = Field[int]()  # computed: pv1 + pv2

    # --- DC-DC input: alternator / vehicle / solar (BbcInData) ---
    dc_input_power = raw_field(bbc_in.dc_input_watt)

    # --- DC-DC output: DC loads (BbcOutData) ---
    dc_output_power = raw_field(bbc_out.ld_out_watt)

    # --- AC inverter / charger (IcHighData) ---
    ac_input_power = raw_field(ic.in_watt)
    ac_output_power = raw_field(ic.out_watt)

    # --- Battery pack (BmsData; single instance for now) ---
    battery_pack_soc = raw_field(bms.soc)
    battery_pack_voltage = raw_field(bms.vol)
    battery_pack_current = raw_field(bms.amp)
    battery_pack_temperature = raw_field(bms.temp)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        # Many EcoFlow devices only start streaming after the app answers a time request.
        self._time_commands = TimeCommands(device=self)

    @classmethod
    def check(cls, sn: bytes) -> bool:
        return sn[:4] in cls.SN_PREFIX

    @property
    def device(self):
        return "EcoFlow Power Hub"

    @property
    def packet_version(self):
        # Provisional: unknown M3-series prefix defaults to v3 (same as unsupported path).
        # Confirm from the capture's connection log.
        return 3

    @property
    def uses_machine_auth(self):
        # Power Kit / "Space" devices (Power Hub) authenticate fully locally over
        # BLE: the device issues its own per-(user, device) signature which we
        # replay to authenticate. No cloud token/cert is involved.
        return True

    async def data_parse(self, packet: Packet) -> bool:
        self.reset_updated()
        processed = False

        # Log every frame so a capture reveals the per-sub-module (src, cmd_set, cmd_id).
        self._logger.log_filtered(
            LogOptions.DESERIALIZED_MESSAGES,
            "PowerHub frame src=0x%02X dst=0x%02X dsrc=0x%02X cmd_set=0x%02X "
            "cmd_id=0x%02X len=%d payload=%s",
            packet.src,
            packet.dst,
            packet.dsrc,
            packet.cmd_set,
            packet.cmd_id,
            len(packet.payload),
            packet.payload_hex,
        )

        # Respond to the device's time request so it starts streaming telemetry.
        if (
            packet.src == 0x35
            and packet.cmd_set == 0x01
            and packet.cmd_id == Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME
        ):
            if len(packet.payload) == 0:
                self._time_commands.async_send_all()
            return True

        # TODO(capture): replace this TEMP size-based dispatch with explicit routing, e.g.
        #   match (packet.src, packet.cmd_set, packet.cmd_id):
        #       case 0x??, 0x??, 0x??:
        #           self.update_from_bytes(SccData, packet.payload)
        #           processed = True
        #       case 0x??, 0x??, 0x??:
        #           self.update_from_bytes(BmsData, packet.payload)
        #           processed = True
        #       ...
        model = _SIZE_TO_MODEL.get(len(packet.payload))
        if model is not None:
            self.update_from_bytes(model, packet.payload)
            processed = True

            if model is SccData:
                self.solar_input_power = (self.solar_pv1_power or 0) + (
                    self.solar_pv2_power or 0
                )

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name, None))

        return processed
