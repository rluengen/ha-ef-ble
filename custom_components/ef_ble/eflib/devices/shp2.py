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

class Device(DeviceBase, ProtobufProps):
    """Smart Home Panel 2"""

    SN_PREFIX = b"HD31"
    NAME_PREFIX = "EF-HD3"

    NUM_OF_CIRCUITS = 12
    NUM_OF_CHANNELS = 3

    battery_level = pb_field(pb_push_set.backup_incre_info.backup_bat_per)

    circuit_power_1 = CircuitPowerField(0)
    circuit_power_2 = CircuitPowerField(1)
    circuit_power_3 = CircuitPowerField(2)
    circuit_power_4 = CircuitPowerField(3)
    circuit_power_5 = CircuitPowerField(4)
    circuit_power_6 = CircuitPowerField(5)
    circuit_power_7 = CircuitPowerField(6)
    circuit_power_8 = CircuitPowerField(7)
    circuit_power_9 = CircuitPowerField(8)
    circuit_power_10 = CircuitPowerField(9)
    circuit_power_11 = CircuitPowerField(10)
    circuit_power_12 = CircuitPowerField(11)

    circuit_current_1 = CircuitCurrentField(0)
    circuit_current_2 = CircuitCurrentField(1)
    circuit_current_3 = CircuitCurrentField(2)
    circuit_current_4 = CircuitCurrentField(3)
    circuit_current_5 = CircuitCurrentField(4)
    circuit_current_6 = CircuitCurrentField(5)
    circuit_current_7 = CircuitCurrentField(6)
    circuit_current_8 = CircuitCurrentField(7)
    circuit_current_9 = CircuitCurrentField(8)
    circuit_current_10 = CircuitCurrentField(9)
    circuit_current_11 = CircuitCurrentField(10)
    circuit_current_12 = CircuitCurrentField(11)

    channel_power_1 = ChannelPowerField(0)
    channel_power_2 = ChannelPowerField(1)
    channel_power_3 = ChannelPowerField(2)

    # Input 1
    energy1_sn = pb_field(pb_push_set.backup_incre_info.Energy1_info.dev_info.model_info.sn)
    energy1_type = pb_field(pb_push_set.backup_incre_info.Energy1_info.dev_info.type)
    energy1_capacity = pb_field(pb_push_set.backup_incre_info.Energy1_info.dev_info.full_cap)
    energy1_rate_power = pb_field(pb_push_set.backup_incre_info.Energy1_info.dev_info.rate_power)
    energy1_is_enabled = pb_field(pb_push_set.backup_incre_info.Energy1_info.is_enable)
    energy1_is_connected = pb_field(pb_push_set.backup_incre_info.Energy1_info.is_connect)
    energy1_is_ac_open = pb_field(pb_push_set.backup_incre_info.Energy1_info.is_ac_open)
    energy1_is_power_output = pb_field(pb_push_set.backup_incre_info.Energy1_info.is_power_output)
    energy1_is_grid_charge = pb_field(pb_push_set.backup_incre_info.Energy1_info.is_grid_charge)
    energy1_is_mppt_charge = pb_field(pb_push_set.backup_incre_info.Energy1_info.is_mppt_charge)
    energy1_battery_percentage = pb_field(pb_push_set.backup_incre_info.Energy1_info.battery_percentage)
    energy1_output_power = pb_field(pb_push_set.backup_incre_info.Energy1_info.output_power)
    energy1_ems_charging = pb_field(pb_push_set.backup_incre_info.Energy1_info.ems_chg_flag)
    energy1_hw_connect = pb_field(pb_push_set.backup_incre_info.Energy1_info.hw_connect)
    energy1_battery_temp = pb_field(pb_push_set.backup_incre_info.Energy1_info.ems_bat_temp)
    energy1_lcd_input = pb_field(pb_push_set.backup_incre_info.Energy1_info.lcd_input_watts)
    energy1_pv_input = pb_field(pb_push_set.backup_incre_info.Energy1_info.pv_charge_watts)
    energy1_pv_lv_input = pb_field(pb_push_set.backup_incre_info.Energy1_info.pv_low_charge_watts)
    energy1_pv_hv_input = pb_field(pb_push_set.backup_incre_info.Energy1_info.pv_height_charge_watts)
    energy1_error_code = pb_field(pb_push_set.backup_incre_info.Energy1_info.error_code_num)

    ch1_backup_is_ready = pb_field(pb_push_set.backup_incre_info.ch1_info.backup_is_ready)
    ch1_ctrl_status = pb_field(pb_push_set.backup_incre_info.ch1_info.ctrl_sta)
    ch1_force_charge = pb_field(pb_push_set.backup_incre_info.ch1_info.force_charge_sta)
    ch1_backup_rly1_cnt = pb_field(pb_push_set.backup_incre_info.ch1_info.backup_rly1_cnt)
    ch1_backup_rly2_cnt = pb_field(pb_push_set.backup_incre_info.ch1_info.backup_rly2_cnt)
    ch1_wake_up_charge_status = pb_field(pb_push_set.backup_incre_info.ch1_info.wake_up_charge_sta)
    ch1_energy_5p8_type = pb_field(pb_push_set.backup_incre_info.ch1_info.energy_5p8_type)

    # Input 2
    energy2_sn = pb_field(pb_push_set.backup_incre_info.Energy2_info.dev_info.model_info.sn)
    energy2_type = pb_field(pb_push_set.backup_incre_info.Energy2_info.dev_info.type)
    energy2_capacity = pb_field(pb_push_set.backup_incre_info.Energy2_info.dev_info.full_cap)
    energy2_rate_power = pb_field(pb_push_set.backup_incre_info.Energy2_info.dev_info.rate_power)
    energy2_is_enabled = pb_field(pb_push_set.backup_incre_info.Energy2_info.is_enable)
    energy2_is_connected = pb_field(pb_push_set.backup_incre_info.Energy2_info.is_connect)
    energy2_is_ac_open = pb_field(pb_push_set.backup_incre_info.Energy2_info.is_ac_open)
    energy2_is_power_output = pb_field(pb_push_set.backup_incre_info.Energy2_info.is_power_output)
    energy2_is_grid_charge = pb_field(pb_push_set.backup_incre_info.Energy2_info.is_grid_charge)
    energy2_is_mppt_charge = pb_field(pb_push_set.backup_incre_info.Energy2_info.is_mppt_charge)
    energy2_battery_percentage = pb_field(pb_push_set.backup_incre_info.Energy2_info.battery_percentage)
    energy2_output_power = pb_field(pb_push_set.backup_incre_info.Energy2_info.output_power)
    energy2_ems_charging = pb_field(pb_push_set.backup_incre_info.Energy2_info.ems_chg_flag)
    energy2_hw_connect = pb_field(pb_push_set.backup_incre_info.Energy2_info.hw_connect)
    energy2_battery_temp = pb_field(pb_push_set.backup_incre_info.Energy2_info.ems_bat_temp)
    energy2_lcd_input = pb_field(pb_push_set.backup_incre_info.Energy2_info.lcd_input_watts)
    energy2_pv_input = pb_field(pb_push_set.backup_incre_info.Energy2_info.pv_charge_watts)
    energy2_pv_lv_input = pb_field(pb_push_set.backup_incre_info.Energy2_info.pv_low_charge_watts)
    energy2_pv_hv_input = pb_field(pb_push_set.backup_incre_info.Energy2_info.pv_height_charge_watts)
    energy2_error_code = pb_field(pb_push_set.backup_incre_info.Energy2_info.error_code_num)

    ch2_backup_is_ready = pb_field(pb_push_set.backup_incre_info.ch2_info.backup_is_ready)
    ch2_ctrl_status = pb_field(pb_push_set.backup_incre_info.ch2_info.ctrl_sta)
    ch2_force_charge = pb_field(pb_push_set.backup_incre_info.ch2_info.force_charge_sta)
    ch2_backup_rly1_cnt = pb_field(pb_push_set.backup_incre_info.ch2_info.backup_rly1_cnt)
    ch2_backup_rly2_cnt = pb_field(pb_push_set.backup_incre_info.ch2_info.backup_rly2_cnt)
    ch2_wake_up_charge_status = pb_field(pb_push_set.backup_incre_info.ch2_info.wake_up_charge_sta)
    ch2_energy_5p8_type = pb_field(pb_push_set.backup_incre_info.ch2_info.energy_5p8_type)

    # Input 3
    energy3_sn = pb_field(pb_push_set.backup_incre_info.Energy3_info.dev_info.model_info.sn)
    energy3_type = pb_field(pb_push_set.backup_incre_info.Energy3_info.dev_info.type)
    energy3_capacity = pb_field(pb_push_set.backup_incre_info.Energy3_info.dev_info.full_cap)
    energy3_rate_power = pb_field(pb_push_set.backup_incre_info.Energy3_info.dev_info.rate_power)
    energy3_is_enabled = pb_field(pb_push_set.backup_incre_info.Energy3_info.is_enable)
    energy3_is_connected = pb_field(pb_push_set.backup_incre_info.Energy3_info.is_connect)
    energy3_is_ac_open = pb_field(pb_push_set.backup_incre_info.Energy3_info.is_ac_open)
    energy3_is_power_output = pb_field(pb_push_set.backup_incre_info.Energy3_info.is_power_output)
    energy3_is_grid_charge = pb_field(pb_push_set.backup_incre_info.Energy3_info.is_grid_charge)
    energy3_is_mppt_charge = pb_field(pb_push_set.backup_incre_info.Energy3_info.is_mppt_charge)
    energy3_battery_percentage = pb_field(pb_push_set.backup_incre_info.Energy3_info.battery_percentage)
    energy3_output_power = pb_field(pb_push_set.backup_incre_info.Energy3_info.output_power)
    energy3_ems_charging = pb_field(pb_push_set.backup_incre_info.Energy3_info.ems_chg_flag)
    energy3_hw_connect = pb_field(pb_push_set.backup_incre_info.Energy3_info.hw_connect)
    energy3_battery_temp = pb_field(pb_push_set.backup_incre_info.Energy3_info.ems_bat_temp)
    energy3_lcd_input = pb_field(pb_push_set.backup_incre_info.Energy3_info.lcd_input_watts)
    energy3_pv_input = pb_field(pb_push_set.backup_incre_info.Energy3_info.pv_charge_watts)
    energy3_pv_lv_input = pb_field(pb_push_set.backup_incre_info.Energy3_info.pv_low_charge_watts)
    energy3_pv_hv_input = pb_field(pb_push_set.backup_incre_info.Energy3_info.pv_height_charge_watts)
    energy3_error_code = pb_field(pb_push_set.backup_incre_info.Energy3_info.error_code_num)

    ch3_backup_is_ready = pb_field(pb_push_set.backup_incre_info.ch3_info.backup_is_ready)
    ch3_ctrl_status = pb_field(pb_push_set.backup_incre_info.ch3_info.ctrl_sta)
    ch3_force_charge = pb_field(pb_push_set.backup_incre_info.ch3_info.force_charge_sta)
    ch3_backup_rly1_cnt = pb_field(pb_push_set.backup_incre_info.ch3_info.backup_rly1_cnt)
    ch3_backup_rly2_cnt = pb_field(pb_push_set.backup_incre_info.ch3_info.backup_rly2_cnt)
    ch3_wake_up_charge_status = pb_field(pb_push_set.backup_incre_info.ch3_info.wake_up_charge_sta)
    ch3_energy_5p8_type = pb_field(pb_push_set.backup_incre_info.ch3_info.energy_5p8_type)

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
