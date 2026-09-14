from tespy.networks import Network
from tespy.components import (
    CycleCloser, Pump, Condenser, Turbine,
    SimpleHeatExchanger, Source, Sink,
    HeatExchanger, Merge, Splitter, Valve,
    DropletSeparator
)

from MultistageTurbine import MultiStageExtractionTurbine

from tespy.connections import Connection

from ts_diagram import plot_ts_diagram

import math
import pandas as pd

cooling_fluid = {"water": 1}
working_fluid = {"water": 1}


def _port_qualifier(component, port):
    """Disambiguate a port when a component has more than one inlet or outlet."""
    kind = type(component).__name__
    if kind in ("HeatExchanger", "Condenser"):
        return "hot" if port.endswith("1") else "cold"
    if kind == "DropletSeparator":
        if port == "out1":
            return "liquid"
        if port == "out2":
            return "vapour"
        return None
    if kind == "MultiStageExtractionTurbine" and port.startswith("out"):
        stage = int(port[3:])
        n_stages = int(component.num_stages.val)
        if stage == n_stages:
            return "exhaust"
        return f"stage {stage} extraction"
    return None


def _end_name(component, port):
    qualifier = _port_qualifier(component, port)
    if qualifier:
        return f"{component.label} ({qualifier})"
    return component.label


def connection_stream_label(conn, network):
    """One label per stream: 'Inlet to <target> — outlet of <source>'.

    The cycle closer is a TESPy numerical device, not plant hardware, so its
    two connections are the same main-steam line and are collapsed to one row.
    """
    source, source_port = conn.source, conn.source_id
    target, target_port = conn.target, conn.target_id

    if isinstance(target, CycleCloser):
        return None
    if isinstance(source, CycleCloser):
        for other in network.conns["object"]:
            if other.target is source:
                source, source_port = other.source, other.source_id
                break

    return (
        f"Inlet to {_end_name(target, target_port)}, "
        f"outlet of {_end_name(source, source_port)}"
    )


def export_connections_to_excel(network, path, connections=None):
    """Write unique connection states (m, T, p, h) with inlet/outlet labels."""
    rows = []
    used_labels = {}
    stream_list = connections if connections is not None else network.conns["object"]
    for conn in stream_list:
        label = connection_stream_label(conn, network)
        if label is None:
            continue
        if label in used_labels:
            label = f"{label} [{conn.source_id} to {conn.target_id}]"
        used_labels[label] = True
        rows.append({
            "Connection": label,
            "m (kg/s)": conn.m.val,
            "T (K)": conn.T.val,
            "p (Pa)": conn.p.val,
            "h (J/kg)": conn.h.val,
        })

    frame = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Connections", index=False)
        sheet = writer.sheets["Connections"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        widths = {"A": 88, "B": 14, "C": 12, "D": 16, "E": 16}
        for column, width in widths.items():
            sheet.column_dimensions[column].width = width
        from openpyxl.styles import Font
        header_font = Font(bold=True)
        for cell in sheet[1]:
            cell.font = header_font
        for row in sheet.iter_rows(min_row=2, min_col=2, max_col=5):
            row[0].number_format = "0.00"
            row[1].number_format = "0.00"
            row[2].number_format = "0.00E+00"
            row[3].number_format = "0.0"
    print(f"Wrote {len(frame)} connections to {path}")


def solve_ap1000(
        p_main_steam=5.571e6,
        h_main_steam=2785.6e3,
        p_hp_bleed_1=3.413025e6,  # 495 psia, 1st-stage reheat (DCD Fig 10.1-1)
        p_hp_bleed_2=2.8269e6,    # 410 psia, HP FWH 7
        p_hp_bleed_3=1785742.14,    # 259 psia, HP FWH 6
        p_hp_exhaust=1.1328e6,    # 164.3 psia, HP exhaust / MSH
        T_reheat_stage_1=490.0,
        T_lp_inlet=527.7,         # 490.2 F at the CIV
        p_lp_bleed_1=0.2889e6,    # 41.9 psia -> LP FWH 4
        p_lp_bleed_4=0.2565e6,    # 37.2 psia -> LP FWH 3
        p_lp_bleed_2=0.08660e6,   # 12.56 psia -> LP FWH 2
        p_lp_bleed_3=0.03930e6,   # 5.70 psia -> LP FWH 1
        p_condenser=8466.0,       # 2.50 inHg abs
        p_condensate=1.28e6,      # condensate-pump discharge, lands at DA pressure
        p_lp_fwh_4_shell=0.4137e6,  # unused; LP FWH 4 now follows p_lp_bleed_1
        ttd_u_fwh=2.222,          # 4 F heater TTD on Fig 10.1-1
        ttd_l_drain_cooler=5.556, # 10 F drain-cooler approach on Fig 10.1-1
        T_cw_in=303.65,
        T_cw_out=307.15,
        p_cw=1.2e5,
        steam_generator_duty=1707e6,
        pr_steam_generator=0.97,
        print_results=True,
        design_point_out=None,
):
    eta_s_hp_turbine=[0.8275, 0.9226, 0.8939, 0.8834]
    eta_s_lp_turbine = [0.8855,0.9051,0.8944,0.8248]#0.84
    eta_s_condensate_pump = 0.80
    eta_s_feed_pump = 0.80

    AP1000_plant = Network()
    AP1000_plant.units.set_defaults(
        temperature="K",
        pressure="Pa",
        pressure_difference="Pa",
        enthalpy="J/kg",
        heat="W",
        power="W",
        mass_flow="kg/s"
    )

    cwso = Source("cooling water source")
    cwsi = Sink("cooling water sink")

    cc = CycleCloser("cycle closer")

    # Two steam generators, as built: the feedwater splits between them and the two
    # main steam headers recombine ahead of the turbine stop valves.
    steam_generator_1 = SimpleHeatExchanger("steam generator 1")
    steam_generator_2 = SimpleHeatExchanger("steam generator 2")
    feedwater_split = Splitter("feedwater splitter", num_out=2)
    main_steam_merge = Merge("main steam merge", num_in=2)

    condenser = Condenser("main condenser")
    condenser_merge = Merge("condenser merge", num_in=2)
    HP_turbine = MultiStageExtractionTurbine("HP turbine", num_stages=4)

    main_steam_split = Splitter("main steam splitter", num_out=2)

    moisture_separator = DropletSeparator("moisture separator")

    # Two-stage interstage reheat in process order. Heater 1 is the low-temperature
    # stage (HP turbine stage-1 bleed on the hot inlet). Heater 2 follows it and is
    # the high-temperature stage (main steam bled upstream of the HP turbine).
    interstage_heater_1 = HeatExchanger("interstage heater 1")
    interstage_heater_2 = HeatExchanger("interstage heater 2")
    interstage_heater_2_valve = Valve("interstage heater 2 drain valve")
    interstage_drain_merge = Merge("interstage heater drain merge", num_in=2)

    RH_FWH = HeatExchanger("reheater drain FWH")
    RH_FWH_valve = Valve("reheater drain FWH drain valve")
    HP_FWH_2_shell_merge = Merge("HP FWH 2 shell merge", num_in=2)

    # LP expansion: three turbine bodies in parallel off the reheater outlet.
    # Turbine 1 expands to LP FWH 4. Turbine 2 is a two-stage machine (FWH 3
    # then FWH 2). Turbine 3 extracts to LP FWH 1 and exhausts to the condenser.
    LP_inlet_split = Splitter("LP turbine inlet splitter", num_out=3)
    LP_turbine_1 = Turbine("LP turbine 1")
    LP_turbine_2 = MultiStageExtractionTurbine("LP turbine 2", num_stages=2)
    LP_turbine_3 = MultiStageExtractionTurbine("LP turbine 3", num_stages=2)

    condensate_pump = Pump("condenser pump")

    # Four-heater LP train, cascaded shell drains. LP FWH 1 is the coldest (fed
    # from the condenser); LP FWH 4 is the hottest. Each heater takes a bleed
    # from one of the parallel LP turbines. Each shell outlet is throttled
    # down to the next bleed pressure and merges with that bleed, and the last
    # drain lands on the condenser merge.
    LP_FWH_1 = HeatExchanger("LP FWH 1")
    LP_FWH_1_merge = Merge("LP FWH 1 shell merge", num_in=2)
    LP_FWH_1_valve = Valve("LP FWH 1 drain valve")

    LP_FWH_2 = HeatExchanger("LP FWH 2")
    LP_FWH_2_merge = Merge("LP FWH 2 shell merge", num_in=2)
    LP_FWH_2_valve = Valve("LP FWH 2 drain valve")

    LP_FWH_3 = HeatExchanger("LP FWH 3")
    LP_FWH_3_merge = Merge("LP FWH 3 shell merge", num_in=2)
    LP_FWH_3_valve = Valve("LP FWH 3 drain valve")

    LP_FWH_4 = HeatExchanger("LP FWH 4")
    LP_FWH_4_valve = Valve("LP FWH 4 drain valve")

    # DCD open deaerator (heater 5): LP feedwater + HP FWH drains + MSR drain
    # + a small HP-exhaust steam take-off. Outlet is saturated liquid to the
    # feed pump.
    hp_exhaust_split = Splitter("HP exhaust splitter", num_out=2)
    deaerator = Merge("deaerator", num_in=4)
    lp_to_da_valve = Valve("LP FWH 4 to deaerator valve")
    msr_to_da_valve = Valve("MSR drain to deaerator valve")

    HP_pump = Pump("feed pump")

    HP_FWH_2 = HeatExchanger("HP FWH 2")
    HP_FWH_1 = HeatExchanger("HP FWH 1")
    HP_FWH_M = Merge("HP FWH merge")

    HP_FWH_valve_1 = Valve("HP FWH drain valve 1")
    HP_FWH_valve_2 = Valve("HP FWH drain valve 2")

    c1 = Connection(cc, "out1", main_steam_split, "in1")
    c1a = Connection(main_steam_split, "out1", HP_turbine, "in1")
    c1b = Connection(main_steam_split, "out2", interstage_heater_2, "in1")

    # MultiStageExtractionTurbine: out1 is after stage 1 (highest outlet P),
    # outN is the exhaust (lowest P). Stage i+1 uses out{i}'s (p, h) as its inlet.
    c2_hp = Connection(HP_turbine, "out4", hp_exhaust_split, "in1")
    c2 = Connection(hp_exhaust_split, "out1", moisture_separator, "in1")
    c2_da = Connection(hp_exhaust_split, "out2", deaerator, "in4")

    # DropletSeparator: out1 is the saturated liquid drain, out2 the saturated vapour
    # that goes on to the interstage reheaters and the LP turbine.
    c2a = Connection(moisture_separator, "out2", interstage_heater_1, "in2")
    c2d = Connection(interstage_heater_1, "out2", interstage_heater_2, "in2")
    c2b = Connection(interstage_heater_2, "out2", LP_inlet_split, "in1")
    c2b1 = Connection(LP_inlet_split, "out1", LP_turbine_1, "in1")
    c2b2 = Connection(LP_inlet_split, "out2", LP_turbine_2, "in1")
    c2b3 = Connection(LP_inlet_split, "out3", LP_turbine_3, "in1")
    c2c = Connection(moisture_separator, "out1", msr_to_da_valve, "in1")
    c2c_da = Connection(msr_to_da_valve, "out1", deaerator, "in3")


    c30 = Connection(HP_turbine, "out1", interstage_heater_1, "in1")
    c31 = Connection(interstage_heater_2, "out1", interstage_heater_2_valve, "in1")
    c32 = Connection(interstage_heater_2_valve, "out1", interstage_drain_merge, "in1")
    c33 = Connection(interstage_heater_1, "out1", interstage_drain_merge, "in2")
    c34 = Connection(interstage_drain_merge, "out1", RH_FWH, "in1")
    c35 = Connection(RH_FWH, "out1", RH_FWH_valve, "in1")
    c36 = Connection(RH_FWH_valve, "out1", HP_FWH_2_shell_merge, "in2")

    c3 = Connection(HP_turbine, "out2", HP_FWH_2_shell_merge, "in1")
    c37 = Connection(HP_FWH_2_shell_merge, "out1", HP_FWH_2, "in1")


    c40 = Connection(LP_turbine_1, "out1", LP_FWH_4, "in1")
    c40b = Connection(LP_turbine_2, "out1", LP_FWH_3_merge, "in2")
    c42 = Connection(LP_turbine_2, "out2", LP_FWH_2_merge, "in2")
    c45 = Connection(LP_turbine_3, "out1", LP_FWH_1_merge, "in2")
    c5 = Connection(LP_turbine_3, "out2", condenser_merge, "in1")

    c6 = Connection(condenser_merge, "out1", condenser, "in1")

    c7 = Connection(condenser, "out1", condensate_pump, "in1")

    # Feedwater climbs the LP train from the condenser: FWH 1 -> 2 -> 3 -> 4.
    c8 = Connection(condensate_pump, "out1", LP_FWH_1, "in2")
    c60 = Connection(LP_FWH_1, "out2", LP_FWH_2, "in2")
    c61 = Connection(LP_FWH_2, "out2", LP_FWH_3, "in2")
    c62 = Connection(LP_FWH_3, "out2", LP_FWH_4, "in2")
    c9 = Connection(LP_FWH_4, "out2", lp_to_da_valve, "in1")
    c9d = Connection(lp_to_da_valve, "out1", deaerator, "in1")
    c9a = Connection(deaerator, "out1", HP_pump, "in1")

    # DCD: HP heater drains and the MSR drain go to the deaerator, not LP FWH 4.
    # LP FWH 4 is now an extraction heater; its drain still cascades 4 -> 3 -> 2 -> 1.
    c18 = Connection(HP_FWH_valve_1, "out1", deaerator, "in2")
    c19 = Connection(LP_FWH_4, "out1", LP_FWH_4_valve, "in1")
    c20 = Connection(LP_FWH_4_valve, "out1", LP_FWH_3_merge, "in1")
    c63 = Connection(LP_FWH_3_merge, "out1", LP_FWH_3, "in1")
    c64 = Connection(LP_FWH_3, "out1", LP_FWH_3_valve, "in1")
    c65 = Connection(LP_FWH_3_valve, "out1", LP_FWH_2_merge, "in1")
    c66 = Connection(LP_FWH_2_merge, "out1", LP_FWH_2, "in1")
    c67 = Connection(LP_FWH_2, "out1", LP_FWH_2_valve, "in1")
    c68 = Connection(LP_FWH_2_valve, "out1", LP_FWH_1_merge, "in1")
    c69 = Connection(LP_FWH_1_merge, "out1", LP_FWH_1, "in1")
    c70 = Connection(LP_FWH_1, "out1", LP_FWH_1_valve, "in1")
    c71 = Connection(LP_FWH_1_valve, "out1", condenser_merge, "in2")

    c10 = Connection(HP_pump, "out1", HP_FWH_1, "in2")

    c11 = Connection(HP_FWH_1, "out2", HP_FWH_2, "in2")

    c12 = Connection(HP_FWH_valve_2, "out1", HP_FWH_M, "in1")
    c13 = Connection(HP_turbine, "out3", HP_FWH_M, "in2")

    c14 = Connection(HP_FWH_M, "out1", HP_FWH_1, "in1")
    c15 = Connection(HP_FWH_1, "out1", HP_FWH_valve_1, "in1")

    c16 = Connection(HP_FWH_2, "out2", RH_FWH, "in2")
    c38 = Connection(RH_FWH, "out2", feedwater_split, "in1")

    c17 = Connection(HP_FWH_2, "out1", HP_FWH_valve_2, "in1")

    c39 = Connection(feedwater_split, "out1", steam_generator_1, "in1")
    c72 = Connection(feedwater_split, "out2", steam_generator_2, "in1")
    c73 = Connection(steam_generator_1, "out1", main_steam_merge, "in1")
    c74 = Connection(steam_generator_2, "out1", main_steam_merge, "in2")

    c0 = Connection(main_steam_merge, "out1", cc, "in1")

    # Condenser cooling connections
    c1_1 = Connection(cwso, "out1", condenser, "in2", label="11")
    c1_2 = Connection(condenser, "out2", cwsi, "in1", label="12")




    #Component Attributes

    condenser.set_attr(pr1=1, pr2=0.98)

    # Each steam generator carries its DCD rating of 1707 MWt, so the total NSSS heat
    # input is 3414 MWt and the main steam flow follows from the two duties.
    steam_generator_1.set_attr(pr=pr_steam_generator, Q=steam_generator_duty)
    steam_generator_2.set_attr(Q=steam_generator_duty)

    # Isentropic efficiencies are the DCD-consistent values that land the shaft output
    # at 1200 MW
    HP_turbine.set_attr(
    eta_s1=eta_s_hp_turbine[0], eta_s2=eta_s_hp_turbine[1],
    eta_s3=eta_s_hp_turbine[2], eta_s4=eta_s_hp_turbine[3],
    )
    LP_turbine_1.set_attr(eta_s=eta_s_lp_turbine[0])
    LP_turbine_2.set_attr(eta_s1=eta_s_lp_turbine[1], eta_s2=eta_s_lp_turbine[2])
    LP_turbine_3.set_attr(eta_s1=eta_s_lp_turbine[3], eta_s2=eta_s_lp_turbine[3])

    # Interstage heaters. Each shell condenses to x=0 (set on c31/c33) and each cold
    # outlet temperature is fixed (c2d, c2b), so the bleed mass flows follow from the
    # two energy balances. No ttd spec belongs here: the cold outlet temperature
    # already occupies that degree of freedom. pr2=0.98 per stage lands the LP inlet
    # at 1.088 MPa, inside the DCD's 1.073-1.096 MPa band.
    interstage_heater_2.set_attr(pr1=0.97, pr2=0.98)
    interstage_heater_1.set_attr(pr1=0.97, pr2=0.98)


    RH_FWH.set_attr(ttd_l=ttd_l_drain_cooler, pr1=0.97, pr2=0.97)


    HP_FWH_2.set_attr(
    ttd_u=ttd_u_fwh,
    pr1=0.97,
    pr2=0.97,
    )

    HP_FWH_1.set_attr(
    ttd_u=ttd_u_fwh,
    pr1=0.97,
    pr2=0.97
    )

    condensate_pump.set_attr(eta_s=eta_s_condensate_pump)

    # All four LP heaters are now steam-extraction condensing heaters. Each has a
    # free bleed flow, so x=0 on the drain plus ttd_u on the feedwater outlet
    # is exactly determined.
    LP_FWH_1.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)
    LP_FWH_2.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)
    LP_FWH_3.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)
    LP_FWH_4.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)

    HP_pump.set_attr(eta_s=eta_s_feed_pump)

    # COnnection Attributes

    # Condenser cooling connections
    c1_1.set_attr(T=T_cw_in, p=p_cw, fluid=cooling_fluid)
    c1_2.set_attr(T=T_cw_out)

    # Main steam, DCD Fig 10.1-1: 808 psia / 1197.6 BTU/lb. The flow follows from the
    # two steam generator duties, so only a start value is given here.
    c1.set_attr(p=p_main_steam, h=h_main_steam, m0=1891, fluid=working_fluid)
    c1a.set_attr(m0=1824, h0=2.786e6)  # main steam -> HP turbine
    c1b.set_attr(m0=61.3, h0=2.786e6)  # 486,692 lb/h 2nd-stage reheat take-off

    # HP turbine outlets: pressures fall along the stage order out1 -> ... -> out4.
    # Extraction masses are results of each heater's ttd_u. c13 is the DCD 251 psia
    # HP FWH 6 extraction; c3 is 410 psia to HP FWH 7.
    c2_hp.set_attr(p=p_hp_exhaust, m0=1452, h0=2.540e6)
    c2.set_attr(m0=1323, h0=2.540e6)
    c2_da.set_attr(m0=129, h0=2.540e6)
    c2a.set_attr(m0=1280, h0=2.782e6)
    c2d.set_attr(m0=1280, h0=2.863e6)
    c2b.set_attr(T=T_lp_inlet, m0=1280, h0=2.950e6)
    c2b1.set_attr(m0=43, h0=2.950e6)
    c2b2.set_attr(m0=118, h0=2.950e6)
    c2b3.set_attr(m0=1119, h0=2.950e6)
    c2c.set_attr(m0=172, h0=7.87e5)
    c2c_da.set_attr(m0=172, h0=7.87e5)
    c30.set_attr(p=p_hp_bleed_1, m=82.9, h0=2.740e6)  # 659,256 lb/h 1st-stage reheat
    c3.set_attr(p=p_hp_bleed_2, m0=92, h0=2.690e6)  # 410 psia -> HP FWH 2
    c13.set_attr(p=p_hp_bleed_3, m0=200, h0=2.620e6)  # 251 psia -> HP FWH 1


    c31.set_attr(x=0.05, m0=61, h0=1.179e6)
    c32.set_attr(m0=61, h0=1.179e6)
    c33.set_attr(x=0.05, m0=60, h0=1.079e6)
    c34.set_attr(m0=126, h0=1.132e6)
    c35.set_attr(m0=126, h0=9.93e5)
    c36.set_attr(m0=126, h0=9.93e5)
    c37.set_attr(m0=218, h0=1.706e6)


    c40.set_attr(p=p_lp_bleed_1, m0=43, h0=2.775e6)   # 41.9 psia -> LP FWH 4
    c40b.set_attr(p=p_lp_bleed_4, m0=75, h0=2.770e6)  # 37.2 psia -> LP FWH 3
    c42.set_attr(p=p_lp_bleed_2, m0=43, h0=2.550e6)   # 12.56 psia -> LP FWH 2
    c45.set_attr(p=p_lp_bleed_3, m0=1.002e1, h0=2.490e6)   # 5.70 psia -> LP FWH 1


    c5.set_attr(p=p_condenser, m0=1069, h0=2.350e6)

    c8.set_attr(p=p_condensate, m0=1286, h0=1.81e5)
    c9.set_attr(m0=1286, h0=5.27e5)
    c9d.set_attr(m0=1286, h0=5.27e5)

    c60.set_attr(m0=1286, h0=2.03e5)
    c61.set_attr(m0=1286, h0=3.09e5)
    c62.set_attr(m0=1286, h0=3.90e5)
    c9a.set_attr(x=0, m0=1887, h0=7.81e5)

    c10.set_attr(m0=1891, h0=6.203e5)
    c11.set_attr(m0=1891, h0=8.873e5)
    c16.set_attr(m0=1891, h0=9.706e5)
    c38.set_attr(m0=1891, h0=9.798e5)

    c39.set_attr(m0=945, h0=9.798e5)
    c72.set_attr(m0=945, h0=9.798e5)
    c73.set_attr(h=h_main_steam, m0=945)
    c74.set_attr(m0=945, h0=2.786e6)

    c14.set_attr(m0=502, h0=1.908e6)
    c15.set_attr(x=0, m0=502, h0=9.015e5)  # HP FWH 1 drain leaves as saturated liquid
    c17.set_attr(x=0, m0=218, h0=9.854e5)  # HP FWH 2 drain leaves as saturated liquid

    c18.set_attr(m0=306, h0=9.015e5)
    c19.set_attr(x=0, m0=43, h0=6.65e5)
    c20.set_attr(m0=43, h0=6.65e5)

    c63.set_attr(m0=118, h0=9.29e5)
    c64.set_attr(x=0, m0=118, h0=5.52e5)
    c65.set_attr(m0=118, h0=5.52e5)

    c66.set_attr(m0=794, h0=5.891e5)
    c67.set_attr(x=0, m0=794, h0=3.965e5)
    c68.set_attr(m0=794, h0=3.965e5)

    c69.set_attr(m0=884, h0=6.023e5)
    c70.set_attr(x=0, m0=884, h0=3.158e5)
    c71.set_attr(m0=884, h0=3.158e5)

    AP1000_plant.add_conns(
    c1, c1a, c1b, c2_hp, c2, c2_da, c2a, c2b, c2b1, c2b2, c2b3, c2c, c2c_da, c2d, c3, c5,
    c6, c7, c8, c9, c9d, c9a, c10, c11, c12, c13, c14, c15,
    c16, c17, c18, c19, c20, c0, c1_1, c1_2,
    c30, c31, c32, c33, c34, c35, c36, c37, c38, c39,
    c40, c40b, c42, c45,
    c60, c61, c62, c63, c64, c65, c66, c67, c68, c69, c70, c71,
    c72, c73, c74
)

    AP1000_plant.iterinfo = False
    failed = {
        "P_net": float("nan"),
        "P_turbine": float("nan"),
        "P_pumps": float("nan"),
        "efficiency": float("nan"),
        "solar_efficiency": float("nan"),
        "ex_nuclear": float("nan"),
        "ex_solar": 0.0,
        "efficiency_II": float("nan"),
    }
    try:
        AP1000_plant.solve(
            mode="design",
            block_solve=True,
            robust_relax=True,
            oscillation_damping=True,
            max_iter=700,
        )
    except Exception as e:
        if print_results:
            print(f"Error: {e}")
            AP1000_plant.print_variables()
            AP1000_plant.print_structural_analysis()
            AP1000_plant.print_incidence_matrix()
        return failed

    if print_results:
        print(f"Converged: {AP1000_plant.status == 0} (status={AP1000_plant.status})")

    if AP1000_plant.status != 0:
        if print_results:
            AP1000_plant.print_structural_analysis()
            AP1000_plant.print_variables()
            AP1000_plant.print_incidence_matrix()
            AP1000_plant.print_equations_with_dependents()
        return failed

    turbine_power = sum(
        t.P.val_SI for t in (
            HP_turbine, LP_turbine_1, LP_turbine_2, LP_turbine_3
        )
    )
    pump_power = condensate_pump.P.val_SI + HP_pump.P.val_SI
    net_power = -(turbine_power + pump_power)
    heat_input = steam_generator_1.Q.val_SI + steam_generator_2.Q.val_SI
    Q_nuclear = heat_input
    T_in = 273.15 + 324.7
    T_out = 273.15 + 281.835
    T_nuclear = (T_in - T_out) / math.log(T_in / T_out)
    ex_nuclear = Q_nuclear * (1 - (T_cw_in / T_nuclear))
    ex_solar = 0.0
    results = {
        "P_net": net_power,
        "P_turbine": -turbine_power,
        "P_pumps": pump_power,
        "efficiency": net_power / heat_input,
        "solar_efficiency": float("nan"),
        "ex_nuclear": ex_nuclear,
        "ex_solar": ex_solar,
        "efficiency_II": net_power / (ex_nuclear + ex_solar),
    }

    if print_results:
        AP1000_plant.print_results()
        print(f"main steam flow      : {c1.m.val_SI:.1f} kg/s")
        print(f"SG 1 duty            : {steam_generator_1.Q.val_SI / 1e6:.1f} MW")
        print(f"SG 2 duty            : {steam_generator_2.Q.val_SI / 1e6:.1f} MW")
        print(f"total heat input     : {heat_input / 1e6:.1f} MW")
        print(f"gross turbine power  : {-turbine_power / 1e6:.1f} MW")
        print(f"pump power           : {pump_power / 1e6:.1f} MW")
        print(f"net power            : {net_power / 1e6:.1f} MW")
        print(f"cycle efficiency     : {100 * net_power / heat_input:.2f} %")
        export_connections_to_excel(
            AP1000_plant,
            "AP1000_connection_results.xlsx",
            connections=[
                c73, c74, c1, c1a, c1b, c30, c3, c13, c2, c2c, c2c_da,
                c2a, c2d, c2b, c2b1, c2b2, c2b3, c31, c32, c33, c34, c35, c36,
                c37, c40, c40b, c42, c45, c5, c6, c7, c8, c60, c61, c62,
                c9, c9a, c10, c11, c16, c38, c39, c72, c12, c14, c15, c17,
                c18, c19, c20, c63, c64, c65, c66, c67, c68, c69, c70, c71,
                c1_1, c1_2,
            ],
        )
        plot_ts_diagram(
            AP1000_plant, "water", "AP1000_ts_diagram.svg",
            "T-s diagram of the AP1000 Rankine cycle",
        )

    if design_point_out is not None:
        design_point_out.update({"steam": AP1000_plant})
    return results


if __name__ == "__main__":
    solve_ap1000()


