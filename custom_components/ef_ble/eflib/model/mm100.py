"""
EcoFlow Power Hub (MM100) BLE telemetry structs.

The Power Hub ("Power Kit" central unit, serial ``M3H1*`` / BLE name ``EF-M35*``) reports
each internal sub-module (solar MPPT, DC-DC converters, inverter, BMS, AC/DC distribution,
generator) as a packed fixed-width binary payload. Field order and widths below are the
BLE wire layout, recovered from the EcoFlow Android app packet parser (setter-call order
in obfuscated class ``ld.f``, app 5.4.5). Each field follows the same
``Annotated[<pytype>, <struct_fmt>, <originalCamelCaseName>]`` convention as the other
``RawData`` models in this package.

PROVISIONAL - verify against a live decrypted capture before relying on values:
  * ``int`` fields are treated as unsigned (``I``); some currents may be signed (``i``).
  * 16-bit ``h`` fields are temperatures (signed) and small flags.
  * byte temperatures (``B``) may actually be signed/offset.
  * The leading payload may contain a header before field 0 (no preamble assumed here).

DEFERRED until capture (per-channel arrays / generator pack of runtime length):
  * ACData / DCData distribution panels: errorCode[], channelCur[], chPower[],
    chStates[], chEnableStates[] (length == channel count).
  * OilPackData (smart generator): hwVer[], errorCode[], systemVer[] arrays.
"""

from typing import Annotated

from .base import RawData


class BatterySummaryData(RawData):
    """
    Power Kit battery summary frame (src=0x03, cmd_set=0x03, cmd_id=0x1C).

    Only the state-of-charge (byte 0) is confirmed, verified against two live captures
    (0x36 = 54% then 0x32 = 50%, matching the app). The remaining ~34 bytes (a static
    ~0x0a64 field, a near-zero signed value that tracks pack current, etc.) are not yet
    mapped, so this struct intentionally stops after ``soc``.
    """

    soc: Annotated[int, "B", "soc"]



class SccData(RawData):
    """MPPT solar charge controller sub-module (PV1/PV2)."""

    pv1_error_code: Annotated[int, "I", "pv1ErrorCode"]
    pv2_error_code: Annotated[int, "I", "pv2ErrorCode"]
    battery_vol: Annotated[int, "I", "batteryVol"]
    battery_cur: Annotated[int, "I", "batteryCur"]
    battery_watt: Annotated[int, "I", "batteryWatt"]
    pv1_in_vol: Annotated[int, "I", "pv1InVol"]
    pv1_in_cur: Annotated[int, "I", "pv1InCur"]
    pv1_in_watt: Annotated[int, "I", "pv1InWatt"]
    pv2_in_vol: Annotated[int, "I", "pv2InVol"]
    pv2_in_cur: Annotated[int, "I", "pv2InCur"]
    pv2_in_watt: Annotated[int, "I", "pv2InWatt"]
    l1_cur: Annotated[int, "I", "l1Cur"]
    l2_cur: Annotated[int, "I", "l2Cur"]
    hs1_temp: Annotated[int, "h", "hs1Temp"]
    hs2_temp: Annotated[int, "h", "hs2Temp"]
    pcb_temp: Annotated[int, "h", "pcbTemp"]
    pv1_work_mode: Annotated[int, "h", "pv1WorkMode"]
    pv2_work_mode: Annotated[int, "h", "pv2WorkMode"]
    mppt1_switch_state: Annotated[int, "h", "mppt1SwitchState"]
    mppt2_switch_state: Annotated[int, "h", "mppt2SwitchState"]
    pv1_input_flag: Annotated[int, "h", "pv1InputFlag"]
    pv2_input_flag: Annotated[int, "h", "pv2InputFlag"]
    day_energy: Annotated[int, "I", "dayEnergy"]
    total_energy: Annotated[int, "I", "totalEnergy"]
    pv1_cable_length: Annotated[int, "I", "pv1CableLength"]
    pv2_cable_length: Annotated[int, "I", "pv2CableLength"]
    pv1_len_unit_flag: Annotated[int, "B", "pv1LenUnitFlag"]
    pv2_len_unit_flag: Annotated[int, "B", "pv2LenUnitFlag"]
    pv1_hot_out: Annotated[int, "I", "pv1HotOut"]
    pv2_hot_out: Annotated[int, "I", "pv2HotOut"]
    warn_code1: Annotated[int, "I", "warnCode1"]
    event_code1: Annotated[int, "I", "eventCode1"]
    warn_code2: Annotated[int, "I", "warnCode2"]
    event_code2: Annotated[int, "I", "eventCode2"]
    pv1_vol_limit: Annotated[int, "I", "pv1VolLimit"]
    pv2_vol_limit: Annotated[int, "I", "pv2VolLimit"]
    pv1_vol_limit_enable: Annotated[int, "B", "pv1VolLimitEnable"]
    pv2_vol_limit_enable: Annotated[int, "B", "pv2VolLimitEnable"]


class BbcInData(RawData):
    """BBC DC-DC input: solar / alternator / vehicle DC charging."""

    dc_input_vol: Annotated[int, "I", "dcInputVol"]
    dc_input_cur: Annotated[int, "I", "dcInputCur"]
    dc_input_watt: Annotated[int, "I", "dcInputWatt"]
    battery_vol: Annotated[int, "I", "batteryVol"]
    battery_cur: Annotated[int, "I", "batteryCur"]
    battery_watt: Annotated[int, "I", "batteryWatt"]
    l1_cur: Annotated[int, "I", "l1Cur"]
    l2_cur: Annotated[int, "I", "l2Cur"]
    hs1_temp: Annotated[int, "h", "hs1Temp"]
    hs2_temp: Annotated[int, "h", "hs2Temp"]
    pcb_temp: Annotated[int, "h", "pcbTemp"]
    work_mode: Annotated[int, "B", "workMode"]
    charge_pause: Annotated[int, "B", "chargePause"]
    max_config_charge_cur: Annotated[int, "I", "maxConfigChargeCur"]
    day_energy: Annotated[int, "I", "dayEnergy"]
    total_energy: Annotated[int, "I", "totalEnergy"]
    dc_input_state: Annotated[int, "B", "dcInputState"]
    bp_online_pos: Annotated[int, "B", "bpOnlinePos"]
    in_hw_type: Annotated[int, "B", "inHwType"]
    charge_type: Annotated[int, "B", "chargeType"]
    is_car_moving: Annotated[int, "B", "isCarMoving"]
    cfg_shake_disable: Annotated[int, "B", "cfgShakeDisable"]
    alt_cable_length: Annotated[int, "I", "altCableLength"]
    length_unit_flag: Annotated[int, "B", "lengthUnitFlag"]
    charge_mode: Annotated[int, "B", "chargeMode"]
    warn_code: Annotated[int, "I", "warnCode"]
    event_code: Annotated[int, "I", "eventCode"]
    work_mode2: Annotated[int, "B", "workMode2"]
    allow_dsg_on: Annotated[int, "B", "allowDsgOn"]
    alt_limit_vol: Annotated[int, "I", "altLimitVol"]
    alt_vol_limit_enable: Annotated[int, "B", "altVolLimitEnable"]
    third_watts: Annotated[int, "I", "thirdWatts"]


class BbcOutData(RawData):
    """BBC DC-DC output: DC loads."""

    battery_vol: Annotated[int, "I", "batteryVol"]
    battery_cur: Annotated[int, "I", "batteryCur"]
    battery_watt: Annotated[int, "I", "batteryWatt"]
    ld_out_vol: Annotated[int, "I", "ldOutVol"]
    ld_out_cur: Annotated[int, "I", "ldOutCur"]
    ld_out_watt: Annotated[int, "I", "ldOutWatt"]
    l1_cur: Annotated[int, "I", "l1Cur"]
    l2_cur: Annotated[int, "I", "l2Cur"]
    hs1_temp: Annotated[int, "h", "hs1Temp"]
    hs2_temp: Annotated[int, "h", "hs2Temp"]
    pcb_temp: Annotated[int, "h", "pcbTemp"]
    work_mode: Annotated[int, "B", "workMode"]
    dc_switch_mode: Annotated[int, "B", "dcSwitchMode"]
    dc_output_vol_tag: Annotated[int, "B", "dcOutputVolTag"]
    day_energy: Annotated[int, "I", "dayEnergy"]
    total_energy: Annotated[int, "I", "totalEnergy"]
    warn_code: Annotated[int, "I", "warnCode"]
    event_code: Annotated[int, "I", "eventCode"]
    standby_time: Annotated[int, "I", "standbyTime"]


class InvData(RawData):
    """Inverter sub-module."""

    warn_code: Annotated[int, "I", "warnCode"]
    event_code: Annotated[int, "I", "eventCode"]
    battery_vol: Annotated[int, "I", "batteryVol"]
    battery_cur: Annotated[int, "I", "batteryCur"]
    bus_vol: Annotated[int, "I", "busVol"]
    dc_temp: Annotated[int, "h", "dcTemp"]
    fan_level: Annotated[int, "B", "fanLevel"]
    charger_type: Annotated[int, "B", "chargerType"]
    charge_discharge_state: Annotated[int, "B", "chargeDischargeState"]

    # TODO(capture): the following trailing fields are interrupted by a
    # variable-length array / nested struct and need a live capture to
    # confirm size/offset before they can be added:
    #   protect_state  (orig protectState, array/nested/string)
    #   max_charge_cur  (orig maxChargeCur, I)
    #   bms_charge_cur  (orig bmsChargeCur, I)
    #   battery_charge_vol  (orig batteryChargeVol, I)
    #   charge_flag  (orig chargeFlag, B)
    #   real_soc  (orig realSoc, B)
    #   charge_in_type  (orig chargeInType, B)
    #   ext_kit_type  (orig extKitType, B)
    #   low_power_flag  (orig lowPowerFlag, B)


class BmsData(RawData):
    """Battery management system (per-pack)."""

    hard_ware_ver: Annotated[int, "I", "hardWareVer"]
    card_id_num: Annotated[int, "I", "cardIdNum"]
    kit_num: Annotated[int, "I", "kitNum"]
    bms_type: Annotated[int, "B", "bmsType"]
    soc: Annotated[int, "B", "soc"]
    vol: Annotated[int, "I", "vol"]
    amp: Annotated[int, "I", "amp"]
    temp: Annotated[int, "B", "temp"]
    charge_state: Annotated[int, "B", "chargeState"]
    open_bms_state: Annotated[int, "B", "openBmsState"]
    design_capacity: Annotated[int, "I", "designCapacity"]
    full_capacity: Annotated[int, "I", "fullCapacity"]
    remain_capacity: Annotated[int, "I", "remainCapacity"]
    recycles: Annotated[int, "I", "recycles"]
    max_cell_vol: Annotated[int, "I", "maxCellVol"]
    min_cell_vol: Annotated[int, "I", "minCellVol"]
    max_cell_temp: Annotated[int, "B", "maxCellTemp"]
    min_cell_temp: Annotated[int, "B", "minCellTemp"]
    max_mos_temp: Annotated[int, "B", "maxMosTemp"]
    min_mos_temp: Annotated[int, "B", "minMosTemp"]
    bms_fault: Annotated[int, "B", "bmsFault"]
    int_put_watt: Annotated[int, "I", "intPutWatt"]
    out_put_watt: Annotated[int, "I", "outPutWatt"]
    remain_time: Annotated[int, "I", "remainTime"]
    ups_flag: Annotated[int, "B", "upsFlag"]
    chg_set_soc: Annotated[int, "I", "chgSetSoc"]
    dsg_set_soc: Annotated[int, "I", "dsgSetSoc"]
    ptc_allow_flag: Annotated[int, "B", "ptcAllowFlag"]
    ptc_touch_flag: Annotated[int, "B", "ptcTouchFlag"]
    ptc_heating_state: Annotated[int, "B", "ptcHeatingState"]
    ptc_heating_event: Annotated[int, "B", "ptcHeatingEvent"]
    ptc_heat_err_count: Annotated[int, "B", "ptcHeatErrCount"]
    ptc_remain_time: Annotated[int, "I", "ptcRemainTime"]
    lcd_standby_min: Annotated[int, "I", "lcdStandbyMin"]
    oil_start_soc: Annotated[int, "I", "oilStartSoc"]
    oil_stop_soc: Annotated[int, "I", "oilStopSoc"]
    warn_code: Annotated[int, "I", "warnCode"]
    event_code: Annotated[int, "I", "eventCode"]


class IcHighData(RawData):
    """AC inverter/charger (IC) sub-module."""

    in_vol: Annotated[int, "I", "inVol"]
    in_cur: Annotated[int, "I", "inCur"]
    in_watt: Annotated[int, "I", "inWatt"]
    out_vol: Annotated[int, "I", "outVol"]
    out_cur: Annotated[int, "I", "outCur"]
    out_watt: Annotated[int, "I", "outWatt"]
    out_va: Annotated[int, "I", "outVa"]
    ac_temp: Annotated[int, "h", "acTemp"]
    inv_type: Annotated[int, "B", "invType"]
    in_freq: Annotated[int, "B", "inFreq"]
    out_freq: Annotated[int, "B", "outFreq"]
    inv_switch_state: Annotated[int, "B", "invSwitchState"]
    cfg_out_freq: Annotated[int, "B", "cfgOutFreq"]
    day_input_energy: Annotated[int, "I", "dayInputEnergy"]
    day_output_energy: Annotated[int, "I", "dayOutputEnergy"]

    # TODO(capture): the following trailing fields are interrupted by a
    # variable-length array / nested struct and need a live capture to
    # confirm size/offset before they can be added:
    #   app_to_iccfg  (orig appToICCfg, array/nested/string)
    #   ac_output_power  (orig acOutputPower, I)
    #   ac_output_cur  (orig acOutputCur, I)
    #   stand_by_time  (orig standByTime, I)
    #   pass_by_mode_en  (orig passByModeEn, I)


class BmsTotalData(RawData):
    """Aggregated battery/system totals."""

    total_soc: Annotated[int, "B", "totalSoc"]
    total_chg_dsg_state: Annotated[int, "B", "totalChgDsgState"]
    total_input_watt: Annotated[int, "I", "totalInputWatt"]
    total_output_watt: Annotated[int, "I", "totalOutputWatt"]
    total_remain_time: Annotated[int, "I", "totalRemainTime"]
    remind_dsg_ptc_flag: Annotated[int, "B", "remindDsgPtcFlag"]
    bms_chg_stop_soc: Annotated[int, "I", "bmsChgStopSoc"]
    bms_dsg_stop_soc: Annotated[int, "I", "bmsDsgStopSoc"]
    oil_chg_start_soc: Annotated[int, "I", "oilChgStartSoc"]
    oil_chg_stop_soc: Annotated[int, "I", "oilChgStopSoc"]
    double_oil_error_flag: Annotated[int, "B", "doubleOilErrorFlag"]
    lcd_off_confirm_s: Annotated[int, "I", "lcdOffConfirmS"]
    warn_event: Annotated[int, "B", "warnEvent"]
    total_full_cap: Annotated[int, "I", "totalFullCap"]
    total_amp: Annotated[int, "I", "totalAmp"]
    bp_stand_by_time: Annotated[int, "I", "bpStandByTime"]
