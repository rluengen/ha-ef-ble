"""
EcoFlow Power Hub (MM100) BLE telemetry structs.

The Power Hub ("Power Kit" central unit, serial ``M3H1*`` / BLE name ``EF-M35*``) reports
each internal sub-module (solar MPPT, DC-DC converters, inverter, BMS, AC/DC distribution,
generator) as a packed fixed-width binary payload. Field order and widths below are the
BLE wire layout, recovered from the EcoFlow Android app packet parser (obfuscated class
``ld.f`` in app 5.4.5, ``p50.g`` "MM100ParseHelper" in app 6.17.7.12, which the offsets
below were re-checked against) and validated against ~15k live decrypted frames. Gaps the
app parser skips are kept as ``reserved`` byte blocks so later fields stay aligned. Each
field follows the same
``Annotated[<pytype>, <struct_fmt>, <originalCamelCaseName>]`` convention as the other
``RawData`` models in this package.

Wire layout notes (confirmed against the parser bytecode + captures):
  * Serial-prefixed sub-module frames start with a 16-byte ASCII ``sn`` then, for most
    modules, a 4-byte ``errCode``/``pv*ErrorCode`` and a 4-byte ``sysVer`` (packed as an
    ``int[4]`` firmware version in the app; we keep it as a single ``I``).
  * ``batteryCur``/``*Watt``/``*Cur`` are signed (``i``/``h``) - a negative value is
    discharge/reverse flow (verified: batteryCur read back as -16 while idle).
  * Heat-sink/PCB temperatures are signed 16-bit (``h``), in whole degrees C.
  * Voltages are milli-volts, currents milli-amps, power whole watts.
    (verified e.g. BbcOut ldOutVol=13555 -> 13.5 V, ldOutCur=671..4840 mA,
    ldOutWatt=9..65 W all self-consistent; Scc batteryVol=53081 -> 53.1 V.)
"""

from typing import Annotated

from .base import RawData


class SccData(RawData):
    """MPPT solar charge controller sub-module (PV1/PV2). Frame 0x05/0x05/0x20."""

    sn: Annotated[bytes, "16s", "sn"]
    pv1_error_code: Annotated[int, "I", "pv1ErrorCode"]
    pv2_error_code: Annotated[int, "I", "pv2ErrorCode"]
    sys_ver: Annotated[int, "I", "sysVer"]
    battery_vol: Annotated[int, "I", "batteryVol"]
    battery_cur: Annotated[int, "i", "batteryCur"]
    battery_watt: Annotated[int, "i", "batteryWatt"]
    pv1_in_vol: Annotated[int, "I", "pv1InVol"]
    pv1_in_cur: Annotated[int, "i", "pv1InCur"]
    pv1_in_watt: Annotated[int, "i", "pv1InWatt"]
    pv2_in_vol: Annotated[int, "I", "pv2InVol"]
    pv2_in_cur: Annotated[int, "i", "pv2InCur"]
    pv2_in_watt: Annotated[int, "i", "pv2InWatt"]
    l1_cur: Annotated[int, "i", "l1Cur"]
    l2_cur: Annotated[int, "i", "l2Cur"]
    hs1_temp: Annotated[int, "h", "hs1Temp"]
    hs2_temp: Annotated[int, "h", "hs2Temp"]
    pcb_temp: Annotated[int, "h", "pcbTemp"]
    pv1_work_mode: Annotated[int, "B", "pv1WorkMode"]
    pv2_work_mode: Annotated[int, "B", "pv2WorkMode"]
    mppt1_switch_state: Annotated[int, "B", "mppt1SwitchState"]
    mppt2_switch_state: Annotated[int, "B", "mppt2SwitchState"]
    pv1_input_flag: Annotated[int, "B", "pv1InputFlag"]
    pv2_input_flag: Annotated[int, "B", "pv2InputFlag"]
    reserved: Annotated[bytes, "4s", "reserved"]
    day_energy: Annotated[int, "I", "dayEnergy"]
    total_energy: Annotated[int, "I", "totalEnergy"]
    pv1_cable_length: Annotated[int, "I", "pv1CableLength"]
    pv2_cable_length: Annotated[int, "I", "pv2CableLength"]
    pv1_len_unit_flag: Annotated[int, "B", "pv1LenUnitFlag"]
    pv2_len_unit_flag: Annotated[int, "B", "pv2LenUnitFlag"]
    pv1_hot_out: Annotated[int, "B", "pv1HotOut"]
    pv2_hot_out: Annotated[int, "B", "pv2HotOut"]
    warn_code1: Annotated[int, "H", "warnCode1"]
    event_code1: Annotated[int, "H", "eventCode1"]
    warn_code2: Annotated[int, "H", "warnCode2"]
    event_code2: Annotated[int, "H", "eventCode2"]
    pv1_vol_limit: Annotated[int, "H", "pv1VolLimit"]
    pv2_vol_limit: Annotated[int, "H", "pv2VolLimit"]
    pv1_vol_limit_enable: Annotated[int, "B", "pv1VolLimitEnable"]
    pv2_vol_limit_enable: Annotated[int, "B", "pv2VolLimitEnable"]


class BbcInData(RawData):
    """BBC DC-DC input: solar / alternator / vehicle DC charging. Frame 0x50/0x50/0x20."""

    sn: Annotated[bytes, "16s", "sn"]
    err_code: Annotated[int, "I", "errCode"]
    sys_ver: Annotated[int, "I", "sysVer"]
    dc_input_vol: Annotated[int, "I", "dcInputVol"]
    dc_input_cur: Annotated[int, "i", "dcInputCur"]
    dc_input_watt: Annotated[int, "i", "dcInputWatt"]
    battery_vol: Annotated[int, "I", "batteryVol"]
    battery_cur: Annotated[int, "i", "batteryCur"]
    battery_watt: Annotated[int, "i", "batteryWatt"]
    l1_cur: Annotated[int, "i", "l1Cur"]
    l2_cur: Annotated[int, "i", "l2Cur"]
    hs1_temp: Annotated[int, "h", "hs1Temp"]
    hs2_temp: Annotated[int, "h", "hs2Temp"]
    pcb_temp: Annotated[int, "h", "pcbTemp"]
    work_mode: Annotated[int, "B", "workMode"]
    charge_pause: Annotated[int, "B", "chargePause"]
    max_config_charge_cur: Annotated[int, "i", "maxConfigChargeCur"]
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
    warn_code: Annotated[int, "H", "warnCode"]
    event_code: Annotated[int, "H", "eventCode"]
    work_mode2: Annotated[int, "B", "workMode2"]
    allow_dsg_on: Annotated[int, "B", "allowDsgOn"]
    alt_limit_vol: Annotated[int, "H", "altLimitVol"]
    alt_vol_limit_enable: Annotated[int, "B", "altVolLimitEnable"]
    third_watts: Annotated[int, "i", "thirdWatts"]


class BbcOutData(RawData):
    """BBC DC-DC output: DC loads. Frame 0x51/0x51/0x20."""

    sn: Annotated[bytes, "16s", "sn"]
    err_code: Annotated[int, "I", "errCode"]
    sys_ver: Annotated[int, "I", "sysVer"]
    battery_vol: Annotated[int, "I", "batteryVol"]
    battery_cur: Annotated[int, "i", "batteryCur"]
    battery_watt: Annotated[int, "i", "batteryWatt"]
    ld_out_vol: Annotated[int, "I", "ldOutVol"]
    ld_out_cur: Annotated[int, "i", "ldOutCur"]
    ld_out_watt: Annotated[int, "i", "ldOutWatt"]
    l1_cur: Annotated[int, "i", "l1Cur"]
    l2_cur: Annotated[int, "i", "l2Cur"]
    hs1_temp: Annotated[int, "h", "hs1Temp"]
    hs2_temp: Annotated[int, "h", "hs2Temp"]
    pcb_temp: Annotated[int, "h", "pcbTemp"]
    work_mode: Annotated[int, "B", "workMode"]
    dc_switch_mode: Annotated[int, "B", "dcSwitchMode"]
    dc_output_vol_tag: Annotated[int, "B", "dcOutputVolTag"]
    reserved: Annotated[bytes, "3s", "reserved"]
    day_energy: Annotated[int, "I", "dayEnergy"]
    total_energy: Annotated[int, "I", "totalEnergy"]
    warn_code: Annotated[int, "H", "warnCode"]
    event_code: Annotated[int, "H", "eventCode"]
    standby_time: Annotated[int, "H", "standbyTime"]


class InvData(RawData):
    """
    Low-voltage inverter/charger sub-module (M1095-PSDL). Frame 0x02/0x02/0x04.

    NOTE: field offsets past ``sys_ver`` follow the app parser's Power Hub (product type
    62) branch but have not been cross-validated against a live capture with the LV
    inverter active, so no sensors are wired from this struct yet (the HV AC inverter is
    ``IcHighData``).
    """

    sn: Annotated[bytes, "16s", "sn"]
    err_code: Annotated[int, "I", "errCode"]
    sys_ver: Annotated[int, "I", "sysVer"]
    warn_code: Annotated[int, "H", "warnCode"]
    event_code: Annotated[int, "H", "eventCode"]
    battery_cur: Annotated[int, "i", "batteryCur"]
    bus_vol: Annotated[int, "I", "busVol"]
    dc_temp: Annotated[int, "h", "dcTemp"]
    fan_level: Annotated[int, "B", "fanLevel"]
    charger_type: Annotated[int, "B", "chargerType"]


class IcHighData(RawData):
    """
    High-voltage AC inverter/charger (IC, M1095-PSDH). Frame 0x04/0x04/0x06.

    This is the module that produces/consumes household AC; `inv_switch_state` is the
    AC inverter on/off state. The app parser (`p50.g.j0`) reads `appToICCfg` at fixed
    offsets starting at byte 60, including `acChgDisable` at byte 64.
    """

    sn: Annotated[bytes, "16s", "sn"]
    in_vol: Annotated[int, "I", "inVol"]
    in_cur: Annotated[int, "i", "inCur"]
    in_watt: Annotated[int, "i", "inWatt"]
    out_vol: Annotated[int, "I", "outVol"]
    out_cur: Annotated[int, "i", "outCur"]
    out_watt: Annotated[int, "i", "outWatt"]
    out_va: Annotated[int, "I", "outVa"]
    ac_temp: Annotated[int, "h", "acTemp"]
    inv_type: Annotated[int, "B", "invType"]
    in_freq: Annotated[int, "B", "inFreq"]
    out_freq: Annotated[int, "B", "outFreq"]
    inv_switch_state: Annotated[int, "B", "invSwitchState"]
    cfg_out_freq: Annotated[int, "B", "cfgOutFreq"]
    reserved: Annotated[bytes, "1s", "reserved"]
    day_input_energy: Annotated[int, "I", "dayInputEnergy"]
    day_output_energy: Annotated[int, "I", "dayOutputEnergy"]
    app_to_ic_cfg_prefix: Annotated[bytes, "4s", "appToICCfg"]
    ac_chg_disable: Annotated[int, "B", "acChgDisable"]


class DCData(RawData):
    """
    DC distribution panel (M3L1 smart panel). Frame 0x54/0x54/0x20, dsrc 0x11.

    Sixteen DC output channels, each with a current and power reading and an on/off state
    bit in ``ch_states``. Channels 1-12 are in the base frame; channels 13-16 are in the
    V2 extension the app parses from frames of at least 215 bytes (older firmware sends
    141 bytes and those fields stay ``None``). ``relay_state`` holds the panel's six relay
    (high-current / non-switched) circuit bits. Validated against live frames: input_vol
    ~13.6 V, per-channel power in whole watts, current in mA. Error-code, version and
    relay blocks are kept as raw bytes purely to hold offsets.
    """

    sn: Annotated[bytes, "16s", "sn"]
    error_code: Annotated[bytes, "8s", "errorCode"]
    sys_ver: Annotated[bytes, "4s", "sysVer"]
    input_vol: Annotated[int, "I", "inputVol"]
    ch1_current: Annotated[int, "i", "channelCur1"]
    ch2_current: Annotated[int, "i", "channelCur2"]
    ch3_current: Annotated[int, "i", "channelCur3"]
    ch4_current: Annotated[int, "i", "channelCur4"]
    ch5_current: Annotated[int, "i", "channelCur5"]
    ch6_current: Annotated[int, "i", "channelCur6"]
    ch7_current: Annotated[int, "i", "channelCur7"]
    ch8_current: Annotated[int, "i", "channelCur8"]
    ch9_current: Annotated[int, "i", "channelCur9"]
    ch10_current: Annotated[int, "i", "channelCur10"]
    ch11_current: Annotated[int, "i", "channelCur11"]
    ch12_current: Annotated[int, "i", "channelCur12"]
    ch1_power: Annotated[int, "i", "chPower1"]
    ch2_power: Annotated[int, "i", "chPower2"]
    ch3_power: Annotated[int, "i", "chPower3"]
    ch4_power: Annotated[int, "i", "chPower4"]
    ch5_power: Annotated[int, "i", "chPower5"]
    ch6_power: Annotated[int, "i", "chPower6"]
    ch7_power: Annotated[int, "i", "chPower7"]
    ch8_power: Annotated[int, "i", "chPower8"]
    ch9_power: Annotated[int, "i", "chPower9"]
    ch10_power: Annotated[int, "i", "chPower10"]
    ch11_power: Annotated[int, "i", "chPower11"]
    ch12_power: Annotated[int, "i", "chPower12"]
    total_power: Annotated[int, "i", "totalPower"]
    temp0: Annotated[int, "h", "temp0"]
    temp1: Annotated[int, "h", "temp1"]
    relay_state: Annotated[int, "B", "relayState"]
    ch_states: Annotated[int, "H", "chStates"]
    ch_enable_states: Annotated[int, "H", "chEnableStates"]
    error_code_new: Annotated[bytes, "26s", "errorCodeNew"]
    ch13_current: Annotated[int, "i", "dcChCurV2[0]"]
    ch14_current: Annotated[int, "i", "dcChCurV2[1]"]
    ch15_current: Annotated[int, "i", "dcChCurV2[2]"]
    ch16_current: Annotated[int, "i", "dcChCurV2[3]"]
    ch13_power: Annotated[int, "i", "dcChPWattV2[0]"]
    ch14_power: Annotated[int, "i", "dcChPWattV2[1]"]
    ch15_power: Annotated[int, "i", "dcChPWattV2[2]"]
    ch16_power: Annotated[int, "i", "dcChPWattV2[3]"]
    error_code_new2: Annotated[bytes, "8s", "errorCodeNew2"]
    relay_v2: Annotated[bytes, "4s", "dcChRelayV2"]
    ld_dc_cfg_cnt: Annotated[int, "I", "ldDcCfgCnt"]


class ACData(RawData):
    """
    AC distribution panel. Frame 0x53/0x53/0x20.

    Six AC output circuits, each with a current (mA) and power (W) reading and an on/off
    bit in ``ch_states`` (bit i = circuit i+1). Layout follows the app parser
    (``p50.g.d`` "parseAcInfo"), which reads the 14-byte ``errorCodeNew`` block from
    frames of at least 101 bytes and the remaining tail from frames of at least 118
    bytes. Not yet validated against a live capture.
    """

    sn: Annotated[bytes, "16s", "sn"]
    error_code: Annotated[bytes, "5s", "errorCode"]
    sys_ver: Annotated[bytes, "4s", "sysVer"]
    input_vol: Annotated[int, "i", "inputVol"]
    ch1_current: Annotated[int, "i", "channelCur1"]
    ch2_current: Annotated[int, "i", "channelCur2"]
    ch3_current: Annotated[int, "i", "channelCur3"]
    ch4_current: Annotated[int, "i", "channelCur4"]
    ch5_current: Annotated[int, "i", "channelCur5"]
    ch6_current: Annotated[int, "i", "channelCur6"]
    ch1_power: Annotated[int, "i", "chPower1"]
    ch2_power: Annotated[int, "i", "chPower2"]
    ch3_power: Annotated[int, "i", "chPower3"]
    ch4_power: Annotated[int, "i", "chPower4"]
    ch5_power: Annotated[int, "i", "chPower5"]
    ch6_power: Annotated[int, "i", "chPower6"]
    total_power: Annotated[int, "i", "totalPower"]
    temp0: Annotated[int, "h", "temp0"]
    temp1: Annotated[int, "h", "temp1"]
    ch_states: Annotated[int, "B", "chStates"]
    ch_enable_states: Annotated[int, "B", "chEnableStates"]
    error_code_new: Annotated[bytes, "14s", "errorCodeNew"]
    ac_in_vol2: Annotated[int, "i", "acInVol2"]
    ac_all_p_watts1: Annotated[int, "i", "acAllPWatts1"]
    ac_all_p_watts2: Annotated[int, "i", "acAllPWatts2"]
    ld_ac_cfg_cnt: Annotated[int, "i", "ldACCfgCnt"]
    can_res_ctrl_mode: Annotated[int, "B", "canResCtrlMode"]


class BmsData(RawData):
    """
    Battery management system (per-pack). Frame 0x03/0x03/0x1A.

    Layout follows the app parser (``p50.g.A``): the app drops frames shorter than the
    106-byte base struct and reads the optional tail in steps at 108, 118, 122 and 123
    bytes. Not yet validated against a live capture.
    """

    sn: Annotated[bytes, "16s", "sn"]
    err_code: Annotated[int, "I", "errCode"]
    sys_ver: Annotated[bytes, "4s", "sysVer"]
    hard_ware_ver: Annotated[int, "I", "hardWareVer"]
    card_id_num: Annotated[int, "I", "cardIdNum"]
    kit_num: Annotated[int, "I", "kitNum"]
    bms_type: Annotated[int, "B", "bmsType"]
    soc: Annotated[int, "B", "soc"]
    vol: Annotated[int, "I", "vol"]
    amp: Annotated[int, "i", "amp"]
    temp: Annotated[int, "b", "temp"]
    charge_state: Annotated[int, "B", "chargeState"]
    open_bms_state: Annotated[int, "B", "openBmsState"]
    design_capacity: Annotated[int, "I", "designCapacity"]
    full_capacity: Annotated[int, "I", "fullCapacity"]
    remain_capacity: Annotated[int, "I", "remainCapacity"]
    recycles: Annotated[int, "I", "recycles"]
    max_cell_vol: Annotated[int, "I", "maxCellVol"]
    min_cell_vol: Annotated[int, "I", "minCellVol"]
    max_cell_temp: Annotated[int, "b", "maxCellTemp"]
    min_cell_temp: Annotated[int, "b", "minCellTemp"]
    max_mos_temp: Annotated[int, "b", "maxMosTemp"]
    min_mos_temp: Annotated[int, "b", "minMosTemp"]
    bms_fault: Annotated[int, "B", "bmsFault"]
    int_put_watt: Annotated[int, "i", "intPutWatt"]
    out_put_watt: Annotated[int, "i", "outPutWatt"]
    remain_time: Annotated[int, "I", "remainTime"]
    ups_flag: Annotated[int, "B", "upsFlag"]
    chg_set_soc: Annotated[int, "B", "chgSetSoc"]
    dsg_set_soc: Annotated[int, "B", "dsgSetSoc"]
    ptc_allow_flag: Annotated[int, "b", "ptcAllowFlag"]
    ptc_touch_flag: Annotated[int, "b", "ptcTouchFlag"]
    ptc_heating_state: Annotated[int, "b", "ptcHeatingState"]
    ptc_heating_event: Annotated[int, "B", "ptcHeatingEvent"]
    ptc_heat_err_count: Annotated[int, "B", "ptcHeatErrCount"]
    ptc_remain_time: Annotated[int, "I", "ptcRemainTime"]
    lcd_standby_min: Annotated[int, "I", "lcdStandbyMin"]
    oil_start_soc: Annotated[int, "B", "oilStartSoc"]
    oil_stop_soc: Annotated[int, "B", "oilStopSoc"]
    reserved: Annotated[bytes, "6s", "reserved"]
    warn_code: Annotated[int, "H", "warnCode"]
    event_code: Annotated[int, "H", "eventCode"]
    illegality_d_addr_flag: Annotated[int, "B", "illegalityDAddrFlag"]
    para_soc: Annotated[int, "B", "paraSoc"]
    design_energy: Annotated[int, "H", "designEnergy"]
    cal_type: Annotated[int, "B", "calType"]

    BASE_SIZE = 106


class BmsTotalData(RawData):
    """
    Aggregated battery/system totals. Frame 0x03/0x03/0x1C.

    Validated against live captures: totalSoc (0x36 -> 54 %, 0x32 -> 50 %) and
    totalInputWatt (0 while idle) / totalOutputWatt.
    """

    total_soc: Annotated[int, "B", "totalSoc"]
    total_chg_dsg_state: Annotated[int, "B", "totalChgDsgState"]
    total_input_watt: Annotated[int, "i", "totalInputWatt"]
    total_output_watt: Annotated[int, "i", "totalOutputWatt"]
    total_remain_time: Annotated[int, "I", "totalRemainTime"]
    remind_dsg_ptc_flag: Annotated[int, "B", "remindDsgPtcFlag"]
    bms_chg_stop_soc: Annotated[int, "B", "bmsChgStopSoc"]
    bms_dsg_stop_soc: Annotated[int, "B", "bmsDsgStopSoc"]
    oil_chg_start_soc: Annotated[int, "B", "oilChgStartSoc"]
    oil_chg_stop_soc: Annotated[int, "B", "oilChgStopSoc"]
    double_oil_error_flag: Annotated[int, "B", "doubleOilErrorFlag"]
    lcd_off_confirm_s: Annotated[int, "I", "lcdOffConfirmS"]
    warn_event: Annotated[int, "B", "warnEvent"]
    total_full_cap: Annotated[int, "H", "totalFullCap"]
    total_amp: Annotated[int, "H", "totalAmp"]
    bp_stand_by_time: Annotated[int, "H", "bpStandByTime"]


class ModuleStateData(RawData):
    """
    One sub-module record of the module-state frame 0x35/0x35/0x11.

    The frame is a list of these 34-byte records, one per connected module. Layout
    follows the app parser (``p50.g.p0``). ``src_addr`` is the module's bus address
    (3 = battery pack) and ``custom`` encodes a pack's group and position, from which
    the app derives the pack's slot. Not yet validated against a live capture.
    """

    version: Annotated[int, "B", "version"]
    sn: Annotated[bytes, "16s", "sn"]
    run_state: Annotated[int, "b", "runState"]
    product_detail: Annotated[int, "B", "productDetail"]
    product_type: Annotated[int, "B", "productType"]
    versions: Annotated[bytes, "8s", "versions"]
    custom: Annotated[int, "I", "custom"]
    src_addr: Annotated[int, "b", "srcAddr"]
    d_src_addr: Annotated[int, "B", "dSrcAddr"]
