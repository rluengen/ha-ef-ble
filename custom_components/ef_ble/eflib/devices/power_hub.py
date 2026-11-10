"""
EcoFlow Power Hub (MM100 / "Power Kit").

The Power Hub speaks the standard EcoFlow BLE framing (handled by ``Packet``) but, unlike
the protobuf devices, reports each internal sub-module as a packed fixed-width binary
payload. The struct layouts live in ``..model.mm100`` and were recovered from - and
validated against - the EcoFlow Android app packet parser plus ~15k live decrypted frames.

Auth is the standard local ``md5(numeric userId + sn)`` handshake; telemetry payloads are
XOR-obfuscated with ``seq[0]`` (undone in :meth:`packet_parse`). Each sub-module frame is
routed by ``(src, cmd_set, cmd_id)`` in :meth:`data_parse` to its ``RawData`` struct.

Currently surfaced: system totals, battery charge limits and remaining time, PV input
voltage/current, solar controller temperatures, daily AC energy, AC/DC/PV input
on/off, module telemetry, 16 DC circuit measurements and switches, the DC output master
switch, app-derived circuit names/icon identifiers, 6 AC circuit measurements and
per-pack battery data for up to 9 packs. The AC circuit, charge limit, remaining time
and per-pack layouts come from the app parser and have not yet been seen in a capture.
"""

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..commands import TimeCommands
from ..connection import ConnectionState
from ..devicebase import DeviceBase
from ..entity import controls
from ..exceptions import PacketParseError
from ..logging_util import LogOptions
from ..model.mm100 import (
    ACData,
    BbcInData,
    BbcOutData,
    BmsData,
    BmsTotalData,
    DCData,
    IcHighData,
    ModuleStateData,
    SccData,
)
from ..packet import Packet
from ..props import Field, computed_field, field_group
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps
from ..props.transforms import pdiv

total = dataclass_attr_mapper(BmsTotalData)
scc = dataclass_attr_mapper(SccData)
bbc_in = dataclass_attr_mapper(BbcInData)
bbc_out = dataclass_attr_mapper(BbcOutData)
ic_high = dataclass_attr_mapper(IcHighData)
dc = dataclass_attr_mapper(DCData)
ac_panel = dataclass_attr_mapper(ACData)

# Raw telemetry units: voltages are mV, currents mA, power whole watts. Scale to
# V/A for the corresponding Home Assistant device classes; watts are used as-is.
# Currents keep three decimals so even a few milliamps of draw is not rounded to 0.
_mv_to_v = pdiv(1000, 2)
_ma_to_a = pdiv(1000, 3)
_cell_mv_to_v = pdiv(1000, 3)


def _decode_sn(sn: bytes) -> str:
    return sn.rstrip(b"\x00").decode("ascii", errors="replace")


def _bit_state(bit: int):
    """Return a transform reading a single circuit's on/off bit from a state bitmask."""
    return lambda mask: bool((mask >> bit) & 1)


def _equals(on_value: int):
    """Return a transform reading an on/off flag, keeping an unknown value unknown."""
    return lambda x: None if x is None else x == on_value


def _pack_slot(custom: int) -> int | None:
    """
    Map a pack's module-state ``custom`` word to its slot (1-9), as the app does.

    The app (``y50.k``) reads a group from bits 8-15 and a position from bits 0-7: group
    0 is the slot under the hub (2, 5 or 8 for position 1, 2 or other), groups 1-3 each
    hold three slots. Packs in any other group are shown as abnormal and skipped.
    """
    group = (custom >> 8) & 0xFF
    position = custom & 0xFF
    if group == 0:
        slot = {1: 2, 2: 5}.get(position, 8)
    elif group in (1, 2, 3):
        slot = position + (group - 1) * 3
    else:
        return None
    return slot if 1 <= slot <= Device.NUM_BATTERY_SLOTS else None


def _make_circuit_enable(circuit: int):
    """Return an ``enable_dc_output_channel_{n}`` coroutine bound to a circuit index."""

    async def _enable(self: "Device", enabled: bool) -> None:
        await self.set_dc_circuit(circuit, enabled)

    return _enable


class Device(DeviceBase, RawDataProps):
    """EcoFlow Power Hub (Power Kit)."""

    SN_PREFIX = (b"M3H1",)
    NAME_PREFIX = "EF-M35"
    NUM_DC_CIRCUITS = 16
    NUM_AC_CIRCUITS = 6
    NUM_BATTERY_SLOTS = 9

    extra_battery_name = "Power Kit Battery"

    # -- System totals (BmsTotalData, frame 0x03/0x03/0x1C). Verified against live
    #    captures: totalSoc (0x36->54%, 0x32->50%) and totalInputWatt (0 while idle).
    battery_level = raw_field(total.total_soc)
    input_power = raw_field(total.total_input_watt)
    output_power = raw_field(total.total_output_watt)

    # Charge limits and remaining time, read as the app does: the system-wide stop SOCs
    # from the totals frame, falling back to the packs' own set SOCs while the totals
    # report neither (``y50.k`` N/Q), and the remaining minutes shown as time to full
    # while charging (state 2) or time to empty while discharging (state 1).
    _bms_chg_stop_soc = raw_field(total.bms_chg_stop_soc)
    _bms_dsg_stop_soc = raw_field(total.bms_dsg_stop_soc)
    _total_chg_dsg_state = raw_field(total.total_chg_dsg_state)
    _total_remain_time = raw_field(total.total_remain_time)
    is_charging = raw_field(total.total_chg_dsg_state, _equals(2))
    _pack_chg_set_soc = Field[int]()
    _pack_dsg_set_soc = Field[int]()

    @computed_field
    def battery_charge_limit_max(self) -> int | None:
        if self._bms_chg_stop_soc or self._bms_dsg_stop_soc:
            return self._bms_chg_stop_soc
        return self._pack_chg_set_soc

    @computed_field
    def battery_charge_limit_min(self) -> int | None:
        if self._bms_chg_stop_soc or self._bms_dsg_stop_soc:
            return self._bms_dsg_stop_soc
        return self._pack_dsg_set_soc

    @computed_field
    def remaining_time_charging(self) -> int | None:
        return self._total_remain_time if self._total_chg_dsg_state == 2 else None

    @computed_field
    def remaining_time_discharging(self) -> int | None:
        return self._total_remain_time if self._total_chg_dsg_state == 1 else None

    # -- Solar MPPT input (SccData, frame 0x05/0x05/0x20). PV1/PV2 charge power.
    solar_input_power = raw_field(scc.pv1_in_watt)
    solar_input_power_2 = raw_field(scc.pv2_in_watt)
    pv_voltage = field_group(
        lambda n: raw_field(getattr(scc, f"pv{n}_in_vol"), _mv_to_v),
        count=2,
        name_template="pv_voltage_{n}",
    )
    pv_current = field_group(
        lambda n: raw_field(getattr(scc, f"pv{n}_in_cur"), _ma_to_a),
        count=2,
        name_template="pv_current_{n}",
    )
    # `p50.g.E0` reads signed temperatures at bytes 72, 74 and 76.
    solar_heatsink_temperature = field_group(
        lambda n: raw_field(getattr(scc, f"hs{n}_temp")),
        count=2,
        name_template="solar_heatsink_{n}_temperature",
    )
    solar_pcb_temperature = raw_field(scc.pcb_temp)

    # PV input on/off (Scc.mppt{n}SwitchState: 1 = on), as the app's input page reads
    # it. Back the "PV1/PV2 Input" switch entities and the enable_pv*_input writers.
    pv1_input = raw_field(scc.mppt1_switch_state, _equals(1))
    pv2_input = raw_field(scc.mppt2_switch_state, _equals(1))

    # -- DC / alternator input (BbcInData, frame 0x50/0x50/0x20) - the hub module.
    #    Also the source for the shared 48V battery bus voltage/current.
    dc_input_power = raw_field(bbc_in.dc_input_watt)
    dc_input_voltage = raw_field(bbc_in.dc_input_vol, _mv_to_v)
    dc_input_current = raw_field(bbc_in.dc_input_cur, _ma_to_a)
    battery_voltage = raw_field(bbc_in.battery_vol, _mv_to_v)
    battery_current = raw_field(bbc_in.battery_cur, _ma_to_a)

    # DC/alternator input on/off (BbcIn.chargePause: 0 = charging allowed), as the app's
    # input page reads it. Backs the "DC Input" switch and its enable_dc_input writer.
    dc_input = raw_field(bbc_in.charge_pause, _equals(0))

    # -- DC output / loads (BbcOutData, frame 0x51/0x51/0x20).
    dc_output_power = raw_field(bbc_out.ld_out_watt)
    dc_output_voltage = raw_field(bbc_out.ld_out_vol, _mv_to_v)
    dc_output_current = raw_field(bbc_out.ld_out_cur, _ma_to_a)

    # DC output master on/off (BbcOut.dcSwitchMode: 1 = on), as the app's output page
    # reads it. Backs the "DC Ports" switch entity and its enable_dc_ports writer below.
    dc_ports = raw_field(bbc_out.dc_switch_mode, lambda x: x == 1)

    # -- AC inverter/charger (IcHighData, frame 0x04/0x04/0x06). in_* = AC charging,
    #    out_* = AC inverter output; inv_switch_state is the AC inverter on/off state.
    ac_input_power = raw_field(ic_high.in_watt)
    ac_input_voltage = raw_field(ic_high.in_vol, _mv_to_v)
    ac_output_power = raw_field(ic_high.out_watt)
    ac_output_voltage = raw_field(ic_high.out_vol, _mv_to_v)
    ac_output_current = raw_field(ic_high.out_cur, _ma_to_a)
    ac_inverter_temperature = raw_field(ic_high.ac_temp)

    # `IcHighDataBean` calls these inputWhInDay/outputWhInDay, not lifetime totals.
    ac_input_energy_today = raw_field(ic_high.day_input_energy)
    ac_output_energy_today = raw_field(ic_high.day_output_energy)

    # The input page (`i50.r.L0`) treats acChgDisable == 0 as charging enabled.
    ac_input = raw_field(ic_high.ac_chg_disable, _equals(0))

    # AC inverter on/off state (IcHigh.invSwitchState: 1 = on). Backs the "AC Output"
    # switch entity (see deprecated/switches.py) and its enable_ac_output writer below.
    ac_output = raw_field(ic_high.inv_switch_state, lambda x: x == 1)

    # -- DC distribution panel (DCData, frame 0x54/0x54/0x20): 16 DC output channels.
    #    Expose per-channel power (W) and current (mA->A). Attributes are generated
    #    dynamically as dc_output_channel_{n}_power/_current for n in 1..16, matching
    #    the indexed sensor keys in sensor.py.
    for _n in range(1, NUM_DC_CIRCUITS + 1):
        vars()[f"dc_output_channel_{_n}_power"] = raw_field(
            getattr(dc, f"ch{_n}_power")
        )
        vars()[f"dc_output_channel_{_n}_current"] = raw_field(
            getattr(dc, f"ch{_n}_current"), _ma_to_a
        )
    del _n

    # DC circuit on/off states: the panel reports all 16 switchable circuits as the
    # 16-bit chStates bitmask (bit i = circuit i+1). dc_ch_states holds the raw mask
    # (used to rebuild the command); dc_output_channel_{n} is each circuit's bool state
    # and backs the "DC Channel {n}" switch entities (see deprecated/switches.py).
    dc_ch_states = raw_field(dc.ch_states)
    for _c in range(1, NUM_DC_CIRCUITS + 1):
        vars()[f"dc_output_channel_{_c}"] = raw_field(dc.ch_states, _bit_state(_c - 1))
        vars()[f"enable_dc_output_channel_{_c}"] = _make_circuit_enable(_c)
    del _c

    dc_channel_names = field_group(
        lambda _: Field[str](),
        count=NUM_DC_CIRCUITS,
        name_template="dc_output_channel_{n}_name",
    )
    dc_channel_icon_ids = field_group(
        lambda _: Field[int](),
        count=NUM_DC_CIRCUITS,
        name_template="dc_output_channel_{n}_icon_id",
    )

    # -- AC distribution panel (ACData, frame 0x53/0x53/0x20): 6 AC output circuits,
    #    shown in the app as power (W) and current (mA->A) per circuit.
    ac_channel_power = field_group(
        lambda n: raw_field(getattr(ac_panel, f"ch{n}_power")),
        count=NUM_AC_CIRCUITS,
        name_template="ac_output_channel_{n}_power",
    )
    ac_channel_current = field_group(
        lambda n: raw_field(getattr(ac_panel, f"ch{n}_current"), _ma_to_a),
        count=NUM_AC_CIRCUITS,
        name_template="ac_output_channel_{n}_current",
    )

    # -- Battery packs (BmsData, frame 0x03/0x03/0x1A), one slot per position in the
    #    app's battery view. Each pack frame carries its serial, and the module-state
    #    frame 0x35/0x35/0x11 places each serial in a slot (see _pack_slot).
    pack_enabled = field_group(
        lambda _: Field[bool](), NUM_BATTERY_SLOTS, name_template="battery_{n}_enabled"
    )
    pack_sn = field_group(
        lambda _: Field[str](), NUM_BATTERY_SLOTS, name_template="battery_{n}_sn"
    )
    pack_level = field_group(
        lambda _: Field[int](),
        NUM_BATTERY_SLOTS,
        name_template="battery_{n}_battery_level",
    )
    pack_temperature = field_group(
        lambda _: Field[int](),
        NUM_BATTERY_SLOTS,
        name_template="battery_{n}_cell_temperature",
    )
    pack_voltage = field_group(
        lambda _: Field[float](),
        NUM_BATTERY_SLOTS,
        name_template="battery_{n}_voltage",
    )
    pack_max_cell_voltage = field_group(
        lambda _: Field[float](),
        NUM_BATTERY_SLOTS,
        name_template="battery_{n}_max_cell_voltage",
    )
    pack_min_cell_voltage = field_group(
        lambda _: Field[float](),
        NUM_BATTERY_SLOTS,
        name_template="battery_{n}_min_cell_voltage",
    )
    pack_input_power = field_group(
        lambda _: Field[int](),
        NUM_BATTERY_SLOTS,
        name_template="battery_{n}_input_power",
    )
    pack_output_power = field_group(
        lambda _: Field[int](),
        NUM_BATTERY_SLOTS,
        name_template="battery_{n}_output_power",
    )

    # Each I/O sub-module frame is routed by (src, cmd_set, cmd_id) - where src, cmd_set
    # and the module bus address are equal - to its RawData struct in data_parse().
    _MODULE_FRAMES = {
        (0x03, 0x03, 0x1C): BmsTotalData,
        (0x05, 0x05, 0x20): SccData,
        (0x50, 0x50, 0x20): BbcInData,
        (0x51, 0x51, 0x20): BbcOutData,
        (0x04, 0x04, 0x06): IcHighData,
        (0x54, 0x54, 0x20): DCData,
        (0x53, 0x53, 0x20): ACData,
    }

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        # Many EcoFlow devices only start streaming after the app answers a time request.
        self._time_commands = TimeCommands(device=self)
        # Circuit names are not in the periodic telemetry - they are requested from the
        # DC panel once it is seen. Track load state and cap the number of requests.
        self._dc_names_loaded = False
        self._dc_name_requests = 0
        # Latest data per pack and the slot of each connected pack, both keyed by the
        # pack serial; they arrive in separate frames and either may come first.
        self._packs: dict[str, BmsData] = {}
        self._pack_slots: dict[str, int] | None = None
        self.on_connection_state_change(self._reset_dc_metadata)

    def _reset_dc_metadata(self, state: ConnectionState) -> None:
        if state.authenticated:
            self._dc_names_loaded = False
            self._dc_name_requests = 0

    @property
    def dc_channel_icons(self) -> dict[int, int]:
        return {
            circuit: icon_id
            for circuit in range(1, self.NUM_DC_CIRCUITS + 1)
            if (icon_id := self.dc_channel_icon_ids[circuit]) is not None
        }

    @classmethod
    def check(cls, sn: bytes) -> bool:
        return sn[:4] in cls.SN_PREFIX

    @property
    def device(self):
        return "EcoFlow Power Hub"

    @property
    def packet_version(self):
        # The app sends Power Hub (product type 62) commands as protocol version 3.
        return 3

    async def packet_parse(self, data: bytes):
        # Power Hub telemetry payloads are XOR-obfuscated with seq[0] (the same scheme
        # ~18 other EcoFlow devices use, e.g. Delta Pro / Wave 2). Undo it here so
        # data_parse sees plaintext. Auth frames carry seq[0] == 0, so the XOR is a
        # no-op for them and the md5 auth handshake is unaffected.
        return Packet.from_bytes(data, xor_payload=True)

    # NOTE: The Power Hub authenticates with the standard local md5(userId + sn)
    # handshake (see connection._auto_authentication) - the same as other EcoFlow
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

        # DC distribution panel circuit names (request-driven, parser ld.f.J).
        if (packet.src, packet.cmd_set, packet.cmd_id) == (0x54, 0x54, 0x12):
            self._parse_dc_names(packet.payload)
            self._notify_updated()
            return True

        if (packet.src, packet.cmd_set, packet.cmd_id) == (0x35, 0x35, 0x11):
            self._parse_module_states(packet.payload)
            self._notify_updated()
            return True

        if (packet.src, packet.cmd_set, packet.cmd_id) == (0x03, 0x03, 0x1A):
            self._parse_pack(packet.payload)
            self._notify_updated()
            return True

        # Route each mapped sub-module frame to its RawData struct.
        model = self._MODULE_FRAMES.get((packet.src, packet.cmd_set, packet.cmd_id))
        if model is not None:
            self.update_from_bytes(model, packet.payload)
            processed = True
            # The panel does not stream circuit names; ask for them once it appears.
            if (
                model is DCData
                and not self._dc_names_loaded
                and self._dc_name_requests < 5
            ):
                self._dc_name_requests += 1
                await self._send_config_packet(0x54, 0x54, 0x12, b"")

        self._notify_updated()
        return processed

    def _parse_module_states(self, payload: bytes) -> None:
        """
        Place each connected pack in its slot from the module-state frame.

        Layout and validation follow the app parser (``p50.g.p0``): a list of 34-byte
        records, dropped whole if any record has an out-of-range run state or a negative
        bus address. Every frame lists all connected modules, so it replaces the slots.
        """
        size = ModuleStateData.SIZE
        records = [
            ModuleStateData.from_bytes(payload[offset : offset + size])
            for offset in range(0, len(payload) - size + 1, size)
        ]
        if not records or any(
            not 0 <= r.run_state <= 1 or r.src_addr < 0 for r in records
        ):
            self._logger.debug("Ignoring invalid module state frame: %s", payload.hex())
            return

        self._pack_slots = {
            _decode_sn(r.sn): slot
            for r in records
            if r.src_addr == 3 and (slot := _pack_slot(r.custom)) is not None
        }
        self._update_pack_slots()

    def _parse_pack(self, payload: bytes) -> None:
        """
        Store a battery pack's data from its frame and update its slot.

        The app parser (``p50.g.A``) drops frames shorter than the base struct or with
        an out-of-range PTC heater flag; we do the same.
        """
        if len(payload) < BmsData.BASE_SIZE:
            self._logger.debug("Ignoring truncated pack frame: %s", payload.hex())
            return
        pack = BmsData.from_bytes(payload)
        if not (
            0 <= pack.ptc_allow_flag <= 1
            and 0 <= pack.ptc_touch_flag <= 2
            and 0 <= pack.ptc_heating_state <= 2
        ):
            self._logger.debug("Ignoring invalid pack frame: %s", payload.hex())
            return

        self._packs[_decode_sn(pack.sn)] = pack
        self._pack_chg_set_soc = pack.chg_set_soc
        self._pack_dsg_set_soc = pack.dsg_set_soc
        self._update_pack_slots()

    def _update_pack_slots(self) -> None:
        if self._pack_slots is None:
            return
        sn_by_slot = {slot: sn for sn, slot in self._pack_slots.items()}
        for slot in range(1, self.NUM_BATTERY_SLOTS + 1):
            sn = sn_by_slot.get(slot)
            pack = self._packs.get(sn) if sn is not None else None
            self._set_pack_slot(slot, sn, pack)

    def _set_pack_slot(self, slot: int, sn: str | None, pack: BmsData | None) -> None:
        def reading(attr: str) -> int | None:
            return None if pack is None else getattr(pack, attr)

        cls = type(self)
        self.set_value(cls.pack_enabled[slot], sn is not None)
        self.set_value(cls.pack_sn[slot], sn)
        self.set_value(cls.pack_level[slot], reading("soc"))
        self.set_value(cls.pack_temperature[slot], reading("temp"))
        self.set_value(cls.pack_voltage[slot], _mv_to_v(reading("vol")))
        self.set_value(
            cls.pack_max_cell_voltage[slot], _cell_mv_to_v(reading("max_cell_vol"))
        )
        self.set_value(
            cls.pack_min_cell_voltage[slot], _cell_mv_to_v(reading("min_cell_vol"))
        )
        self.set_value(cls.pack_input_power[slot], reading("int_put_watt"))
        self.set_value(cls.pack_output_power[slot], reading("out_put_watt"))

    def _parse_dc_names(self, payload: bytes) -> None:
        """
        Parse the DC panel circuit-name frame (0x54/0x54/0x12).

        Layout (from the app parser ld.f.J "parseDcName"): a header byte, a circuit
        count, then per circuit ``[chImgId (u32 LE icon), nameLen (u8), name (UTF-8)]``.
        The Nth record maps to circuit N (1-based). This app-derived layout still
        needs live confirmation; icon IDs remain opaque rather than guessed MDI icons.
        """
        if len(payload) < 2:
            raise PacketParseError("Power Hub circuit metadata header is truncated")
        count = payload[1]
        if count > self.NUM_DC_CIRCUITS:
            raise PacketParseError(
                f"Power Hub circuit metadata contains too many circuits: {count}"
            )

        metadata: list[tuple[int, str]] = []
        offset = 2
        for _ in range(count):
            if offset + 5 > len(payload):
                raise PacketParseError("Power Hub circuit metadata record is truncated")
            icon_id = int.from_bytes(payload[offset : offset + 4], "little")
            offset += 4
            name_len = payload[offset]
            offset += 1
            if offset + name_len > len(payload):
                raise PacketParseError("Power Hub circuit metadata name is truncated")
            try:
                name = payload[offset : offset + name_len].decode("utf-8")
            except UnicodeDecodeError as err:
                raise PacketParseError(
                    "Power Hub circuit metadata name is not valid UTF-8"
                ) from err
            offset += name_len
            metadata.append((icon_id, name))

        # A partial response must not overwrite previously received names or icons.
        for circuit, (icon_id, name) in enumerate(metadata, start=1):
            self.set_value(type(self).dc_channel_names[circuit], name)
            self.set_value(type(self).dc_channel_icon_ids[circuit], icon_id)
        self._dc_names_loaded = True

    async def _send_config_packet(
        self,
        dst: int,
        cmd_set: int,
        cmd_id: int,
        payload: bytes,
        *,
        ddst: int = 1,
        raise_on_failure: bool = False,
    ) -> None:
        packet = Packet(
            src=0x21,
            dst=dst,
            cmd_set=cmd_set,
            cmd_id=cmd_id,
            payload=payload,
            ddst=ddst,
            version=self.packet_version,
        )
        await self.send_packet(packet, raise_on_failure=raise_on_failure)

    @controls.battery(battery_charge_limit_max, min=50, max=100)
    async def set_battery_charge_limit_max(self, limit: float) -> bool:
        """
        Set the charge limit (maximum SOC).

        Command recovered from the EcoFlow app: the charge limit slider
        (MM100SystemActivity, range 50-100 %) sends ``z50.p1.x2``, a one-byte SOC to the
        battery module (dst 0x03, cmd_set 0x20, cmd_id 0x31, ddst 0).
        """
        await self._send_config_packet(
            0x03, 0x20, 0x31, bytes([int(limit)]), ddst=0, raise_on_failure=True
        )
        return True

    @controls.battery(battery_charge_limit_min, min=0, max=30)
    async def set_battery_charge_limit_min(self, limit: float) -> bool:
        """
        Set the discharge limit (minimum SOC).

        Command recovered from the EcoFlow app: the discharge limit slider
        (MM100SystemActivity, range 0-30 %) sends ``z50.p1.N2``, a one-byte SOC to the
        battery module (dst 0x03, cmd_set 0x20, cmd_id 0x33, ddst 0).
        """
        await self._send_config_packet(
            0x03, 0x20, 0x33, bytes([int(limit)]), ddst=0, raise_on_failure=True
        )
        return True

    async def enable_pv1_input(self, enabled: bool) -> None:
        """
        Turn the PV1 solar input on/off.

        Command recovered from the EcoFlow app: the input page's PV1 switch sends
        ``z50.p1.X2``, a 20-byte payload to the MPPT module (dst 0x05, cmd_set 0x05,
        cmd_id 0x06). Byte 0 is the PV1 on/off flag; the 0xFF bytes mark the module's
        other settings as "leave unchanged".
        """
        payload = bytes((0x01 if enabled else 0x00,)) + b"\xff" * 19
        await self._send_config_packet(0x05, 0x05, 0x06, payload, raise_on_failure=True)

    async def enable_pv2_input(self, enabled: bool) -> None:
        """
        Turn the PV2 solar input on/off.

        Command recovered from the EcoFlow app: the input page's PV2 switch sends
        ``z50.p1.Y2``, the same 20-byte MPPT payload as PV1 with the on/off flag in
        byte 1 instead.
        """
        payload = bytes((0xFF, 0x01 if enabled else 0x00)) + b"\xff" * 18
        await self._send_config_packet(0x05, 0x05, 0x06, payload, raise_on_failure=True)

    async def enable_dc_input(self, enabled: bool) -> None:
        """
        Allow or pause charging from the DC/alternator input.

        Command recovered from the EcoFlow app: the input page's alternator switch sends
        ``z50.p1.G2``, a 15-byte payload to the hub module (dst 0x50, cmd_set 0x50,
        cmd_id 0x21). Byte 4 is the charge-pause flag (0 = charging allowed); the 0xFF
        bytes mark the module's other settings as "leave unchanged".
        """
        payload = b"\xff" * 4 + bytes((0x00 if enabled else 0x01,)) + b"\xff" * 10
        await self._send_config_packet(0x50, 0x50, 0x21, payload, raise_on_failure=True)

    async def enable_ac_input(self, enabled: bool) -> None:
        """
        Allow or pause AC charging without changing AC output.

        The input page (`i50.r.h1`) calls `z50.p1.e2`: byte 4 is acChgDisable
        (0 = enabled), byte 6 wakes the inverter, and 0xFF leaves other settings alone.
        """
        payload = b"\xff" * 4 + bytes((0 if enabled else 1, 0xFF, 1)) + b"\xff" * 3
        await self._send_config_packet(0x02, 0x02, 0x07, payload, raise_on_failure=True)

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
        payload = bytes((onoff, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0xFF, 0xFF, 0xFF))
        await self._send_config_packet(0x02, 0x02, 0x07, payload, raise_on_failure=True)

    async def enable_dc_ports(self, enabled: bool) -> None:
        """
        Turn the DC output master on/off.

        Command recovered from the EcoFlow app: the output page's DC switch
        (``k50.s.L0``) sends ``z50.p1.H2``, an 11-byte payload to the BBC output module
        (dst 0x51, cmd_set 0x50, cmd_id 0x22). Byte 1 is the on/off flag; the 0xFF
        bytes mark the module's other settings as "leave unchanged".
        """
        payload = bytes((0xFF, 0x01 if enabled else 0x00)) + b"\xff" * 9
        await self._send_config_packet(0x51, 0x50, 0x22, payload, raise_on_failure=True)

    async def set_dc_circuit(self, circuit: int, enabled: bool) -> None:
        """
        Turn a DC distribution circuit (1-16) on/off.

        The panel reports every circuit's on/off in the 16-bit ``chStates`` bitmask
        (bit i = circuit i+1). Mirroring the app's DC toggle (MM100OutputDcViewModel.k
        -> ud.x0.u1: dst 0x54, cmd_set 0x54, cmd_id 0x10, payload = the state bitmask),
        we resend the full mask with just this circuit's bit updated so the other
        circuits are preserved. The panel has 16 circuits so the mask is two
        little-endian bytes.

        Turning a circuit on first turns the DC output master on, as the app's toggle
        does (MM100OutputDcFragment calls ``P(true)`` before ``O``); the app shows
        every circuit as unpowered while the master is off.
        """
        current = self.dc_ch_states
        if current is None:
            raise RuntimeError(
                "Cannot switch a DC circuit before the panel has reported circuit states"
            )
        bit = circuit - 1
        if enabled:
            await self.enable_dc_ports(True)
            new_states = current | (1 << bit)
        else:
            new_states = current & ~(1 << bit)
        await self._send_config_packet(
            0x54,
            0x54,
            0x10,
            new_states.to_bytes(2, "little"),
            raise_on_failure=True,
        )
