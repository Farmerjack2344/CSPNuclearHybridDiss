from tespy.networks import Network
from tespy.components import (
    CycleCloser, Pump, Condenser, Turbine,
    SimpleHeatExchanger, Source, Sink,
    HeatExchanger, Merge, Splitter, Valve,
    DropletSeparator
)

from MultistageTurbine import MultiStageExtractionTurbine

from tespy.connections import Connection

import matplotlib.pyplot as plt
import numpy as np
from fluprodia import FluidPropertyDiagram

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

cooling_fluid = {"water": 1}
working_fluid = {"water": 1}

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

# Two-stage interstage reheat. Heater 2 is the low-temperature stage (fed by the
# HP turbine stage-1 bleed), heater 1 the high-temperature stage (fed by main
# steam bled upstream of the HP turbine).
interstage_heater_1 = HeatExchanger("interstage heater 1")
interstage_heater_2 = HeatExchanger("interstage heater 2")
interstage_heater_1_valve = Valve("interstage heater 1 drain valve")
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

# Four-heater LP train, cascaded shell drains. LP FWH 1 is the hottest (fed by
# the HP FWH 1 drain), LP FWH 2/3/4 are fed by the three LP bleeds. Each shell
# outlet is throttled down to the next bleed pressure and merges with that
# bleed, and the last drain lands on the condenser merge.
LP_FWH = HeatExchanger("LP FWH 1")
LP_FWH_valve = Valve("LP FWH 1 drain valve")

LP_FWH_2 = HeatExchanger("LP FWH 2")
LP_FWH_2_merge = Merge("LP FWH 2 shell merge", num_in=3)
LP_FWH_2_valve = Valve("LP FWH 2 drain valve")

LP_FWH_3 = HeatExchanger("LP FWH 3")
LP_FWH_3_merge = Merge("LP FWH 3 shell merge", num_in=2)
LP_FWH_3_valve = Valve("LP FWH 3 drain valve")

LP_FWH_4 = HeatExchanger("LP FWH 4")
LP_FWH_4_merge = Merge("LP FWH 4 shell merge", num_in=2)
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
c1b = Connection(main_steam_split, "out2", interstage_heater_1, "in1")

# MultiStageExtractionTurbine: out1 is after stage 1 (highest outlet P),
# outN is the exhaust (lowest P). Stage i+1 uses out{i}'s (p, h) as its inlet.
c2 = Connection(HP_turbine, "out4", moisture_separator, "in1")

# DropletSeparator: out1 is the saturated liquid drain, out2 the saturated vapour
# that goes on to the interstage reheaters and the LP turbine.
c2a = Connection(moisture_separator, "out2", interstage_heater_2, "in2")
c2d = Connection(interstage_heater_2, "out2", interstage_heater_1, "in2")
c2b = Connection(interstage_heater_1, "out2", LP_turbine_stg1, "in1")
c2c = Connection(moisture_separator, "out1", MSR_FWH, "in1")

# Interstage heater shell sides and their cascaded drains.
c30 = Connection(HP_turbine, "out1", interstage_heater_2, "in1")
c31 = Connection(interstage_heater_1, "out1", interstage_heater_1_valve, "in1")
c32 = Connection(interstage_heater_1_valve, "out1", interstage_drain_merge, "in1")
c33 = Connection(interstage_heater_2, "out1", interstage_drain_merge, "in2")
c34 = Connection(interstage_drain_merge, "out1", RH_FWH, "in1")
c35 = Connection(RH_FWH, "out1", RH_FWH_valve, "in1")
c36 = Connection(RH_FWH_valve, "out1", HP_FWH_2_shell_merge, "in2")

c3 = Connection(HP_turbine, "out2", HP_FWH_2_shell_merge, "in1")
c37 = Connection(HP_FWH_2_shell_merge, "out1", HP_FWH_2, "in1")

# LP expansion and the three LP bleeds.
c40 = Connection(LP_turbine_stg1, "out1", LP_FWH_2_merge, "in2")
c41 = Connection(LP_turbine_stg1, "out2", LP_bleed_split_1, "in1")
c42 = Connection(LP_bleed_split_1, "out1", LP_FWH_3_merge, "in2")
c43 = Connection(LP_bleed_split_1, "out2", LP_turbine_stg2, "in1")
c44 = Connection(LP_turbine_stg2, "out1", LP_bleed_split_2, "in1")
c45 = Connection(LP_bleed_split_2, "out1", LP_FWH_4_merge, "in2")
c46 = Connection(LP_bleed_split_2, "out2", LP_turbine_stg3, "in1")

c5 = Connection(LP_turbine_stg3, "out1", condenser_merge, "in1")

c6 = Connection(condenser_merge, "out1", condenser, "in1")

c7 = Connection(condenser, "out1", condensate_pump, "in1")

# Feedwater climbs the LP train from the coldest heater upwards.
c8 = Connection(condensate_pump, "out1", LP_FWH_4, "in2")
c60 = Connection(LP_FWH_4, "out2", LP_FWH_3, "in2")
c61 = Connection(LP_FWH_3, "out2", LP_FWH_2, "in2")
c62 = Connection(LP_FWH_2, "out2", LP_FWH, "in2")
c9 = Connection(LP_FWH, "out2", MSR_FWH, "in2")
c9a = Connection(MSR_FWH, "out2", HP_pump, "in1")

# Cascaded LP shell drains: HP FWH 1 -> LP FWH 1 -> 2 -> 3 -> 4 -> condenser.
c18 = Connection(HP_FWH_valve_1, "out1", LP_FWH, "in1")
c19 = Connection(LP_FWH, "out1", LP_FWH_valve, "in1")
c20 = Connection(LP_FWH_valve, "out1", LP_FWH_2_merge, "in1")
c63 = Connection(LP_FWH_2_merge, "out1", LP_FWH_2, "in1")
c64 = Connection(LP_FWH_2, "out1", LP_FWH_2_valve, "in1")
c65 = Connection(LP_FWH_2_valve, "out1", LP_FWH_3_merge, "in1")
c66 = Connection(LP_FWH_3_merge, "out1", LP_FWH_3, "in1")
c67 = Connection(LP_FWH_3, "out1", LP_FWH_3_valve, "in1")
c68 = Connection(LP_FWH_3_valve, "out1", LP_FWH_4_merge, "in1")
c69 = Connection(LP_FWH_4_merge, "out1", LP_FWH_4, "in1")
c70 = Connection(LP_FWH_4, "out1", LP_FWH_4_valve, "in1")
c71 = Connection(LP_FWH_4_valve, "out1", condenser_merge, "in2")

# The MSR drain leaves its cooler at ~420 K. Flashing it straight to the
# condenser threw away ~50 MW; cascading it into the top of the LP shell train
# instead lets that heat displace bleed steam.
c21 = Connection(MSR_FWH, "out1", MSR_FWH_valve, "in1")
c22 = Connection(MSR_FWH_valve, "out1", LP_FWH_2_merge, "in3")

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

condenser.set_attr(pr1=1, pr2=0.98)

# Each steam generator carries its DCD rating of 1707 MWt, so the total NSSS heat
# input is 3414 MWt and the main steam flow follows from the two duties. Only one
# of the two shells may carry a pressure spec: both outlets are pinned to the main
# steam header pressure by the merge, so a second pr equation would be redundant
# with it and leave the Jacobian singular.
steam_generator_1.set_attr(pr=0.97, Q=1707e6)
steam_generator_2.set_attr(Q=1707e6)

# Isentropic efficiencies are the DCD-consistent values that land the shaft output
# at 1200 MW: the wet LP stages run well below dry-expansion efficiency.
HP_turbine.set_attr(eta_s1=0.84, eta_s2=0.84, eta_s3=0.84, eta_s4=0.84)
LP_turbine_stg1.set_attr(eta_s1=0.873, eta_s2=0.873)
LP_turbine_stg2.set_attr(eta_s=0.873)
LP_turbine_stg3.set_attr(eta_s=0.873)

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
RH_FWH.set_attr(ttd_l=5, pr1=0.97, pr2=0.97)

# Every heater fed by wet steam has a shell temperature fixed by pressure alone
# (dT/dh = 0), so a ttd equation reduces to a constraint on the single feedwater
# enthalpy it references and no two heaters may reference the same one. Using
# ttd_u throughout keeps each heater on its own cold outlet, and the drains are
# pinned with x=0 on their own connections instead.
HP_FWH_2.set_attr(
    ttd_u=5,
    pr1=0.97,
    pr2=0.97,
)

HP_FWH_1.set_attr(
    ttd_u=5,
    pr1=0.97,
    pr2=0.97
)

condensate_pump.set_attr(eta_s=0.804)

# LP FWH 1 carries the whole HP FWH 1 drain, and that flow is already fixed
# upstream. Its duty is therefore not free: x=0 on c19 closes the shell side and
# the feedwater rise on c9 is the result. A ttd spec here would demand a duty
# roughly twice what the drain can supply.
LP_FWH.set_attr(pr1=0.97, pr2=0.97)

# LP FWH 2/3/4 each have one free bleed flow, so x=0 on the drain plus ttd_u on
# the feedwater outlet is exactly determined.
LP_FWH_2.set_attr(ttd_u=5, pr1=0.97, pr2=0.97)
LP_FWH_3.set_attr(ttd_u=5, pr1=0.97, pr2=0.97)
LP_FWH_4.set_attr(ttd_u=5, pr1=0.97, pr2=0.97)

# Separator drain heater. This is a drain cooler, not a condensing heater: the
# shell side receives saturated liquid, so ttd_u would tie the feedwater outlet
# to Tsat(1.13 MPa) = 458 K and demand far more duty than 162 kg/s of drain can
# supply. ttd_l fixes how close the drain leaves to the incoming feedwater
# instead, and the duty follows.
MSR_FWH.set_attr(
    ttd_l=5,
    pr1=0.97,
    pr2=0.97
)

HP_pump.set_attr(eta_s=0.804)

# Condenser cooling connections
c1_1.set_attr(T=288.15, p=1.2e5, fluid=cooling_fluid)
c1_2.set_attr(T=300.15)

# Main steam, DCD Fig 10.1-1: 808 psia / 1197.6 BTU/lb. The flow follows from the
# two steam generator duties, so only a start value is given here.
c1.set_attr(p=5.571e6, h=2785.6e3, m0=1891, fluid=working_fluid)
c1a.set_attr(m0=1824, h0=2.786e6)  # main steam -> HP turbine
c1b.set_attr(m0=66, h0=2.786e6)  # main steam bleed -> interstage heater 1

# HP turbine outlets: pressures fall along the stage order out1 -> ... -> out4.
# Extraction masses are results of each heater's ttd_u. c13 sits at 2.0 MPa so
# that Tsat = 485.5 K supports the DCD's 478 K feedwater point ahead of the
# final heater, and c3 at 2.83 MPa (Tsat = 503.6 K) the 500.9 K SG inlet.
c2.set_attr(p=1.133e6, m0=1388, h0=2.55e6)  # HP exhaust -> moisture separator
c2a.set_attr(m0=1216, h0=2.782e6)  # separated vapour -> interstage heater 2
c2d.set_attr(T=490, m0=1216, h0=2.863e6)  # first reheat stage outlet
c2b.set_attr(T=527.7, m0=1216, h0=2.950e6)  # reheated steam -> LP turbine
c2c.set_attr(m0=172, h0=7.87e5)  # separator drain -> MSR drain FWH
c30.set_attr(p=4.0e6, m0=60, h0=2.740e6)  # stage-1 bleed -> interstage heater 2
c3.set_attr(p=2.83e6, m0=92, h0=2.690e6)  # stage-2 extraction -> HP FWH 2
c13.set_attr(p=2.0e6, m0=284, h0=2.640e6)  # stage-3 extraction -> HP FWH merge

# Interstage heater drains. x=0 on both shells sets the bleed flows; heater 1's
# drain is then throttled to heater 2's shell-outlet pressure, which is what the
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
c40.set_attr(p=0.289e6, m0=104, h0=2.710e6)  # LP bleed 1 -> LP FWH 2
c41.set_attr(p=0.086e6, m0=1112, h0=2.535e6)  # LP stage 1 exhaust
c42.set_attr(m0=16, h0=2.535e6)  # LP bleed 2 -> LP FWH 3
c43.set_attr(m0=1096, h0=2.535e6)
c44.set_attr(p=0.0405e6, m0=1096, h0=2.435e6)  # LP stage 2 exhaust
c45.set_attr(m0=90, h0=2.435e6)  # LP bleed 3 -> LP FWH 4
c46.set_attr(m0=1006, h0=2.435e6)

# Condenser backpressure. The DCD's 5.66 psia is the last LP extraction, not
# condenser vacuum; the hotwell sits at 7 kPa, which is the 118.7 F / 86.7
# BTU/lb condensate point on the heat balance.
c5.set_attr(p=7000, m0=1006, h0=2.230e6)  # LP turbine exhaust

c8.set_attr(p=1.2e6, m0=1891, h0=1.65e5)

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
c73.set_attr(h=2785.6e3, m0=945)
c74.set_attr(m0=945, h0=2.786e6)

c14.set_attr(m0=502, h0=1.908e6)
c15.set_attr(x=0, m0=502, h0=9.015e5)  # HP FWH 1 drain leaves as saturated liquid
c17.set_attr(x=0, m0=218, h0=9.854e5)  # HP FWH 2 drain leaves as saturated liquid

# LP FWH 1 shell pressure. Tsat(0.6 MPa) = 432 K against feedwater at 400 K, so
# the throttled HP FWH 1 drain arrives wet (x ~ 0.11) and condenses out.
c18.set_attr(p=0.60e6, m0=502, h0=9.015e5)
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

try:
    AP1000_plant.solve(
        mode="design",
        block_solve=True,
        robust_relax=True,
        oscillation_damping=True,
        max_iter=700,
    )

    print(f"Converged: {AP1000_plant.status == 0} (status={AP1000_plant.status})")

    if AP1000_plant.status != 0:
        AP1000_plant.print_structural_analysis()
        AP1000_plant.print_variables()
        AP1000_plant.print_incidence_matrix()
        AP1000_plant.print_equations_with_dependents()
    else:
        AP1000_plant.print_results()

        turbine_power = sum(
            t.P.val_SI for t in (
                HP_turbine, LP_turbine_stg1, LP_turbine_stg2, LP_turbine_stg3
            )
        )
        pump_power = condensate_pump.P.val_SI + HP_pump.P.val_SI
        net_power = -(turbine_power + pump_power)
        heat_input = (
            steam_generator_1.Q.val_SI + steam_generator_2.Q.val_SI
        )
        print(f"main steam flow      : {c1.m.val_SI:.1f} kg/s")
        print(f"SG 1 duty            : {steam_generator_1.Q.val_SI / 1e6:.1f} MW")
        print(f"SG 2 duty            : {steam_generator_2.Q.val_SI / 1e6:.1f} MW")
        print(f"total heat input     : {heat_input / 1e6:.1f} MW")
        print(f"gross turbine power  : {-turbine_power / 1e6:.1f} MW")
        print(f"pump power           : {pump_power / 1e6:.1f} MW")
        print(f"net power            : {net_power / 1e6:.1f} MW")
        print(f"cycle efficiency     : {100 * net_power / heat_input:.2f} %")

        # Initial Setup
        diagram = FluidPropertyDiagram('water')
        diagram.set_unit_system(units=AP1000_plant.units)

        # Storing the model result in the dictionary
        result_dict = {}
        result_dict.update(
            {cp.label: cp.get_plotting_data()[1] for cp in AP1000_plant.comps['object']
             if cp.get_plotting_data() is not None})

        # Iterate over the results obtained from TESPy simulation
        for key, data in result_dict.items():
            # Calculate individual isolines for T-s diagram
            result_dict[key]['datapoints'] = diagram.calc_individual_isoline(**data)

        # Create a figure and axis for plotting T-s diagram
        fig, ax = plt.subplots(1, figsize=(20, 10))
        isolines = {
            'Q': np.linspace(0, 1, 2),
            'p': np.array([1, 2, 5, 10, 20, 50, 100, 300]),
            'vol': np.array([]),
            'h': np.arange(500, 3501, 500)
        }

        # Set isolines for T-s diagram
        diagram.set_isolines(**isolines)
        diagram.calc_isolines()

        # Draw isolines on the T-s diagram
        diagram.draw_isolines(fig, ax, 'Ts', x_min=0, x_max=7500, y_min=0, y_max=650)

        # Adjust the font size of the isoline labels
        for text in ax.texts:
            text.set_fontsize(10)

        # Plot T-s curves for each component
        for key in result_dict.keys():
            datapoints = result_dict[key]['datapoints']
            _ = ax.plot(datapoints['s'], datapoints['T'], color='#ff0000', linewidth=2)
            _ = ax.scatter(datapoints['s'][0], datapoints['T'][0], color='#ff0000')

        # Set labels and title for the T-s diagram
        ax.set_xlabel('Entropy, s in J/kgK', fontsize=16)
        ax.set_ylabel('Temperature, T in °C', fontsize=16)
        ax.set_title('T-s Diagram of Rankine Cycle', fontsize=20)

        # Set font size for the x-axis and y-axis ticks
        ax.tick_params(axis='x', labelsize=12)
        ax.tick_params(axis='y', labelsize=12)
        plt.tight_layout()

        # Save the T-s diagram plot as an SVG file
        fig.savefig('AP1000_ts_diagram.svg')


except Exception as e:
    print(f"Error: {e}")
    AP1000_plant.print_variables()
    AP1000_plant.print_structural_analysis()
    AP1000_plant.print_incidence_matrix()


