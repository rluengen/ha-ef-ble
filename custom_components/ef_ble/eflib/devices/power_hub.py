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
from ..model.mm100 import BatterySummaryData
from ..packet import Packet
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps

batt = dataclass_attr_mapper(BatterySummaryData)


class Device(DeviceBase, RawDataProps):
    """EcoFlow Power Hub (Power Kit)."""

    SN_PREFIX = (b"M3H1",)
    NAME_PREFIX = "EF-M35"

    # Confirmed from live captures: the battery summary frame (src=0x03, cmd_set=0x03,
    # cmd_id=0x1C) byte 0 is the state of charge (%).
    battery_level = raw_field(batt.soc)

    # TODO(capture): remaining sensors are not yet mapped to real wire offsets. The
    # Power Kit streams per-module frames (now deobfuscated via packet_parse XOR):
    #   0x50/0x50/0x20 = Power Hub   (serial M3H1*)  - system input/output power, etc.
    #   0x03/0x03/0x1A = battery pack (serial M101*) - per-pack voltage/current/temp/SoC
    #   0x02/0x02/0x04 = M1095-PSDL module
    #   0x37/0x37/0x20 = BMS cell voltages (ten 16-bit values)
    # Map each from differential captures (e.g. known load vs. idle) before exposing.

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

    async def packet_parse(self, data: bytes):
        # Power Hub telemetry payloads are XOR-obfuscated with seq[0] (the same scheme
        # ~18 other EcoFlow devices use, e.g. Delta Pro / Wave 2). Undo it here so
        # data_parse sees plaintext. Auth frames carry seq[0] == 0, so the XOR is a
        # no-op for them and the md5 auth handshake is unaffected.
        return Packet.from_bytes(data, xor_payload=True)

    # NOTE: The Power Hub authenticates with the standard local md5(userId + sn)
    # handshake (see connection.autoAuthentication) - the same as other EcoFlow
    # devices. The EcoFlow app's "machine"/getSignatureInfo (0xA8) and cloud
    # cert/token paths were investigated but are NOT used by the consumer Power
    # Hub: the device ignores 0xA8, and the app computes the BLE secret locally as
    # MD5(numeric userId + sn) (decompiled from d2.o -> f0.V -> MD5). So we leave
    # both uses_machine_auth and uses_cert_auth at their False defaults and rely on
    # the base md5 auth. The critical requirement is that the configured user id is
    # the *numeric* EcoFlow account id, not the account email.

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

        # TODO(capture): route each module frame to its struct as offsets are mapped.
        # Battery summary -> state of charge (byte 0).
        if (packet.src, packet.cmd_set, packet.cmd_id) == (0x03, 0x03, 0x1C):
            self.update_from_bytes(BatterySummaryData, packet.payload)
            processed = True

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name, None))

        return processed
