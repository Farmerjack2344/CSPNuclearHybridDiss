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
        p_hp_bleed_1=3.413025e6,  #Changed
        p_hp_bleed_2=2.83e6,
        p_hp_bleed_3=2.0e6,
        p_hp_exhaust=1.133e6,
        T_reheat_stage_1=490.0,
        T_lp_inlet=527.7,
        p_lp_bleed_1=0.289e6,
        p_lp_bleed_2=0.086e6,
        p_lp_bleed_3=0.0405e6,
        p_condenser=7000.0,
        p_condensate=1.2e6,
        p_lp_fwh_4_shell=0.60e6,
        ttd_u_fwh=5.0,
        ttd_l_drain_cooler=5.0,
        T_cw_in=288.15,
        T_cw_out=300.15,
        p_cw=1.2e5,
        steam_generator_duty=1707e6,
        pr_steam_generator=0.97,
        print_results=True,
        design_point_out=None,
):
    eta_s_hp_turbine = 0.84
    eta_s_lp_turbine = 0.873
    eta_s_condensate_pump = 0.804
    eta_s_feed_pump = 0.804

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

    # LP expansion: three turbine bodies (a two-stage extraction turbine of the same
    # type as the HP turbine, then two single-stage turbines). Four outlet streams
    # leave the group: LP1 out1, LP1 out2, LP2 out1 and the LP3 exhaust. The first
    # three are the bleeds that feed the LP heater train, the last one is the
    # exhaust to the condenser.
    LP_turbine_stg1 = MultiStageExtractionTurbine("LP turbine stage 1", num_stages=2)
    LP_turbine_stg2 = Turbine("LP turbine stage 2")
    LP_turbine_stg3 = Turbine("LP turbine stage 3")

    # Only part of each LP body's outlet is bled off; the rest carries on expanding,
    # so every bleed below the first needs its own splitter.
    LP_bleed_split_1 = Splitter("LP stage 1 exhaust splitter", num_out=2)
    LP_bleed_split_2 = Splitter("LP stage 2 exhaust splitter", num_out=2)

    condensate_pump = Pump("condenser pump")

    # Four-heater LP train, cascaded shell drains. LP FWH 1 is the coldest (fed
    # from the condenser); LP FWH 4 is the hottest (HP FWH 1 drain). LP FWH 1/2/3
    # take the three LP bleeds in rising pressure. Each shell outlet is throttled
    # down to the next bleed pressure and merges with that bleed, and the last
    # drain lands on the condenser merge.
    LP_FWH_1 = HeatExchanger("LP FWH 1")
    LP_FWH_1_merge = Merge("LP FWH 1 shell merge", num_in=2)
    LP_FWH_1_valve = Valve("LP FWH 1 drain valve")

    LP_FWH_2 = HeatExchanger("LP FWH 2")
    LP_FWH_2_merge = Merge("LP FWH 2 shell merge", num_in=2)
    LP_FWH_2_valve = Valve("LP FWH 2 drain valve")

    LP_FWH_3 = HeatExchanger("LP FWH 3")
    LP_FWH_3_merge = Merge("LP FWH 3 shell merge", num_in=3)
    LP_FWH_3_valve = Valve("LP FWH 3 drain valve")

    LP_FWH_4 = HeatExchanger("LP FWH 4")
    LP_FWH_4_valve = Valve("LP FWH 4 drain valve")

    MSR_FWH = HeatExchanger("MSR drain FWH")
    MSR_FWH_valve = Valve("MSR drain FWH drain valve")

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
    c2 = Connection(HP_turbine, "out4", moisture_separator, "in1")

    # DropletSeparator: out1 is the saturated liquid drain, out2 the saturated vapour
    # that goes on to the interstage reheaters and the LP turbine.
    c2a = Connection(moisture_separator, "out2", interstage_heater_1, "in2")
    c2d = Connection(interstage_heater_1, "out2", interstage_heater_2, "in2")
    c2b = Connection(interstage_heater_2, "out2", LP_turbine_stg1, "in1")
    c2c = Connection(moisture_separator, "out1", MSR_FWH, "in1")

    # Interstage heater shell sides and their cascaded drains. Live-steam condensate
    # leaves heater 2 at header pressure and is throttled down to heater 1's shell.
    c30 = Connection(HP_turbine, "out1", interstage_heater_1, "in1")
    c31 = Connection(interstage_heater_2, "out1", interstage_heater_2_valve, "in1")
    c32 = Connection(interstage_heater_2_valve, "out1", interstage_drain_merge, "in1")
    c33 = Connection(interstage_heater_1, "out1", interstage_drain_merge, "in2")
    c34 = Connection(interstage_drain_merge, "out1", RH_FWH, "in1")
    c35 = Connection(RH_FWH, "out1", RH_FWH_valve, "in1")
    c36 = Connection(RH_FWH_valve, "out1", HP_FWH_2_shell_merge, "in2")

    c3 = Connection(HP_turbine, "out2", HP_FWH_2_shell_merge, "in1")
    c37 = Connection(HP_FWH_2_shell_merge, "out1", HP_FWH_2, "in1")

    # LP expansion and the three LP bleeds. Highest-pressure bleed to FWH 3,
    # then FWH 2, then FWH 1 (lowest pressure, nearest the condenser).
    c40 = Connection(LP_turbine_stg1, "out1", LP_FWH_3_merge, "in2")
    c41 = Connection(LP_turbine_stg1, "out2", LP_bleed_split_1, "in1")
    c42 = Connection(LP_bleed_split_1, "out1", LP_FWH_2_merge, "in2")
    c43 = Connection(LP_bleed_split_1, "out2", LP_turbine_stg2, "in1")
    c44 = Connection(LP_turbine_stg2, "out1", LP_bleed_split_2, "in1")
    c45 = Connection(LP_bleed_split_2, "out1", LP_FWH_1_merge, "in2")
    c46 = Connection(LP_bleed_split_2, "out2", LP_turbine_stg3, "in1")

    c5 = Connection(LP_turbine_stg3, "out1", condenser_merge, "in1")

    c6 = Connection(condenser_merge, "out1", condenser, "in1")

    c7 = Connection(condenser, "out1", condensate_pump, "in1")

    # Feedwater climbs the LP train from the condenser: FWH 1 -> 2 -> 3 -> 4.
    c8 = Connection(condensate_pump, "out1", LP_FWH_1, "in2")
    c60 = Connection(LP_FWH_1, "out2", LP_FWH_2, "in2")
    c61 = Connection(LP_FWH_2, "out2", LP_FWH_3, "in2")
    c62 = Connection(LP_FWH_3, "out2", LP_FWH_4, "in2")
    c9 = Connection(LP_FWH_4, "out2", MSR_FWH, "in2")
    c9a = Connection(MSR_FWH, "out2", HP_pump, "in1")

    # Cascaded LP shell drains: HP FWH 1 -> LP FWH 4 -> 3 -> 2 -> 1 -> condenser.
    c18 = Connection(HP_FWH_valve_1, "out1", LP_FWH_4, "in1")
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

    # The MSR drain leaves its cooler at ~420 K. Flashing it straight to the
    # condenser threw away ~50 MW; cascading it into the top of the LP shell train
    # instead lets that heat displace bleed steam.
    c21 = Connection(MSR_FWH, "out1", MSR_FWH_valve, "in1")
    c22 = Connection(MSR_FWH_valve, "out1", LP_FWH_3_merge, "in3")

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
    eta_s1=eta_s_hp_turbine, eta_s2=eta_s_hp_turbine,
    eta_s3=eta_s_hp_turbine, eta_s4=eta_s_hp_turbine,
    )
    LP_turbine_stg1.set_attr(eta_s1=eta_s_lp_turbine, eta_s2=eta_s_lp_turbine)
    LP_turbine_stg2.set_attr(eta_s=eta_s_lp_turbine)
    LP_turbine_stg3.set_attr(eta_s=eta_s_lp_turbine)

    # Interstage heaters. Each shell condenses to x=0 (set on c31/c33) and each cold
    # outlet temperature is fixed (c2d, c2b), so the bleed mass flows follow from the
    # two energy balances. No ttd spec belongs here: the cold outlet temperature
    # already occupies that degree of freedom. pr2=0.98 per stage lands the LP inlet
    # at 1.088 MPa, inside the DCD's 1.073-1.096 MPa band.
    interstage_heater_2.set_attr(pr1=0.97, pr2=0.98)
    interstage_heater_1.set_attr(pr1=0.97, pr2=0.98)

    # The merged reheater drains are the highest-pressure drain in the plant, so they
    # feed their own heater at the hot end of the feedwater train. The shell receives
    # (nearly) saturated liquid, so this is a drain cooler: ttd_l, not ttd_u.
    RH_FWH.set_attr(ttd_l=ttd_l_drain_cooler, pr1=0.97, pr2=0.97)

    # Every heater fed by wet steam has a shell temperature fixed by pressure alone
    # (dT/dh = 0), so a ttd equation reduces to a constraint on the single feedwater
    # enthalpy it references and no two heaters may reference the same one. Using
    # ttd_u throughout keeps each heater on its own cold outlet, and the drains are
    # pinned with x=0 on their own connections instead.
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

    # LP FWH 4 carries the whole HP FWH 1 drain, and that flow is already fixed
    # upstream. Its duty is therefore not free: x=0 on c19 closes the shell side and
    # the feedwater rise on c9 is the result. A ttd spec here would demand a duty
    # roughly twice what the drain can supply.
    LP_FWH_4.set_attr(pr1=0.97, pr2=0.97)

    # LP FWH 1/2/3 each have one free bleed flow, so x=0 on the drain plus ttd_u on
    # the feedwater outlet is exactly determined.
    LP_FWH_1.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)
    LP_FWH_2.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)
    LP_FWH_3.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)

    # Separator drain heater. This is a drain cooler, not a condensing heater: the
    # shell side receives saturated liquid, so ttd_u would tie the feedwater outlet
    # to Tsat(1.13 MPa) = 458 K and demand far more duty than 162 kg/s of drain can
    # supply. ttd_l fixes how close the drain leaves to the incoming feedwater
    # instead, and the duty follows.
    MSR_FWH.set_attr(
    ttd_l=ttd_l_drain_cooler,
    pr1=0.97,
    pr2=0.97
    )

    HP_pump.set_attr(eta_s=eta_s_feed_pump)

    # COnnection Attributes

    # Condenser cooling connections
    c1_1.set_attr(T=T_cw_in, p=p_cw, fluid=cooling_fluid)
    c1_2.set_attr(T=T_cw_out)

    # Main steam, DCD Fig 10.1-1: 808 psia / 1197.6 BTU/lb. The flow follows from the
    # two steam generator duties, so only a start value is given here.
    c1.set_attr(p=p_main_steam, h=h_main_steam, m0=1891, fluid=working_fluid)
    c1a.set_attr(m0=1824, h0=2.786e6)  # main steam -> HP turbine
    c1b.set_attr(m0=66, h0=2.786e6)  # main steam bleed -> interstage heater 2

    # HP turbine outlets: pressures fall along the stage order out1 -> ... -> out4.
    # Extraction masses are results of each heater's ttd_u. c13 sits at 2.0 MPa so
    # that Tsat = 485.5 K supports the DCD's 478 K feedwater point ahead of the
    # final heater, and c3 at 2.83 MPa (Tsat = 503.6 K) the 500.9 K SG inlet.
    c2.set_attr(p=p_hp_exhaust, m0=1388, h0=2.55e6)  # HP exhaust -> moisture separator
    c2a.set_attr(m0=1216, h0=2.782e6)  # separated vapour -> interstage heater 1
    c2d.set_attr(m0=1216, h0=2.863e6)  #Changed
    c2b.set_attr(T=T_lp_inlet, m0=1216, h0=2.950e6)  # reheated steam -> LP turbine
    c2c.set_attr(m0=172, h0=7.87e5)  # separator drain -> MSR drain FWH
    c30.set_attr(p=p_hp_bleed_1, m=82.935, h0=2.740e6)  #Changed
    c3.set_attr(p=p_hp_bleed_2, m0=92, h0=2.690e6)  # stage-2 extraction -> HP FWH 2
    c13.set_attr(p=p_hp_bleed_3, m0=284, h0=2.640e6)  # stage-3 extraction -> HP FWH merge

    # Interstage heater drains. x=0 on both shells sets the bleed flows; heater 2's
    # drain is then throttled to heater 1's shell-outlet pressure, which is what the
    # merge pins the two branches to.
    c31.set_attr(x=0, m0=66, h0=1.179e6)
    c32.set_attr(m0=66, h0=1.179e6)
    c33.set_attr(x=0, m0=60, h0=1.079e6)
    c34.set_attr(m0=126, h0=1.132e6)
    c35.set_attr(m0=126, h0=9.93e5)
    c36.set_attr(m0=126, h0=9.93e5)
    c37.set_attr(m0=218, h0=1.706e6)

    # LP bleed pressures, DCD LP extraction stages. Spreading them 0.289 / 0.086 /
    # 0.0405 MPa puts Tsat at 405 / 369 / 349 K against condensate entering at
    # 312 K, which is the ladder the DCD feedwater temperatures imply.
    c40.set_attr(p=p_lp_bleed_1, m0=104, h0=2.710e6)  # LP bleed 1 -> LP FWH 3
    c41.set_attr(p=p_lp_bleed_2, m0=1112, h0=2.535e6)  # LP stage 1 exhaust
    c42.set_attr(m0=16, h0=2.535e6)  # LP bleed 2 -> LP FWH 2
    c43.set_attr(m0=1096, h0=2.535e6)
    c44.set_attr(p=p_lp_bleed_3, m0=1096, h0=2.435e6)  # LP stage 2 exhaust
    c45.set_attr(m0=90, h0=2.435e6)  # LP bleed 3 -> LP FWH 1
    c46.set_attr(m0=1006, h0=2.435e6)

    # Condenser backpressure. The DCD's 5.66 psia is the last LP extraction, not
    # condenser vacuum; the hotwell sits at 7 kPa, which is the 118.7 F / 86.7
    # BTU/lb condensate point on the heat balance.
    c5.set_attr(p=p_condenser, m0=1006, h0=2.230e6)  # LP turbine exhaust

    c8.set_attr(p=p_condensate, m0=1891, h0=1.65e5)

    c60.set_attr(m0=1891, h0=2.988e5)
    c61.set_attr(m0=1891, h0=3.797e5)
    c62.set_attr(m0=1891, h0=5.352e5)
    c9.set_attr(m0=1891, h0=5.979e5)
    c9a.set_attr(m0=1891, h0=6.132e5)

    c10.set_attr(m0=1891, h0=6.203e5)
    c11.set_attr(m0=1891, h0=8.873e5)
    c16.set_attr(m0=1891, h0=9.706e5)
    c38.set_attr(m0=1891, h0=9.798e5)

    # Even split between the two steam generators: fixing the enthalpy leaving shell 1
    # at the main steam value forces the merge to hand shell 2 the same outlet state,
    # so the two duties are carried by equal mass flows.
    c39.set_attr(m0=945, h0=9.798e5)
    c72.set_attr(m0=945, h0=9.798e5)
    c73.set_attr(h=h_main_steam, m0=945)
    c74.set_attr(m0=945, h0=2.786e6)

    c14.set_attr(m0=502, h0=1.908e6)
    c15.set_attr(x=0, m0=502, h0=9.015e5)  # HP FWH 1 drain leaves as saturated liquid
    c17.set_attr(x=0, m0=218, h0=9.854e5)  # HP FWH 2 drain leaves as saturated liquid

    # LP FWH 4 shell pressure. Tsat(0.6 MPa) = 432 K against feedwater at 400 K, so
    # the throttled HP FWH 1 drain arrives wet (x ~ 0.11) and condenses out.
    c18.set_attr(p=p_lp_fwh_4_shell, m0=502, h0=9.015e5)
    c19.set_attr(x=0, m0=502, h0=6.652e5)
    c20.set_attr(m0=502, h0=6.652e5)

    c63.set_attr(m0=778, h0=9.293e5)
    c64.set_attr(x=0, m0=778, h0=5.516e5)
    c65.set_attr(m0=778, h0=5.516e5)

    c66.set_attr(m0=794, h0=5.891e5)
    c67.set_attr(x=0, m0=794, h0=3.965e5)
    c68.set_attr(m0=794, h0=3.965e5)

    c69.set_attr(m0=884, h0=6.023e5)
    c70.set_attr(x=0, m0=884, h0=3.158e5)
    c71.set_attr(m0=884, h0=3.158e5)

    c21.set_attr(m0=172, h0=6.194e5)
    c22.set_attr(m0=172, h0=6.194e5)

    AP1000_plant.add_conns(
    c1, c1a, c1b, c2, c2a, c2b, c2c, c2d, c3, c5,
    c6, c7, c8, c9, c9a, c10, c11, c12, c13, c14, c15,
    c16, c17, c18, c19, c20, c21, c22, c0, c1_1, c1_2,
    c30, c31, c32, c33, c34, c35, c36, c37, c38, c39,
    c40, c41, c42, c43, c44, c45, c46,
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
            HP_turbine, LP_turbine_stg1, LP_turbine_stg2, LP_turbine_stg3
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
                c73, c74, c1, c1a, c1b, c30, c3, c13, c2, c2c, c2a, c2d, c2b,
                c31, c32, c33, c34, c35, c36, c37, c40, c41, c42, c43, c44,
                c45, c46, c5, c6, c7, c8, c60, c61, c62, c9, c9a, c10, c11,
                c16, c38, c39, c72, c12, c14, c15, c17, c18, c19, c20, c63,
                c64, c65, c66, c67, c68, c69, c70, c71, c21, c22, c1_1, c1_2,
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


