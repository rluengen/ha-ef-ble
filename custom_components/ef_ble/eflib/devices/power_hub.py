"""
EcoFlow Power Hub (MM100 / "Power Kit").

The Power Hub speaks the standard EcoFlow BLE framing (handled by ``Packet``) but, unlike
the protobuf devices, reports each internal sub-module as a packed fixed-width binary
payload. The struct layouts live in ``..model.mm100`` and were recovered from - and
validated against - the EcoFlow Android app packet parser plus ~15k live decrypted frames.

Auth is the standard local ``md5(numeric userId + sn)`` handshake; telemetry payloads are
XOR-obfuscated with ``seq[0]`` (undone in :meth:`packet_parse`). Each sub-module frame is
routed by ``(src, cmd_set, cmd_id)`` in :meth:`data_parse` to its ``RawData`` struct.

Currently surfaced: system SoC / input / output power, plus per-module solar, DC input,
DC output and AC inverter power/voltage/current and battery bus voltage/current.

Still to do: AC-inverter on/off write control; per-pack BMS detail (multiple ``M101*``
packs addressed by ``dsrc``); AC/DC distribution-panel per-circuit arrays; generator.
"""

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..commands import TimeCommands
from ..devicebase import DeviceBase
from ..logging_util import LogOptions
from ..model.mm100 import (
    BbcInData,
    BbcOutData,
    BmsTotalData,
    IcHighData,
    SccData,
)
from ..packet import Packet
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps
from ..props.transforms import pdiv

total = dataclass_attr_mapper(BmsTotalData)
scc = dataclass_attr_mapper(SccData)
bbc_in = dataclass_attr_mapper(BbcInData)
bbc_out = dataclass_attr_mapper(BbcOutData)
ic_high = dataclass_attr_mapper(IcHighData)

# Raw telemetry units: voltages are mV, currents mA, power whole watts. Scale to
# V/A for the corresponding Home Assistant device classes; watts are used as-is.
_mv_to_v = pdiv(1000, 2)
_ma_to_a = pdiv(1000, 2)


class Device(DeviceBase, RawDataProps):
    """EcoFlow Power Hub (Power Kit)."""

    SN_PREFIX = (b"M3H1",)
    NAME_PREFIX = "EF-M35"

    # -- System totals (BmsTotalData, frame 0x03/0x03/0x1C). Verified against live
    #    captures: totalSoc (0x36->54%, 0x32->50%) and totalInputWatt (0 while idle).
    battery_level = raw_field(total.total_soc)
    input_power = raw_field(total.total_input_watt)
    output_power = raw_field(total.total_output_watt)

    # -- Solar MPPT input (SccData, frame 0x05/0x05/0x20). PV1/PV2 charge power.
    solar_input_power = raw_field(scc.pv1_in_watt)
    solar_input_power_2 = raw_field(scc.pv2_in_watt)

    # -- DC / alternator input (BbcInData, frame 0x50/0x50/0x20) - the hub module.
    #    Also the source for the shared 48V battery bus voltage/current.
    dc_input_power = raw_field(bbc_in.dc_input_watt)
    dc_input_voltage = raw_field(bbc_in.dc_input_vol, _mv_to_v)
    dc_input_current = raw_field(bbc_in.dc_input_cur, _ma_to_a)
    battery_voltage = raw_field(bbc_in.battery_vol, _mv_to_v)
    battery_current = raw_field(bbc_in.battery_cur, _ma_to_a)

    # -- DC output / loads (BbcOutData, frame 0x51/0x51/0x20).
    dc_output_power = raw_field(bbc_out.ld_out_watt)
    dc_output_voltage = raw_field(bbc_out.ld_out_vol, _mv_to_v)
    dc_output_current = raw_field(bbc_out.ld_out_cur, _ma_to_a)

    # -- AC inverter/charger (IcHighData, frame 0x04/0x04/0x06). in_* = AC charging,
    #    out_* = AC inverter output; inv_switch_state is the AC inverter on/off state.
    ac_input_power = raw_field(ic_high.in_watt)
    ac_input_voltage = raw_field(ic_high.in_vol, _mv_to_v)
    ac_output_power = raw_field(ic_high.out_watt)
    ac_output_voltage = raw_field(ic_high.out_vol, _mv_to_v)
    ac_output_current = raw_field(ic_high.out_cur, _ma_to_a)
    ac_inverter_temperature = raw_field(ic_high.ac_temp)

    # AC inverter on/off state (IcHigh.invSwitchState: 1 = on). Backs the "AC Output"
    # switch entity (see deprecated/switches.py) and its enable_ac_output writer below.
    ac_output = raw_field(ic_high.inv_switch_state, lambda x: x == 1)

    # Each I/O sub-module frame is routed by (src, cmd_set, cmd_id) - where src, cmd_set
    # and the module bus address are equal - to its RawData struct in data_parse().
    _MODULE_FRAMES = {
        (0x03, 0x03, 0x1C): BmsTotalData,
        (0x05, 0x05, 0x20): SccData,
        (0x50, 0x50, 0x20): BbcInData,
        (0x51, 0x51, 0x20): BbcOutData,
        (0x04, 0x04, 0x06): IcHighData,
    }

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

        # Route each mapped sub-module frame to its RawData struct.
        model = self._MODULE_FRAMES.get(
            (packet.src, packet.cmd_set, packet.cmd_id)
        )
        if model is not None:
            self.update_from_bytes(model, packet.payload)
            processed = True

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name, None))

        return processed

    async def _send_config_packet(
        self, dst: int, cmd_set: int, cmd_id: int, payload: bytes
    ) -> None:
        packet = Packet(
            src=0x21,
            dst=dst,
            cmd_set=cmd_set,
            cmd_id=cmd_id,
            payload=payload,
            version=self.packet_version,
        )
        await self._conn.sendPacket(packet)

    async def enable_ac_output(self, enabled: bool) -> None:
        """
        Turn the AC inverter output on/off.

        Command recovered from the EcoFlow app: the "AC Output" switch
        (MM100OutputViewModel, analytics tag ``ac_output_switch``) dispatches to
        ``ud.x0.h1`` which sends a 10-byte payload to the inverter module (dst 0x02,
        cmd_set 0x02, cmd_id 0x07). Byte 0 is the on/off flag; the 0xFF bytes mark the
        other AC settings as "leave unchanged".
        """
        onoff = 0x01 if enabled else 0x00
        payload = bytes(
            (onoff, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0xFF, 0xFF, 0xFF)
        )
        await self._send_config_packet(0x02, 0x02, 0x07, payload)
