from collections.abc import Sequence
from dataclasses import dataclass

from ..commands import TimeCommands
from ..devicebase import AdvertisementData, BLEDevice, DeviceBase
from ..packet import Packet
from ..pb import pd303_pb2
from ..props import (
    Field,
    ProtobufProps,
    pb_field,
    proto_attr_mapper,
    repeated_pb_field_type,
)
from ..props.protobuf_field import TransformIfMissing

pb_time = proto_attr_mapper(pd303_pb2.ProtoTime)
pb_push_set = proto_attr_mapper(pd303_pb2.ProtoPushAndSet)


@dataclass
class CircuitPowerField(
    repeated_pb_field_type(list_field=pb_time.load_info.hall1_watt)
):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return value[self.idx] if value and len(value) > self.idx else None


@dataclass
class CircuitCurrentField(
    repeated_pb_field_type(list_field=pb_time.load_info.hall1_curr)
):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.idx], 4) if value and len(value) > self.idx else None


@dataclass
class ChannelPowerField(repeated_pb_field_type(list_field=pb_time.watt_info.ch_watt)):
    idx: int

    def get_item(self, value: Sequence[float]) -> float | None:
        return round(value[self.idx], 2) if value and len(value) > self.idx else None


def _errors(error_codes: pd303_pb2.ErrCode):
    return [e for e in error_codes.err_code if e != b"\x00\x00\x00\x00\x00\x00\x00\x00"]


def _create_backup_channel_fields(cls):
    """Dynamically create backup channel fields for all channels"""
    for i in range(1, cls.NUM_OF_CHANNELS + 1):
        ch_info = getattr(pb_push_set.backup_incre_info, f"ch{i}_info")

        setattr(cls, f"ch{i}_backup_is_ready", pb_field(ch_info.backup_is_ready))
        setattr(cls, f"ch{i}_ctrl_status", pb_field(ch_info.ctrl_sta))
        setattr(cls, f"ch{i}_force_charge", pb_field(ch_info.force_charge_sta))
        setattr(cls, f"ch{i}_backup_rly1_cnt", pb_field(ch_info.backup_rly1_cnt))
        setattr(cls, f"ch{i}_backup_rly2_cnt", pb_field(ch_info.backup_rly2_cnt))
        setattr(cls, f"ch{i}_wake_up_charge_status", pb_field(ch_info.wake_up_charge_sta))
        setattr(cls, f"ch{i}_energy_5p8_type", pb_field(ch_info.energy_5p8_type))


def _create_energy_fields(cls):
    """Dynamically create energy fields for all energy units"""
    for i in range(1, cls.NUM_OF_CHANNELS + 1):
        energy_info = getattr(pb_push_set.backup_incre_info, f"Energy{i}_info")

        # Device info fields
        setattr(cls, f"energy{i}_sn", pb_field(energy_info.dev_info.model_info.sn))
        setattr(cls, f"energy{i}_type", pb_field(energy_info.dev_info.type))
        setattr(cls, f"energy{i}_capacity", pb_field(energy_info.dev_info.full_cap))
        setattr(cls, f"energy{i}_rate_power", pb_field(energy_info.dev_info.rate_power))

        # Status fields
        setattr(cls, f"energy{i}_is_enabled", pb_field(energy_info.is_enable))
        setattr(cls, f"energy{i}_is_connected", pb_field(energy_info.is_connect))
        setattr(cls, f"energy{i}_is_ac_open", pb_field(energy_info.is_ac_open))
        setattr(cls, f"energy{i}_is_power_output", pb_field(energy_info.is_power_output))
        setattr(cls, f"energy{i}_is_grid_charge", pb_field(energy_info.is_grid_charge))
        setattr(cls, f"energy{i}_is_mppt_charge", pb_field(energy_info.is_mppt_charge))

        # Power and battery fields
        setattr(cls, f"energy{i}_battery_percentage", pb_field(energy_info.battery_percentage))
        setattr(cls, f"energy{i}_output_power", pb_field(energy_info.output_power))
        setattr(cls, f"energy{i}_ems_charging", pb_field(energy_info.ems_chg_flag))
        setattr(cls, f"energy{i}_hw_connect", pb_field(energy_info.hw_connect))
        setattr(cls, f"energy{i}_battery_temp", pb_field(energy_info.ems_bat_temp))
        setattr(cls, f"energy{i}_lcd_input", pb_field(energy_info.lcd_input_watts))
        setattr(cls, f"energy{i}_pv_input", pb_field(energy_info.pv_charge_watts))
        setattr(cls, f"energy{i}_pv_lv_input", pb_field(energy_info.pv_low_charge_watts))
        setattr(cls, f"energy{i}_pv_hv_input", pb_field(energy_info.pv_height_charge_watts))
        setattr(cls, f"energy{i}_error_code", pb_field(energy_info.error_code_num))

        setattr(cls, f"channel_power_{i}", ChannelPowerField(i-1))

def _create_circuit_fields(cls):
    """Dynamically create circuit fields for all available circuits"""
    for i in range(1, cls.NUM_OF_CIRCUITS + 1):
        # Circuit power
        setattr(cls, f"circuit_power_{i}", CircuitPowerField(i-1))

        # Circuit current
        setattr(cls, f"circuit_current_{i}", CircuitCurrentField(i-1))


class Device(DeviceBase, ProtobufProps):
    """Smart Home Panel 2"""

    SN_PREFIX = b"HD31"
    NAME_PREFIX = "EF-HD3"

    NUM_OF_CIRCUITS = 12
    NUM_OF_CHANNELS = 3

    battery_level = pb_field(pb_push_set.backup_incre_info.backup_bat_per)

    # Additional attributes are created dynamically after class definition

    in_use_power = pb_field(pb_time.watt_info.all_hall_watt)
    grid_power = pb_field(
        pb_time.watt_info.grid_watt,
        TransformIfMissing(lambda v: v if v is not None else 0.0),
    )

    errors = pb_field(pb_push_set.backup_incre_info.errcode, _errors)
    error_count = Field[int]()
    error_happened = Field[bool]()

    @staticmethod
    def check(sn):
        return sn.startswith(Device.SN_PREFIX)

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)

        # Creating dynamic fields
        _create_backup_channel_fields(self)
        _create_energy_fields(self)
        _create_circuit_fields(self)

        self._time_commands = TimeCommands(self)

    async def data_parse(self, packet: Packet) -> bool:
        """Processing the incoming notifications from the device"""
        processed = False
        self.reset_updated()

        prev_error_count = self.error_count

        if packet.src == 0x0B and packet.cmdSet == 0x0C:
            if (
                packet.cmdId == 0x01
            ):  # master_info, load_info, backup_info, watt_info, master_ver_info
                self._logger.debug(
                    "%s: %s: Parsed data: %r", self.address, self.name, packet
                )

                await self._conn.replyPacket(packet)
                self.update_from_bytes(pd303_pb2.ProtoTime, packet.payload)
                processed = True
            elif packet.cmdId == 0x20:  # backup_incre_info
                self._logger.debug(
                    "%s: %s: Parsed data: %r", self.address, self.name, packet
                )

                await self._conn.replyPacket(packet)
                self.update_from_bytes(pd303_pb2.ProtoPushAndSet, packet.payload)

                processed = True

            elif packet.cmdId == 0x21:  # is_get_cfg_flag
                self._logger.debug(
                    "%s: %s: Parsed data: %r", self.address, self.name, packet
                )
                self.update_from_bytes(pd303_pb2.ProtoPushAndSet, packet.payload)
                processed = True

        elif packet.src == 0x35 and packet.cmdSet == 0x35 and packet.cmdId == 0x20:
            self._logger.debug(
                "%s: %s: Ping received: %r", self.address, self.name, packet
            )
            processed = True

        elif (
            packet.src == 0x35
            and packet.cmdSet == 0x01
            and packet.cmdId == Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME
        ):
            # Device requested for time and timezone offset, so responding with that
            # otherwise it will not be able to send us predictions and config data
            if len(packet.payload) == 0:
                self._time_commands.async_send_all()
            processed = True

        elif packet.src == 0x0B and packet.cmdSet == 0x01 and packet.cmdId == 0x55:
            # Device reply that it's online and ready
            self._conn._add_task(self.set_config_flag(True))
            processed = True

        self.error_count = len(self.errors) if self.errors is not None else None

        if (
            self.error_count is not None
            and prev_error_count is not None
            and self.error_count > prev_error_count
        ) or (self.error_count is not None and prev_error_count is None):
            self.error_happened = True
            self._logger.warning(
                "%s: %s: Error happened on device: %s",
                self.address,
                self.name,
                self.errors,
            )

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

    async def set_config_flag(self, enable):
        """Send command to enable/disable sending config data from device to the host"""
        self._logger.debug("%s: setConfigFlag: %s", self._address, enable)

        ppas = pd303_pb2.ProtoPushAndSet()
        ppas.is_get_cfg_flag = enable
        payload = ppas.SerializeToString()
        packet = Packet(0x21, 0x0B, 0x0C, 0x21, payload, 0x01, 0x01, 0x13)

        await self._conn.sendPacket(packet)

    async def set_circuit_power(self, circuit_id, enable):
        """Send command to power on / off the specific circuit of the panel"""
        self._logger.debug(
            "%s: setCircuitPower for %d: %s", self._address, circuit_id, enable
        )

        ppas = pd303_pb2.ProtoPushAndSet()
        sta = getattr(
            ppas.load_incre_info.hall1_incre_info, "ch" + str(circuit_id + 1) + "_sta"
        )
        sta.load_sta = (
            pd303_pb2.LOAD_CH_POWER_ON if enable else pd303_pb2.LOAD_CH_POWER_OFF
        )
        sta.ctrl_mode = pd303_pb2.RLY_HAND_CTRL_MODE
        payload = ppas.SerializeToString()
        packet = Packet(0x21, 0x0B, 0x0C, 0x21, payload, 0x01, 0x01, 0x13)

        await self._conn.sendPacket(packet)
