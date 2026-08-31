from tespy.networks import Network
from tespy.components import (
    CycleCloser, Pump, Condenser, Turbine,
    SimpleHeatExchanger, Source, Sink,
    HeatExchanger, Merge, Splitter, Valve,
    DropletSeparator
)

from MultistageTurbine import MultiStageExtractionTurbine

from tespy.connections import Connection

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
steam_generator = SimpleHeatExchanger("steam generator")
condenser = Condenser("main condenser")
condenser_merge = Merge("condenser merge", num_in=3)
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

LP_turbine_stg1 = Turbine("LP turbine stage 1")
# LP_turbine_stg2 = MultiStageExtractionTurbine("LP turbine stage 2", num_stages=1)
condensate_pump = Pump("condenser pump")

LP_FWH = HeatExchanger("LP FWH 1")
LP_FWH_2 = HeatExchanger("LP FWH 2")
LP_FWH_2_valve = Valve("LP FWH 2 drain valve")
# Drops the LP FWH shell drain from the shell pressure down to the condenser.
# Without this valve the shell outlet sits directly on the condenser merge, which
# pins the shell to condenser pressure and leaves the heater no temperature head.
LP_FWH_valve = Valve("LP FWH drain valve")

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
c2c = Connection(moisture_separator, "out1", LP_FWH_2, "in1")

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

c5 = Connection(LP_turbine_stg1, "out1", condenser_merge, "in1")

c6 = Connection(condenser_merge, "out1", condenser, "in1")

c7 = Connection(condenser, "out1", condensate_pump, "in1")

c8 = Connection(condensate_pump, "out1", LP_FWH, "in2")

c9 = Connection(LP_FWH, "out2", LP_FWH_2, "in2")
c9a = Connection(LP_FWH_2, "out2", HP_pump, "in1")

c21 = Connection(LP_FWH_2, "out1", LP_FWH_2_valve, "in1")
c22 = Connection(LP_FWH_2_valve, "out1", condenser_merge, "in3")

c10 = Connection(HP_pump, "out1", HP_FWH_1, "in2")


c11 = Connection(HP_FWH_1, "out2", HP_FWH_2, "in2")

c12 = Connection(HP_FWH_valve_2, "out1", HP_FWH_M, "in1")
c13 = Connection(HP_turbine, "out3", HP_FWH_M, "in2")

c14 = Connection(HP_FWH_M, "out1", HP_FWH_1, "in1")
c15 = Connection(HP_FWH_1, "out1", HP_FWH_valve_1, "in1")

c16 = Connection(HP_FWH_2, "out2", RH_FWH, "in2")
c38 = Connection(RH_FWH, "out2", steam_generator, "in1")

c17 = Connection(HP_FWH_2, "out1", HP_FWH_valve_2, "in1")

c18 = Connection(HP_FWH_valve_1, "out1", LP_FWH, "in1")
c19 = Connection(LP_FWH, "out1", LP_FWH_valve, "in1")
c20 = Connection(LP_FWH_valve, "out1", condenser_merge, "in2")

c0 = Connection(steam_generator, "out1", cc, "in1")

# Condenser cooling connections
c1_1 = Connection(cwso, "out1", condenser, "in2", label="11")
c1_2 = Connection(condenser, "out2", cwsi, "in1", label="12")

condenser.set_attr(pr1=1, pr2=0.98)

# 1707 MW is ONE of the AP1000's two steam generators, but the main steam flow
# below is the whole plant, so the two must not be paired. With the main steam
# state fixed by the cycle closer, Q and m together dictate the feedwater
# enthalpy entering the SG (h_c16 = h_c1 - Q/m); pairing 1707 MW with the full
# flow demanded a feedwater state no feedwater train can deliver.
steam_generator.set_attr(
    Q=3400e6,
    pr=0.97
)

HP_turbine.set_attr(eta_s1=0.845, eta_s2=0.845, eta_s3=0.845, eta_s4=0.845)
LP_turbine_stg1.set_attr(eta_s=0.845)

# Interstage heaters. Each shell condenses to x=0 (set on c31/c33) and each cold
# outlet temperature is fixed (c2d, c2b), so the bleed mass flows follow from the
# two energy balances. No ttd spec belongs here: the cold outlet temperature
# already occupies that degree of freedom.
interstage_heater_2.set_attr(pr1=0.97, pr2=0.98)
interstage_heater_1.set_attr(pr1=0.97, pr2=0.98)

# The merged reheater drains are the highest-pressure drain in the plant, so they
# feed their own heater at the hot end of the feedwater train. The shell receives
# (nearly) saturated liquid, so this is a drain cooler: ttd_l, not ttd_u.
RH_FWH.set_attr(ttd_l=5, pr1=0.97, pr2=0.97)

# Every heater here is fed by wet steam, so the shell temperature is fixed by
# pressure alone (dT/dh = 0). A ttd equation therefore reduces to a constraint on
# the single feedwater enthalpy it references, so no two heaters may reference the
# same one: ttd_u on HP FWH 1 (which fixes h_c11) together with ttd_l on HP FWH 2
# (whose cold inlet is also c11) gives two identical Jacobian rows. Using ttd_u
# throughout keeps each heater on its own cold outlet, and the drains are pinned
# with x=0 on c15/c17 instead.
HP_FWH_2.set_attr(
    ttd_u=5,
    pr1=0.97,
    pr2=0.97,
)

HP_FWH_1.set_attr(
    # Q=-147.91e6,
    ttd_u=5,
    pr1=0.97,
    pr2=0.97
)

condensate_pump.set_attr(eta_s=0.804)

LP_FWH.set_attr(
    # Q=-136.06e6,
    ttd_u=5,
    pr1=0.97,
    pr2=0.97
)
# The drain is still wet leaving the shell, so no x= spec belongs on c19 -- the
# energy balance sets its quality.

# Separator drain heater. This is a drain cooler, not a condensing heater: the
# shell side receives saturated liquid, so ttd_u would tie the feedwater outlet to
# Tsat(1.13 MPa) = 459 K and demand ~900 MW from a drain flow that can supply
# under 100 MW. ttd_l fixes how close the drain leaves to the incoming condensate
# instead, and the duty (hence the feedwater rise on c9a) follows.
LP_FWH_2.set_attr(
    ttd_l=5,
    pr1=0.97,
    pr2=0.97
)

HP_pump.set_attr(eta_s=0.804)

# Condenser cooling connections
c1_1.set_attr(T=288.15, p=1.2e5, fluid=cooling_fluid)
c1_2.set_attr(T=300.15)

# Saturated main steam, matching AP1000V4 (DCD Fig 10.1-1, 1197.6 BTU/lb).
# T=600 K at 150e5 Pa was SUBCOOLED LIQUID: Tsat(15 MPa) = 615.3 K, so CoolProp
# resolved it to h = 1.4977 MJ/kg on the liquid branch and the HP turbine was
# expanding water. Steam flow is now a result of reactor power, not an input.
c1.set_attr(p=5.57e6, h=2785618, m0=1875, fluid=working_fluid)
c1a.set_attr(m0=1825, h0=2.786e6)  # main steam -> HP turbine
c1b.set_attr(m0=50, h0=2.786e6)  # main steam bleed -> interstage heater 1

# HP turbine outlets: pressures fall along the stage order out1 -> ... -> out4.
# Extraction masses are results of each heater's ttd_u.
# c13 has to sit at 2.40e6, not 1.79e6: HP FWH 2 can only add ~9 K, so HP FWH 1
# must deliver feedwater at ~490 K, and its shell needs Tsat above that
# (Tsat(2.40e6) = 495.0 K). The stages stack tightly only because two HP heaters
# are spanning a 146 K rise; adding the deaerator and the other stages from V4
# will spread this out again.
c2.set_attr(p=113e4)  # HP exhaust -> moisture separator
c2a.set_attr(m0=900, h0=2.78e6)  # separated vapour -> interstage heater 2
c2d.set_attr(T=490, m0=900, h0=2.85e6)  # first reheat stage outlet
c2b.set_attr(T=520, m0=900, h0=2.92e6)  # reheated steam -> LP turbine
c2c.set_attr(m0=140, h0=8.0e5)  # separator drain -> LP FWH 2
c30.set_attr(p=4.0e6, m0=50, h0=2.74e6)  # stage-1 bleed -> interstage heater 2
c3.set_attr(p=2.83e6, m0=45, h0=2.68e6)  # stage-2 extraction -> HP FWH 2
c13.set_attr(p=2.40e6, m0=690, h0=2.65e6)  # stage-3 extraction -> HP FWH merge

# Interstage heater drains. x=0 on both shells sets the bleed flows; heater 1's
# drain is then throttled to heater 2's shell-outlet pressure, which is what the
# merge pins the two branches to.
c31.set_attr(x=0, m0=50, h0=1.131e6)
c32.set_attr(m0=50, h0=1.131e6)
c33.set_attr(x=0, m0=50, h0=1.085e6)
c34.set_attr(m0=100, h0=1.10e6)
c35.set_attr(m0=100, h0=1.017e6)
c36.set_attr(m0=100, h0=1.017e6)
c37.set_attr(m0=145, h0=1.55e6)

c8.set_attr(p=1.0e6)

c9.set_attr(
    m0=1875,
    h0=2.93e5
)

c9a.set_attr(
    m0=1875,
    h0=3.3e5
)

# The separator already pins the shell inlet at x=0, so the drain mass flow is
# not free: an x= spec on c21 on top of ttd_l would over-determine the heater.
c21.set_attr(m0=140, h0=3.2e5)
c22.set_attr(m0=140, h0=3.2e5)

c10.set_attr(
    m0=1875,
    h0=2.99e5
)

c11.set_attr(
    m0=1875,
    h0=9.26e5
)

c16.set_attr(m0=1875, h0=9.79e5)
c38.set_attr(m0=1875, h0=9.85e5)

# Condenser backpressure. 40500 Pa is the DCD's last LP extraction pressure
# (5.66 psia), not condenser vacuum; at 40.5 kPa the condensate leaves at 349 K,
# which is what left the LP FWH no temperature head to work with.
c5.set_attr(p=7000, m0=900, h0=2.15e6)  # LP turbine outlet

c14.set_attr(m0=835, h0=2.40e6)
c15.set_attr(x=0, m0=835, h0=9.62e5)  # HP FWH 1 drain leaves as saturated liquid
c17.set_attr(x=0, m0=145, h0=1.002e6)  # HP FWH 2 drain leaves as saturated liquid

# LP FWH shell pressure. Tsat(0.39e5) = 348.4 K against condensate at 312 K gives
# ~36 K of head; the drain arrives wet (x ~ 0.27) and leaves wetter (x ~ 0.17).
c18.set_attr(p=0.39e5, m0=835, h0=9.62e5)
c19.set_attr(m0=835, h0=7.1e5)
c20.set_attr(m0=835, h0=7.1e5)

AP1000_plant.add_conns(
    c1, c1a, c1b, c2, c2a, c2b, c2c, c2d, c3, c5,
    c6, c7, c8, c9, c9a, c10, c11, c12, c13, c14, c15,
    c16, c17, c18, c19, c20, c21, c22, c0, c1_1, c1_2,
    c30, c31, c32, c33, c34, c35, c36, c37, c38
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

except Exception as e:
    print(f"Error: {e}")
    AP1000_plant.print_variables()
    AP1000_plant.print_structural_analysis()
    AP1000_plant.print_incidence_matrix()
