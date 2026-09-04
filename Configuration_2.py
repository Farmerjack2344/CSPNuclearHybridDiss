import pandas as pd
import math
import numpy as np
from colorama import Fore, Style, init
init(autoreset=True)

from MoltenSaltTank import MoltenSaltTank, dispatch
from MoltenSalt import MoltenSalt
from tespy.networks import Network
from tespy.components import (
    CycleCloser, Pump, Condenser, Turbine,
    SimpleHeatExchanger, Source, Sink,
    HeatExchanger, Merge, Splitter, Valve,
    DropletSeparator, ParabolicTrough
)

from MultistageTurbine import MultiStageExtractionTurbine

from tespy.connections import Connection

rankine_cycle_fluid = {"water": 1}
cooling_fluid = {"water": 1}
oil_fluid = {"INCOMP::TVP1": 1}
# Bottoming cycle working fluid. R245fa is the standard modelling choice for a
# heat source near 100 C: it condenses above atmospheric pressure at ambient
# cooling water temperature, so the ORC condenser does not run under vacuum, and
# it is a dry fluid, so the expansion never enters the wet region.
orc_fluid = {"R245fa": 1}


def highlight(text):
    return Fore.GREEN + Style.BRIGHT + text + Style.RESET_ALL


def state(number, text, mark=False):
    """Label a connection with its position along the flow path.

    TESPy indexes its results table by connection label and sorts that index, so
    the zero padded number is what makes the printout come out in order of
    occurrence. The number has to sit outside the colour codes: an escape
    sequence at the front of a label sorts ahead of every digit, which would
    otherwise pull every highlighted connection to the top of the table.
    """
    return f"{number:02d} {highlight(text) if mark else text}"


def trim_results(*networks):
    """Keep the valves and the drain plumbing out of the results printout.

    Every connection worth reading was given a number by :func:`state`. What is
    left over is the valve inlets and the shell drains entering the cascade
    merges, whose states are already visible on the component either side.
    """
    for network in networks:
        for conn in network.conns["object"]:
            if not conn.label[0].isdigit():
                conn.set_attr(printout=False)
        for comp in network.comps["object"]:
            if isinstance(comp, Valve):
                comp.set_attr(printout=False)


def banner(title, colour):
    """Frame a section title so the results tables are easy to tell apart."""
    rule = "#" * 91
    return f"{Style.BRIGHT}{colour}\n\n\n\n{rule}\n#{title.center(89)}#\n{rule}"


def print_results_split(network, groups):
    """Print one results table per group of components and connections.

    TESPy prints a network as one table, and the nuclear cycle and the organic
    bottoming cycle share a network here because they share the condenser.
    Printing each group with everything else switched out therefore separates
    them on screen without having to split the network itself.

    Whatever :func:`trim_results` already hid stays hidden - a group member that
    was switched off is not switched back on - and the original printout flags
    are restored on the way out.

    :param groups: sequence of (header, components, connections)
    """
    conn_printout = {c: c.printout for c in network.conns["object"]}
    comp_printout = {c: c.printout for c in network.comps["object"]}
    try:
        for header, comps, conns in groups:
            for conn, printout in conn_printout.items():
                conn.set_attr(printout=printout and conn in conns)
            for comp, printout in comp_printout.items():
                comp.set_attr(printout=printout and comp in comps)
            print(header)
            network.print_results()
    finally:
        for conn, printout in conn_printout.items():
            conn.set_attr(printout=printout)
        for comp, printout in comp_printout.items():
            comp.set_attr(printout=printout)


# ---------------------------------------------------------------------------
# Solar field helper functions: to calculate thermal loss
# ---------------------------------------------------------------------------
def cos_theta(day_of_year, solar_hour, solar_elevation_deg):
    """Incidence angle factor for a north-south axis, east-west tracking trough.

    Duffie & Beckman eq. 1.7.2a. The zenith term is taken straight from the
    measured solar elevation in the weather file rather than recomputed from
    latitude, so it stays consistent with the DNI it is applied to.
    """
    delta = np.radians(23.45 * np.sin(np.radians(360 * (284 + day_of_year) / 365)))
    omega = np.radians(15 * (solar_hour - 12))
    cos_zenith = np.sin(np.radians(solar_elevation_deg))
    return np.sqrt(max(cos_zenith ** 2 + np.cos(delta) ** 2 * np.sin(omega) ** 2, 0))


def iam(theta_deg):
    return np.cos(np.radians(theta_deg)) + 0.000884 * theta_deg - 0.00005369 * theta_deg ** 2


def end_loss(theta_deg, f=1.71, L=148.5):
    return 1 - (f * math.tan(math.radians(theta_deg))) / L


def q_thermal_loss(T_htf, T_amb, receiver_length_total=(148.5 * 624), a0=0, a1=0.687, a2=0.001):
    dT = T_htf - T_amb
    q_per_metre = a0 + a1 * dT + a2 * dT ** 2  # W/m
    return q_per_metre * receiver_length_total  # W, total field


def meteorolgoical_values():
    """
    Gets the DNI and stuff from the csv file
    :return:
    """
    df = pd.read_csv("Timeseries_37.320.csv", skiprows=8)
    df["datetime"] = pd.to_datetime(df["time"], format="%Y%m%d:%H%M", errors="coerce")
    df = df.dropna(subset=["datetime"]).copy()

    for col in ["Gb(i)", "H_sun", "T2m"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["hour"] = df["datetime"].dt.hour
    df["day_of_year"] = df["datetime"].dt.dayofyear

    sun_height_rad = np.radians(df["H_sun"])
    with np.errstate(divide="ignore", invalid="ignore"):
        df["DNI"] = np.where(df["H_sun"] > 0, df["Gb(i)"] / np.sin(sun_height_rad), 0.0)

    df["T_amb"] = df["T2m"]
    return list(
        df[["hour", "day_of_year", "DNI", "T_amb", "H_sun"]]
        .itertuples(index=False, name=None)
    )


def Q_solar_field(hour_num, DNI, T_amb_K, collector_area, optical_efficiency,
                   T_htf_in, mdot_htf, htf, day_of_year, solar_elevation_deg):
    """
        Calculates the heat transferred tot eh thermal oil in the collector

    :param hour_num: Hour after midnight
    :param DNI: Direct Normal Irraidiance
    :param T_amb_K: AMbient temperature in Kelvin
    :param collector_area: Area of the colelctor
    :param optical_efficiency:
    :param T_htf_in:
    :param mdot_htf:
    :param htf:
    :param day_of_year:
    :param solar_elevation_deg: Solar altitude angle from the weather file
    :return:The heat collected form the Sun
    """
    Q_ideal = collector_area * DNI * optical_efficiency
    Q_real = Q_ideal
    cos = cos_theta(day_of_year, hour_num, solar_elevation_deg)

    if cos <= 0 or DNI <= 0:
        return 0.0

    theta_deg = math.degrees(math.acos(min(cos, 1.0)))

    for i in range(2):
        delta_T = Q_real / (mdot_htf * htf.cp(T_htf_in)) if Q_real > 0 else 0.0
        T_htf_out = T_htf_in + delta_T
        Q_loss = q_thermal_loss(T_htf=T_htf_out, T_amb=T_amb_K)
        Q_real = (Q_ideal * cos * iam(theta_deg) * end_loss(theta_deg)) - Q_loss

    return max(Q_real, 0.0)


def set_duty_branch(m_conn, T_conn, component, Q, T_out):
    """Drive a branch from its duty, or park it at a trickle flow when idle.

    An active branch gets Q and its outlet temperature, leaving the mass flow to
    be solved. An idle branch would otherwise need m = 0, which the solver
    cannot handle, so it gets a small fixed flow and no duty instead. Duties
    below Q_MIN_BRANCH are dropped for the same reason: they would ask for a
    mass flow small enough to upset the solver, for negligible energy.
    """
    if abs(Q) > Q_MIN_BRANCH:
        component.set_attr(Q=Q)
        m_conn.set_attr(m=None)
        T_conn.set_attr(T=T_out)
    else:
        component.set_attr(Q=0)
        T_conn.set_attr(T=None)
        m_conn.set_attr(m=M_MIN)


def solve_oil_loop(Q_field, Q_to_storage, Q_from_storage, oil_conns,
                   solar_field, T_field_out, T_charge_out, T_discharge_out,
                   charge_hx_oil=None, discharge_hx_oil=None, OilLoop=None,
                   oil_sg=None):
    """Solve the HTF loop for one timestep and return the duty it hands over.

    :param T_field_out: field outlet temperature, K
    :param T_charge_out: oil temperature returned from the charge HX, K
    :param T_discharge_out: oil temperature leaving the discharge HX, K
    """
    o3 = oil_conns[0]
    o4 = oil_conns[1]
    o6 = oil_conns[2]
    o7 = oil_conns[3]
    o8 = oil_conns[4]
    o9 = oil_conns[5]
    set_duty_branch(o3, o4, solar_field, Q_field, T_field_out)
    set_duty_branch(o6, o7, charge_hx_oil, -Q_to_storage, T_charge_out)
    set_duty_branch(o8, o9, discharge_hx_oil, Q_from_storage, T_discharge_out)
    OilLoop.solve("design")
    return max(-oil_sg.Q.val, 0.0)


def solve_power_block(Q_to_steam, heat_in_component, reheater, Steam_network,
                      turbine_list, pump_list, reheat_fraction=0.2,
                      pr_heat_in=1.0, pr_reheater=1.0):
    """Solve the coupled nuclear + ORC network against the duty the HTF gave up.

    Returns gross turbine output and the pumping parasitics, both W.

    Both solar exchangers are valved out of the vapour path (pr = 1) whenever the
    field has nothing to hand over. Leaving a pressure drop on an exchanger that
    transfers no heat is a pure throttling loss, i.e. the plant would come out
    worse at night than it would with no solar equipment fitted at all.

    :param reheat_fraction: fraction of the solar duty sent to the reheater
    :param pr_heat_in: superheater pressure ratio while it is in service
    :param pr_reheater: reheater pressure ratio while it is in service
    """
    in_service = Q_to_steam > 0
    heat_in_component.set_attr(Q=Q_to_steam * (1 - reheat_fraction),
                               pr=pr_heat_in if in_service else 1.0)
    reheater.set_attr(Q=Q_to_steam * reheat_fraction,
                      pr=pr_reheater if in_service else 1.0)
    Steam_network.solve("design")
    P_turbine = -1 * (sum([i.P.val for i in turbine_list]))
    P_pumps = (sum([i.P.val for i in pump_list]))
    return P_turbine, P_pumps


# ---------------------------------------------------------------------------
# Molten salt storage
# ---------------------------------------------------------------------------
htf = MoltenSalt()


T_cold_salt = 565.15   # K
T_hot_salt = 659.15    # K
total_salt_mass = 28_500e3  # kg
salt_cp_avg = htf.cp((T_hot_salt + T_cold_salt) / 2 - 273.15)  # Zavoico wants degC

tank = MoltenSaltTank(
    cp_avg=salt_cp_avg,
    T_cold=T_cold_salt,
    T_hot=T_hot_salt,
    total_salt_mass=total_salt_mass,
    initial_hot_mass=0.0,  # cold start; set >0 to warm-start SoC
)

# ---------------------------------------------------------------------------
# Field parameters
#
# Reference plant is Andasol-1 as modelled by Asfand et al. (2020),
# "Thermodynamic Performance and Water Consumption of Hybrid Cooling System
# Configurations for Concentrated Solar Power Plants", Sustainability 12, 4739.
# Their Table 1/Table 4 design point: HTF 618.1 kg/s delivered to the power
# block at 393 C, boiler duty 118.958 MW, reheater duty 21.479 MW (a 90/10
# split), live steam 60.935 kg/s at 381 C and 105 bar, condenser duty
# 83.597 MW, gross output 55 MWe, net output 50 MWe.
# ---------------------------------------------------------------------------

# Power block design THERMAL input, i.e. boiler + reheater duty. Note this is
# the heat the block swallows, not its 50 MWe electrical rating.
Q_design_thermal = 118.958e6 + 21.479e6
collector_area = 510_120      # m^2, Andasol-1 aperture
optical_efficiency = 0.75
T_htf_in = 273.15 + 293        # K, HTF returned to the field from the SG
mdot_htf = 618.1              # kg/s, design HTF flow (paper Table 1)

DNI_values = meteorolgoical_values()
dt = 3600  # s, hourly PVGIS data

# ---------------------------------------------------------------------------
# NETWORK 1 -- Oil loop (Therminol VP-1)
#
# Cold header -> circulation pump -> split between the solar field and the
# discharge HX; the two hot streams merge again ahead of the steam generator.
# Charging is bled off the hot header and returned cold. This is the ONLY
# network the molten salt tank interacts with (indirectly, via Q= on the
# charge/discharge HXs).
#
#   closer -> pump -> cold split -+-> field ------+-> hot merge -> SG -+-> cold merge -> closer
#                                 |               |                    |
#                                 |               +-> charge HX -------+
#                                 +-> discharge HX -> hot merge
#
# Specification strategy: the cold header temperature is fixed and every
# duty-carrying branch is given its duty plus its outlet temperature, so the
# solver returns the mass flow each branch needs. The steam generator duty is
# left free - it is whatever is required to bring the mixed oil back to the
# cold header temperature, i.e. it closes the loop energy balance. Fixing the
# SG duty as well would over-determine the network.
# ---------------------------------------------------------------------------
T_oil_cold = T_htf_in            # cold header / field inlet, K
T_oil_hot = 273.15 + 393         # field outlet, K (Therminol VP-1 upper limit)
T_oil_from_storage = T_hot_salt - 5.0  # oil leaving the discharge HX, K
M_MIN = 1.0                      # kg/s trickle flow kept in idle branches
Q_MIN_BRANCH = 1e5               # W below which a branch counts as idle


def solve_configuration2(
        # --- HTF loop operating states ---
        T_field_out=T_oil_hot,               # K, oil leaving the solar field
        T_cold_header=T_oil_cold,            # K, oil returned to the field / SG outlet
        T_discharge_out=T_oil_from_storage,  # K, oil leaving the discharge HX
        p_cold_header=28e5,                  # Pa, HTF pump discharge pressure
        eta_s_htf_pump=0.8,
        pr_solar_field=0.65,
        pr_oil_sg=0.95,
        # --- Nuclear (topping) cycle heat input ---
        steam_generator_duty=1707e6,         # W per steam generator (two fitted)
        pr_steam_generator=0.97,
        # --- Nuclear live steam state ---
        p_main_steam=5.571e6,                # Pa
        h_main_steam=2785.6e3,               # J/kg
        # --- Nuclear HP turbine extraction / exhaust pressures ---
        p_hp_bleed_1=4.0e6,                  # Pa, stage-1 bleed -> reheat stage 2 shell
        p_hp_bleed_2=2.83e6,                 # Pa, stage-2 bleed -> HP FWH 2 shell
        p_hp_bleed_3=2.0e6,                  # Pa, stage-3 bleed -> HP FWH 1 shell
        p_hp_exhaust=1.133e6,                # Pa, crossover / moisture separator
        # --- Nuclear interstage reheat outlet temperatures ---
        T_reheat_stage_1=490.0,              # K, after the first reheat stage
        T_lp_inlet=527.7,                    # K, reheated steam into the LP turbine
        # --- Nuclear LP turbine extraction / exhaust pressures ---
        p_lp_bleed_1=0.45e6,                 # Pa, LP bleed 1 -> LP FWH 2
        p_lp_bleed_2=0.30e6,                 # Pa, LP bleed 2 -> LP FWH 3
        p_lp_bleed_3=0.20e6,                 # Pa, LP bleed 3 -> LP FWH 4
        p_nuclear_condenser=1.0e5,           # Pa, topping-cycle backpressure
        # --- Nuclear feedwater train ---
        p_condensate=1.2e6,                  # Pa, condensate pump discharge
        p_lp_fwh_1_shell=0.60e6,             # Pa, top LP heater shell pressure
        ttd_u_fwh=5.0,                       # K, ttd of the condensing heaters
        ttd_l_drain_cooler=5.0,              # K, ttd of the drain coolers
        # --- Nuclear turbomachinery efficiencies ---
        eta_s_hp_turbine=0.84,
        eta_s_lp_turbine=0.873,
        eta_s_condensate_pump=0.804,
        eta_s_feed_pump=0.804,
        # --- Topping/bottoming link: the nuclear condenser is the ORC boiler ---
        pr_nuclear_condenser_orc=0.98,       # ORC-side pressure ratio
        # --- Secondary (organic Rankine) cycle ---
        secondary_fluid=orc_fluid,
        p_evaporator_secondary=10.0e5,       # Pa, ORC evaporation pressure
        p_hp_exhaust_secondary=4.5e5,        # Pa, ORC HP exhaust / reheat pressure
        p_condenser_secondary=1.9e5,         # Pa, ORC backpressure
        pr_orc_superheater=0.97,
        pr_orc_reheater=0.97,
        reheat_fraction=21.479 / (118.958 + 21.479),  # solar duty sent to the reheater
        eta_s_hp_turbine_secondary=0.85,
        eta_s_lp_turbine_secondary=0.85,
        eta_s_feed_pump_secondary=0.80,
        # --- ORC condenser cooling water ---
        T_cw_in=288.15,                      # K
        T_cw_out=300.15,                     # K
        p_cw=1.2e5,                          # Pa
        # --- Simulation window / output ---
        day_number=8,
        verbose=True,
        results_csv="ModelResults/configuration_2_hourly.csv",
        design_point_out=None,
        hourly=True,
):
    """Solve configuration 2: nuclear rejection heat boiling an organic bottoming cycle.

    :param design_point_out: dict to receive the networks, left at the design
        point rather than at the last hour of the run. This is what ts_diagram
        plots, since a cycle diagram of the small hours would show the plant
        with its solar equipment valved out.
    :param hourly: if False, stop after the design-point solve. The T-s
        diagram script uses that so it does not have to run a weather day.

    The two cycles are stacked rather than mixed. No solar heat touches the
    nuclear steam at all - that is configuration 1 - and the nuclear cycle has no
    cooling water of its own. Its LP turbine exhausts at a raised backpressure
    into a condenser whose cold side IS the bottoming cycle: the organic fluid
    preheats and boils on the nuclear rejection heat, and only the organic cycle
    talks to the heat sink.

        nuclear:  SG -> HP turbine -> MSR/reheat -> LP turbines -> condenser -+
                   ^                                                          |
                   +----------------- feedwater train <----------------------+

        organic:  ORC feed pump -> [nuclear condenser, cold side] -> solar
                  superheater -> ORC HP turbine -> solar reheater -> ORC LP
                  turbine -> ORC condenser (cooling water) -> ORC feed pump

    The solar field therefore lands on the top end of the ORC only. That is the
    whole point of the configuration and also its weakness: it buys the ORC a
    modest amount of superheat with 393 C oil, while the nuclear cycle pays for
    the arrangement by running its LP turbine against ~1 bar instead of the
    7 kPa vacuum it was designed for.

    Every argument is an operating condition that moves the cycle efficiency, so
    they can be swept without touching the network topology.
    """
    log = []

    OilLoop = Network()
    OilLoop.units.set_defaults(
        temperature="K", pressure="Pa", pressure_difference="Pa",
        enthalpy="J/kg", heat="W", power="W", mass_flow="kg/s",
    )
    OilLoop.iterinfo = False

    cycle_closer_oil = CycleCloser("Oil Cycle Closer")
    htf_pump = Pump("HTF circulation pump")
    splitter_cold = Splitter("Cold header splitter", num_out=2)
    solar_field = ParabolicTrough("Solar Field")
    splitter_hot = Splitter("Hot header splitter", num_out=2)
    charge_hx_oil = SimpleHeatExchanger("Charge HX (oil side)")
    discharge_hx_oil = SimpleHeatExchanger("Discharge HX (oil side)")
    merge_hot = Merge("Hot header merge", num_in=2)
    oil_side_sg = SimpleHeatExchanger("Steam Generator (oil side)")
    merge_cold = Merge("Cold header merge", num_in=2)

    o1 = Connection(cycle_closer_oil, "out1", htf_pump, "in1",
                    label=state(1, "cold header -> HTF pump"))
    o2 = Connection(htf_pump, "out1", splitter_cold, "in1",
                    label=state(2, "HTF pump -> cold header splitter"))
    o3 = Connection(splitter_cold, "out1", solar_field, "in1",
                    label=state(3, "cold header -> solar field", mark=True))
    o4 = Connection(solar_field, "out1", splitter_hot, "in1",
                    label=state(4, "solar field -> hot header splitter", mark=True))
    o5 = Connection(splitter_hot, "out1", merge_hot, "in1",
                    label=state(5, "hot header -> ORC superheater + reheater (direct)"))
    o6 = Connection(splitter_hot, "out2", charge_hx_oil, "in1",
                    label=state(6, "hot header -> charge HX", mark=True))
    o7 = Connection(charge_hx_oil, "out1", merge_cold, "in2",
                    label=state(7, "charge HX -> cold header", mark=True))
    o8 = Connection(splitter_cold, "out2", discharge_hx_oil, "in1",
                    label=state(8, "cold header -> discharge HX", mark=True))
    o9 = Connection(discharge_hx_oil, "out1", merge_hot, "in2",
                    label=state(9, "discharge HX -> hot header", mark=True))
    # The oil side of the solar heat injection. Here its duty goes to the top end
    # of the organic bottoming cycle, so the labels name the ORC superheater and
    # reheater rather than the nuclear steam generators.
    o10 = Connection(merge_hot, "out1", oil_side_sg, "in1",
                     label=state(10, "hot header -> ORC superheater + reheater", mark=True))
    o11 = Connection(oil_side_sg, "out1", merge_cold, "in1",
                     label=state(11, "ORC superheater + reheater -> cold header", mark=True))
    o12 = Connection(merge_cold, "out1", cycle_closer_oil, "in1",
                     label=state(12, "cold header merge -> closer"))

    OilLoop.add_conns(o1, o2, o3, o4, o5, o6, o7, o8, o9, o10, o11, o12)

    # The cold header is held at 28 bar so that after the field pressure drop the
    # hot end still sits well above the ~10.6 bar vapour pressure of Therminol
    # VP-1 at 393 C. A collector loop drops roughly 10 bar, which is what makes
    # HTF circulation a MW-scale parasitic rather than a rounding error.
    o1.set_attr(fluid=oil_fluid, p=p_cold_header, T=T_cold_header)

    htf_pump.set_attr(eta_s=eta_s_htf_pump)
    solar_field.set_attr(A=collector_area, pr=pr_solar_field)
    oil_side_sg.set_attr(pr=pr_oil_sg)
    # The storage HXs sit in parallel branches whose inlet and outlet pressures are
    # both pinned by the splitters/merges, so their pr has to stay free: giving them
    # one as well would close a pressure loop and over-determine the network.

    # ---------------------------------------------------------------------------
    # NETWORK 2 -- Nuclear steam cycle + organic bottoming cycle
    #
    # Both cycles live in one TESPy network because they share a real component:
    # the nuclear condenser condenses steam on its shell side and boils the
    # organic fluid on its tube side, so the coupling is a genuine two-fluid heat
    # exchanger rather than a matched duty.
    #
    # The oil loop is still coupled by duty only: the solar superheater and solar
    # reheater on the ORC receive -oil_side_sg.Q each timestep.
    # ---------------------------------------------------------------------------
    SteamCycle = Network()
    SteamCycle.units.set_defaults(
        temperature="K",
        pressure="Pa",
        pressure_difference="Pa",
        enthalpy="J/kg",
        heat="W",
        power="W",
        mass_flow="kg/s"
    )

    working_fluid = {"water": 1}

    cc = CycleCloser("cycle closer")

    # Two steam generators, as built: the feedwater splits between them and the two
    # main steam headers recombine ahead of the turbine stop valves.
    steam_generator_1 = SimpleHeatExchanger("steam generator 1")
    steam_generator_2 = SimpleHeatExchanger("steam generator 2")

    feedwater_split = Splitter("feedwater splitter", num_out=2)
    main_steam_merge = Merge("main steam merge", num_in=2)

    # The whole of the nuclear heat rejection goes into the bottoming cycle. There
    # is no cooling water on the nuclear side: the organic fluid is the coolant,
    # and a Condenser holds its own outlet at saturated liquid, so the duty is
    # whatever it takes to condense the exhaust and the ORC mass flow follows.
    nuclear_condenser = Condenser("nuclear condenser / ORC evaporator")
    condenser_merge = Merge("condenser merge", num_in=2)
    HP_turbine = MultiStageExtractionTurbine("HP turbine", num_stages=4)

    main_steam_split = Splitter("main steam splitter", num_out=2)

    moisture_separator = DropletSeparator("moisture separator")

    # Two-stage interstage reheat. Heater 2 is the low-temperature stage (fed by the
    # HP turbine stage-1 bleed), heater 1 the high-temperature stage (fed by main
    # steam bled upstream of the HP turbine). Configuration 1 puts a solar reheater
    # ahead of heater 1's shell; there is deliberately none here.
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

    # Main steam leaves the header at the state the steam generators produce and
    # goes straight to the turbine stop valves. Configuration 1 inserts a solar
    # superheater here; the whole point of configuration 2 is that it does not.
    s1 = Connection(cc, "out1", main_steam_split, "in1",
                    label=state(1, "main steam header -> main steam splitter", mark=True))
    s1b = Connection(main_steam_split, "out1", HP_turbine, "in1",
                     label=state(2, "main steam -> HP turbine inlet", mark=True))
    s1c = Connection(main_steam_split, "out2", interstage_heater_1, "in1",
                     label=state(3, "main steam bleed -> reheat stage 1 shell", mark=True))

    # MultiStageExtrastionTurbine: out1 is after stage 1 (highest outlet P),
    # outN is the exhaust (lowest P). Stage i+1 uses out{i}'s (p, h) as its inlet.
    s30 = Connection(HP_turbine, "out1", interstage_heater_2, "in1",
                     label=state(4, "HP bleed 1 -> reheat stage 2 shell", mark=True))
    s3 = Connection(HP_turbine, "out2", HP_FWH_2_shell_merge, "in1",
                    label=state(5, "HP bleed 2 -> HP FWH 2 shell", mark=True))
    s13 = Connection(HP_turbine, "out3", HP_FWH_M, "in2",
                     label=state(6, "HP bleed 3 -> HP FWH 1 shell", mark=True))
    s2 = Connection(HP_turbine, "out4", moisture_separator, "in1",
                    label=state(7, "HP turbine exhaust -> moisture separator", mark=True))

    # DropletSeparator: out1 is the saturated liquid drain, out2 the saturated vapour
    # that goes on to the interstage reheaters and the LP turbine.
    s2c = Connection(moisture_separator, "out1", MSR_FWH, "in1",
                     label=state(8, "separator drain -> MSR drain cooler"))
    s2a = Connection(moisture_separator, "out2", interstage_heater_2, "in2",
                     label=state(9, "separated vapour -> reheat stage 2", mark=True))
    s2d = Connection(interstage_heater_2, "out2", interstage_heater_1, "in2",
                     label=state(10, "reheat stage 2 outlet -> reheat stage 1"))
    s2b = Connection(interstage_heater_1, "out2", LP_turbine_stg1, "in1",
                     label=state(11, "reheated steam -> LP turbine inlet", mark=True))

    # LP expansion and the three LP bleeds.
    s40 = Connection(LP_turbine_stg1, "out1", LP_FWH_2_merge, "in2",
                     label=state(12, "LP bleed 1 -> LP FWH 2 shell", mark=True))
    s41 = Connection(LP_turbine_stg1, "out2", LP_bleed_split_1, "in1",
                     label=state(13, "LP stage 1 exhaust (LP bleed 2 pressure)", mark=True))
    s42 = Connection(LP_bleed_split_1, "out1", LP_FWH_3_merge, "in2",
                     label=state(14, "LP bleed 2 -> LP FWH 3 shell", mark=True))
    s43 = Connection(LP_bleed_split_1, "out2", LP_turbine_stg2, "in1",
                     label=state(15, "LP stage 1 exhaust -> LP turbine stage 2 inlet", mark=True))
    s44 = Connection(LP_turbine_stg2, "out1", LP_bleed_split_2, "in1",
                     label=state(16, "LP stage 2 exhaust (LP bleed 3 pressure)", mark=True))
    s45 = Connection(LP_bleed_split_2, "out1", LP_FWH_4_merge, "in2",
                     label=state(17, "LP bleed 3 -> LP FWH 4 shell", mark=True))
    s46 = Connection(LP_bleed_split_2, "out2", LP_turbine_stg3, "in1",
                     label=state(18, "LP stage 2 exhaust -> LP turbine stage 3 inlet", mark=True))

    s5 = Connection(LP_turbine_stg3, "out1", condenser_merge, "in1",
                    label=state(19, "LP turbine exhaust (nuclear backpressure)", mark=True))
    s6 = Connection(condenser_merge, "out1", nuclear_condenser, "in1",
                    label=state(20, "nuclear exhaust -> nuclear condenser", mark=True))
    s7 = Connection(nuclear_condenser, "out1", condensate_pump, "in1",
                    label=state(21, "nuclear condensate -> condensate pump", mark=True))

    # Feedwater climbs the LP train from the coldest heater upwards.
    s8 = Connection(condensate_pump, "out1", LP_FWH_4, "in2",
                    label=state(22, "condensate pump discharge -> LP FWH 4", mark=True))
    s60 = Connection(LP_FWH_4, "out2", LP_FWH_3, "in2",
                     label=state(23, "feedwater LP FWH 4 -> LP FWH 3"))
    s61 = Connection(LP_FWH_3, "out2", LP_FWH_2, "in2",
                     label=state(24, "feedwater LP FWH 3 -> LP FWH 2"))
    s62 = Connection(LP_FWH_2, "out2", LP_FWH, "in2",
                     label=state(25, "feedwater LP FWH 2 -> LP FWH 1"))
    s9 = Connection(LP_FWH, "out2", MSR_FWH, "in2",
                    label=state(26, "feedwater LP FWH 1 -> MSR drain FWH"))
    s9a = Connection(MSR_FWH, "out2", HP_pump, "in1",
                     label=state(27, "MSR drain FWH -> feed pump", mark=True))
    s10 = Connection(HP_pump, "out1", HP_FWH_1, "in2",
                     label=state(28, "feed pump discharge -> HP FWH 1", mark=True))
    s11 = Connection(HP_FWH_1, "out2", HP_FWH_2, "in2",
                     label=state(29, "feedwater HP FWH 1 -> HP FWH 2"))
    s16 = Connection(HP_FWH_2, "out2", RH_FWH, "in2",
                     label=state(30, "feedwater HP FWH 2 -> reheater drain FWH"))
    s38 = Connection(RH_FWH, "out2", feedwater_split, "in1",
                     label=state(31, "reheater drain FWH -> feedwater splitter", mark=True))
    s39 = Connection(feedwater_split, "out1", steam_generator_1, "in1",
                     label=state(32, "feedwater -> steam generator 1", mark=True))
    s72 = Connection(feedwater_split, "out2", steam_generator_2, "in1",
                     label=state(33, "feedwater -> steam generator 2", mark=True))
    s73 = Connection(steam_generator_1, "out1", main_steam_merge, "in1",
                     label=state(34, "steam generator 1 -> main steam header", mark=True))
    s74 = Connection(steam_generator_2, "out1", main_steam_merge, "in2",
                     label=state(35, "steam generator 2 -> main steam header", mark=True))
    s0 = Connection(main_steam_merge, "out1", cc, "in1",
                    label=state(36, "main steam header -> cycle closer"))

    # Interstage heater shell sides and their cascaded drains.
    s31 = Connection(interstage_heater_1, "out1", interstage_heater_1_valve, "in1")
    s32 = Connection(interstage_heater_1_valve, "out1", interstage_drain_merge, "in1")
    s33 = Connection(interstage_heater_2, "out1", interstage_drain_merge, "in2")
    s34 = Connection(interstage_drain_merge, "out1", RH_FWH, "in1",
                     label=state(37, "merged reheater drains -> reheater drain FWH shell"))
    s35 = Connection(RH_FWH, "out1", RH_FWH_valve, "in1")
    s36 = Connection(RH_FWH_valve, "out1", HP_FWH_2_shell_merge, "in2")
    s37 = Connection(HP_FWH_2_shell_merge, "out1", HP_FWH_2, "in1",
                     label=state(38, "merged HP FWH 2 shell inlet"))

    s12 = Connection(HP_FWH_valve_2, "out1", HP_FWH_M, "in1")
    s14 = Connection(HP_FWH_M, "out1", HP_FWH_1, "in1",
                     label=state(39, "merged HP FWH 1 shell inlet"))
    s15 = Connection(HP_FWH_1, "out1", HP_FWH_valve_1, "in1")
    s17 = Connection(HP_FWH_2, "out1", HP_FWH_valve_2, "in1")

    # Cascaded LP shell drains: HP FWH 1 -> LP FWH 1 -> 2 -> 3 -> 4 -> condenser.
    s18 = Connection(HP_FWH_valve_1, "out1", LP_FWH, "in1",
                     label=state(40, "HP FWH 1 drain -> LP FWH 1 shell"))
    s19 = Connection(LP_FWH, "out1", LP_FWH_valve, "in1")
    s20 = Connection(LP_FWH_valve, "out1", LP_FWH_2_merge, "in1")
    s63 = Connection(LP_FWH_2_merge, "out1", LP_FWH_2, "in1",
                     label=state(41, "merged LP FWH 2 shell inlet"))
    s64 = Connection(LP_FWH_2, "out1", LP_FWH_2_valve, "in1")
    s65 = Connection(LP_FWH_2_valve, "out1", LP_FWH_3_merge, "in1")
    s66 = Connection(LP_FWH_3_merge, "out1", LP_FWH_3, "in1",
                     label=state(42, "merged LP FWH 3 shell inlet"))
    s67 = Connection(LP_FWH_3, "out1", LP_FWH_3_valve, "in1")
    s68 = Connection(LP_FWH_3_valve, "out1", LP_FWH_4_merge, "in1")
    s69 = Connection(LP_FWH_4_merge, "out1", LP_FWH_4, "in1",
                     label=state(43, "merged LP FWH 4 shell inlet"))
    s70 = Connection(LP_FWH_4, "out1", LP_FWH_4_valve, "in1")
    s71 = Connection(LP_FWH_4_valve, "out1", condenser_merge, "in2")

    # The MSR drain leaves its cooler at ~420 K. Flashing it straight to the
    # condenser threw away ~50 MW; cascading it into the top of the LP shell train
    # instead lets that heat displace bleed steam.
    s21 = Connection(MSR_FWH, "out1", MSR_FWH_valve, "in1")
    s22 = Connection(MSR_FWH_valve, "out1", LP_FWH_2_merge, "in3")

    # Each steam generator carries its DCD rating of 1707 MWt, so the total NSSS heat
    # input is 3414 MWt and the main steam flow follows from the two duties. Only one
    # of the two shells may carry a pressure spec: both outlets are pinned to the main
    # steam header pressure by the merge, so a second pr equation would be redundant
    # with it and leave the Jacobian singular.
    steam_generator_1.set_attr(pr=pr_steam_generator, Q=steam_generator_duty)
    steam_generator_2.set_attr(Q=steam_generator_duty)

    # Isentropic efficiencies are the DCD-consistent values that land the shaft output
    # at 1200 MW: the wet LP stages run well below dry-expansion efficiency.
    HP_turbine.set_attr(
        eta_s1=eta_s_hp_turbine, eta_s2=eta_s_hp_turbine,
        eta_s3=eta_s_hp_turbine, eta_s4=eta_s_hp_turbine,
    )
    LP_turbine_stg1.set_attr(eta_s1=eta_s_lp_turbine, eta_s2=eta_s_lp_turbine)
    LP_turbine_stg2.set_attr(eta_s=eta_s_lp_turbine)
    LP_turbine_stg3.set_attr(eta_s=eta_s_lp_turbine)

    # Interstage heaters. Each shell condenses to x=0 (set on s31/s33) and each cold
    # outlet temperature is fixed (s2d, s2b), so the bleed mass flows follow from the
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

    # LP FWH 1 carries the whole HP FWH 1 drain, and that flow is already fixed
    # upstream. Its duty is therefore not free: x=0 on s19 closes the shell side and
    # the feedwater rise on s9 is the result. A ttd spec here would demand a duty
    # roughly twice what the drain can supply.
    LP_FWH.set_attr(pr1=0.97, pr2=0.97)

    # LP FWH 2/3/4 each have one free bleed flow, so x=0 on the drain plus ttd_u on
    # the feedwater outlet is exactly determined.
    LP_FWH_2.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)
    LP_FWH_3.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)
    LP_FWH_4.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)

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

    # Main steam, DCD Fig 10.1-1: 808 psia / 1197.6 BTU/lb. The flow follows from the
    # two steam generator duties, so only a start value is given here.
    s1.set_attr(p=p_main_steam, h=h_main_steam, m0=1891, fluid=working_fluid)
    s1b.set_attr(m0=1824, h0=2.786e6)  # main steam -> HP turbine
    s1c.set_attr(m0=66, h0=2.786e6)  # main steam bleed -> reheat stage 1 shell

    # HP turbine outlets: pressures fall along the stage order out1 -> ... -> out4.
    # Extrastion masses are results of each heater's ttd_u. s13 sits at 2.0 MPa so
    # that Tsat = 485.5 K supports the DCD's 478 K feedwater point ahead of the
    # final heater, and s3 at 2.83 MPa (Tsat = 503.6 K) the 500.9 K SG inlet.
    s2.set_attr(p=p_hp_exhaust, m0=1388, h0=2.55e6)  # HP exhaust -> moisture separator
    s2a.set_attr(m0=1216, h0=2.782e6)  # separated vapour -> interstage heater 2
    s2d.set_attr(T=T_reheat_stage_1, m0=1216, h0=2.863e6)  # first reheat stage outlet
    s2b.set_attr(T=T_lp_inlet, m0=1216, h0=2.950e6)  # reheated steam -> LP turbine
    s2c.set_attr(m0=172, h0=7.87e5)  # separator drain -> MSR drain FWH
    s30.set_attr(p=p_hp_bleed_1, m0=60, h0=2.740e6)  # stage-1 bleed -> interstage heater 2
    s3.set_attr(p=p_hp_bleed_2, m0=92, h0=2.690e6)  # stage-2 extraction -> HP FWH 2
    s13.set_attr(p=p_hp_bleed_3, m0=284, h0=2.640e6)  # stage-3 extraction -> HP FWH merge

    # Interstage heater drains. x=0 on both shells sets the bleed flows; heater 1's
    # drain is then throttled to heater 2's shell-outlet pressure, whish is what the
    # merge pins the two branshes to.
    s31.set_attr(x=0, m0=66, h0=1.179e6)
    s32.set_attr(m0=66, h0=1.179e6)
    s33.set_attr(x=0, m0=60, h0=1.079e6)
    s34.set_attr(m0=126, h0=1.132e6)
    s35.set_attr(m0=126, h0=9.93e5)
    s36.set_attr(m0=126, h0=9.93e5)
    s37.set_attr(m0=218, h0=1.706e6)

    # LP bleed pressures. These are NOT the DCD values: running the nuclear cycle as
    # a topping cycle at 1 bar backpressure puts the DCD's 0.289 / 0.086 / 0.0405 MPa
    # extractions below the exhaust pressure, which the turbine cannot do. The ladder
    # is respaced 0.45 / 0.30 / 0.20 MPa, i.e. Tsat 421 / 407 / 393 K, against
    # condensate that now leaves the condenser at 373 K instead of 312 K.
    s40.set_attr(p=p_lp_bleed_1, m0=104, h0=2.740e6)  # LP bleed 1 -> LP FWH 2
    s41.set_attr(p=p_lp_bleed_2, m0=1112, h0=2.700e6)  # LP stage 1 exhaust
    s42.set_attr(m0=16, h0=2.700e6)  # LP bleed 2 -> LP FWH 3
    s43.set_attr(m0=1096, h0=2.700e6)
    s44.set_attr(p=p_lp_bleed_3, m0=1096, h0=2.660e6)  # LP stage 2 exhaust
    s45.set_attr(m0=90, h0=2.660e6)  # LP bleed 3 -> LP FWH 4
    s46.set_attr(m0=1006, h0=2.660e6)

    # Condenser backpressure, raised from the DCD's 7 kPa so that the nuclear cycle
    # condenses at 372.8 K and can actually boil the organic fluid. This costs the
    # nuclear turbine a large slice of its LP expansion, which is the whole trade
    # this configuration exists to quantify.
    s5.set_attr(p=p_nuclear_condenser, m0=1006, h0=2.600e6)  # LP turbine exhaust
    s6.set_attr(m0=1890, h0=2.55e6)

    # Feedwater now starts from 373 K condensate rather than 312 K, so every start
    # enthalpy along the LP train moves up with it.
    s8.set_attr(p=p_condensate, m0=1891, h0=4.20e5)

    s60.set_attr(m0=1891, h0=4.83e5)
    s61.set_attr(m0=1891, h0=5.39e5)
    s62.set_attr(m0=1891, h0=6.01e5)
    s9.set_attr(m0=1891, h0=6.40e5)
    s9a.set_attr(m0=1891, h0=6.55e5)

    s10.set_attr(m0=1891, h0=6.203e5)
    s11.set_attr(m0=1891, h0=8.873e5)
    s16.set_attr(m0=1891, h0=9.706e5)
    s38.set_attr(m0=1891, h0=9.798e5)

    # Even split between the two steam generators: fixing the enthalpy leaving shell 1
    # at the main steam value forces the merge to hand shell 2 the same outlet state,
    # so the two duties are carried by equal mass flows.
    s39.set_attr(m0=945, h0=9.798e5)
    s72.set_attr(m0=945, h0=9.798e5)
    s73.set_attr(h=h_main_steam, m0=945)
    s74.set_attr(m0=945, h0=2.786e6)

    s14.set_attr(m0=502, h0=1.908e6)
    s15.set_attr(x=0, m0=502, h0=9.015e5)  # HP FWH 1 drain leaves as saturated liquid
    s17.set_attr(x=0, m0=218, h0=9.854e5)  # HP FWH 2 drain leaves as saturated liquid

    # LP FWH 1 shell pressure. Tsat(0.6 MPa) = 432 K against feedwater at 400 K, so
    # the throttled HP FWH 1 drain arrives wet (x ~ 0.11) and condenses out.
    s18.set_attr(p=p_lp_fwh_1_shell, m0=502, h0=9.015e5)
    s19.set_attr(x=0, m0=502, h0=6.652e5)
    s20.set_attr(m0=502, h0=6.652e5)

    s63.set_attr(m0=778, h0=9.293e5)
    s64.set_attr(x=0, m0=778, h0=6.23e5)
    s65.set_attr(m0=778, h0=6.23e5)

    s66.set_attr(m0=794, h0=6.60e5)
    s67.set_attr(x=0, m0=794, h0=5.61e5)
    s68.set_attr(m0=794, h0=5.61e5)

    s69.set_attr(m0=884, h0=6.00e5)
    s70.set_attr(x=0, m0=884, h0=5.05e5)
    s71.set_attr(m0=884, h0=5.05e5)

    s21.set_attr(m0=172, h0=6.194e5)
    s22.set_attr(m0=172, h0=6.194e5)

    ##############################################
    # Secondary Organic Rankine Cycle            #
    ##############################################
    # The nuclear condenser is this cycle's boiler, so there is no separate
    # evaporator. The cycle is left non-regenerative: the deaerator and HP heater
    # this secondary cycle inherited from Andasol sat at saturation at 10.04 and
    # 20.72 bar, i.e. 453 K and 487 K, and any feedwater hotter than the 372.8 K
    # the nuclear steam condenses at stops heat crossing the nuclear condenser
    # altogether. Rebuilt at ORC pressures and placed ahead of the evaporator,
    # regeneration would raise output - the rejection duty is fixed by the nuclear
    # side, so the mass flow just rises to absorb it - at the cost of a much
    # larger condenser. That is deliberately not modelled here.
    cycle_closer_secondary = CycleCloser("ORC Cycle Closer")
    orc_superheater = SimpleHeatExchanger("ORC superheater : Solar input")
    orc_reheater = SimpleHeatExchanger("ORC reheater : Solar input")
    HP_turbine_secondary = Turbine("ORC HP Turbine")
    LP_turbine_secondary = Turbine("ORC LP Turbine")
    condenser_secondary = Condenser("ORC condenser")
    feed_pump_secondary = Pump("ORC feed pump")
    cooling_water_in = Source("Cooling water in")
    cooling_water_out = Sink("Cooling water out")

    # The ORC gets its own results table, so its states are numbered from 1
    # again rather than carrying on from the nuclear cycle's 36.
    c1 = Connection(cycle_closer_secondary, "out1", nuclear_condenser, "in2",
                    label=state(1, "ORC feed -> nuclear condenser (cold side)", mark=True))
    c2 = Connection(nuclear_condenser, "out2", orc_superheater, "in1",
                    label=state(2, "saturated ORC vapour -> solar superheater", mark=True))
    c3 = Connection(orc_superheater, "out1", HP_turbine_secondary, "in1",
                    label=state(3, "solar superheater -> ORC HP turbine inlet", mark=True))
    c4 = Connection(HP_turbine_secondary, "out1", orc_reheater, "in1",
                    label=state(4, "ORC HP exhaust -> solar reheater", mark=True))
    c5 = Connection(orc_reheater, "out1", LP_turbine_secondary, "in1",
                    label=state(5, "solar reheater -> ORC LP turbine inlet", mark=True))
    c6 = Connection(LP_turbine_secondary, "out1", condenser_secondary, "in1",
                    label=state(6, "ORC LP exhaust (ORC backpressure)", mark=True))
    c7 = Connection(condenser_secondary, "out1", feed_pump_secondary, "in1",
                    label=state(7, "ORC condensate -> ORC feed pump", mark=True))
    c8 = Connection(feed_pump_secondary, "out1", cycle_closer_secondary, "in1",
                    label=state(8, "ORC feed pump discharge"))
    c9 = Connection(cooling_water_in, "out1", condenser_secondary, "in2",
                    label=state(9, "ORC cooling water in"))
    c10 = Connection(condenser_secondary, "out2", cooling_water_out, "in1",
                     label=state(10, "ORC cooling water out"))

    # The nuclear condenser is the only place the two cycles touch. Its shell side
    # holds saturated liquid by construction (Condenser, subcooling off), so the
    # duty is whatever it takes to condense the whole nuclear exhaust. Saturated
    # vapour on the tube side (x=1 on c2) then fixes the ORC mass flow: it is
    # exactly the flow that the rejected heat can boil, nothing more.
    nuclear_condenser.set_attr(pr1=1, pr2=pr_nuclear_condenser_orc)
    condenser_secondary.set_attr(pr1=1, pr2=0.98)

    HP_turbine_secondary.set_attr(eta_s=eta_s_hp_turbine_secondary)
    LP_turbine_secondary.set_attr(eta_s=eta_s_lp_turbine_secondary)
    feed_pump_secondary.set_attr(eta_s=eta_s_feed_pump_secondary)

    # Evaporation pressure has to keep Tsat below the nuclear condensing
    # temperature or no heat crosses the exchanger at all: 10 bar puts R245fa at
    # 362.9 K against steam condensing at 372.8 K, i.e. a 10 K pinch. This is the
    # single most important knob in the configuration.
    c2.set_attr(fluid=secondary_fluid, p=p_evaporator_secondary, x=1, m0=11000)
    c3.set_attr(m0=11000)
    c4.set_attr(p=p_hp_exhaust_secondary, m0=11000)
    c5.set_attr(m0=11000)
    c6.set_attr(p=p_condenser_secondary, m0=11000)
    c7.set_attr(m0=11000)
    c8.set_attr(m0=11000)

    # The rejection is a couple of GW, so the cooling water flow is a result of the
    # duty rather than something worth guessing: both terminal temperatures are
    # fixed and the flow follows.
    c9.set_attr(fluid=cooling_fluid, T=T_cw_in, p=p_cw, m0=50000)
    c10.set_attr(T=T_cw_out)

    SteamCycle.add_conns(
        s0, s1, s1b, s1c, s2, s2a, s2b, s2c, s2d, s3, s5,
        s6, s7, s8, s9, s9a, s10, s11, s12, s13, s14, s15,
        s16, s17, s18, s19, s20, s21, s22,
        s30, s31, s32, s33, s34, s35, s36, s37, s38, s39,
        s40, s41, s42, s43, s44, s45, s46,
        s60, s61, s62, s63, s64, s65, s66, s67, s68, s69, s70, s71,
        s72, s73, s74,
        c1, c2, c3, c4, c5, c6, c7, c8, c9, c10,
    )

    trim_results(OilLoop, SteamCycle)

    # Both cycles are on the same shaft-count for accounting purposes: the nuclear
    # turbines plus the ORC turbines, and every pump in either loop.
    turbine_list = [
        HP_turbine, LP_turbine_stg1, LP_turbine_stg2, LP_turbine_stg3,
        HP_turbine_secondary, LP_turbine_secondary,
    ]
    pump_list = [
        condensate_pump, HP_pump, feed_pump_secondary,
    ]

    oil_conns = [o3, o4, o6, o7, o8, o9]

    # The two cycles share one network but not one results table. The nuclear
    # condenser is the component they share, so it is listed on both sides: its
    # shell is the last state of the nuclear cycle and its tubes the first of
    # the ORC.
    orc_comps = {
        cycle_closer_secondary, nuclear_condenser, orc_superheater, orc_reheater,
        HP_turbine_secondary, LP_turbine_secondary, condenser_secondary,
        feed_pump_secondary, cooling_water_in, cooling_water_out,
    }
    orc_conns = {c1, c2, c3, c4, c5, c6, c7, c8, c9, c10}
    nuclear_comps = (set(SteamCycle.comps["object"]) - orc_comps) | {nuclear_condenser}
    nuclear_conns = set(SteamCycle.conns["object"]) - orc_conns

    # ---------------------------------------------------------------------------
    # Design point check against Asfand et al. (2020), Tables 1 and 4
    # ---------------------------------------------------------------------------
    def solve_design_point():
        """Put the plant on its design duty: full field, no storage exchange."""
        Q_to_steam_design = solve_oil_loop(
            Q_design_thermal, 0.0, 0.0,
            oil_conns=oil_conns, solar_field=solar_field,
            T_field_out=T_field_out, T_charge_out=T_cold_header,
            T_discharge_out=T_discharge_out,
            charge_hx_oil=charge_hx_oil, discharge_hx_oil=discharge_hx_oil,
            OilLoop=OilLoop, oil_sg=oil_side_sg,
        )
        return solve_power_block(
            Q_to_steam_design, orc_superheater, orc_reheater,
            SteamCycle, turbine_list, pump_list, reheat_fraction=reheat_fraction,
            pr_heat_in=pr_orc_superheater, pr_reheater=pr_orc_reheater,
        )

    P_turbine_design, P_pumps_design = solve_design_point()

    # ---------------------------------------------------------------------------
    # Annual simulation
    # ---------------------------------------------------------------------------
    day = (24 * day_number) - 1
    eod = day + 24

    hourly_rows = DNI_values[day:eod] if hourly else []
    for hour_num, day_of_year, DNI, T_amb, solar_elevation in hourly_rows:
        T_amb_K = T_amb + 273.15

        Q_solar = Q_solar_field(
            hour_num=hour_num, DNI=DNI, T_amb_K=T_amb_K,
            collector_area=collector_area, optical_efficiency=optical_efficiency,
            T_htf_in=T_htf_in, mdot_htf=mdot_htf, htf=htf,
            day_of_year=day_of_year, solar_elevation_deg=solar_elevation,
        )
        step = dispatch(Q_solar=Q_solar, Q_design=Q_design_thermal, tank=tank, dt=dt)

        # --- Oil loop side ---
        # The field carries only the heat the plant can actually use; the rest is
        # defocused, otherwise a full hot tank would push its surplus into the
        # power block.
        Q_to_steam = solve_oil_loop(
            Q_solar - step["Q_defocus"], step["Q_to_storage"], step["Q_from_storage"],
            oil_conns=oil_conns, solar_field=solar_field,
            T_field_out=T_field_out, T_charge_out=T_cold_header,
            T_discharge_out=T_discharge_out,
            charge_hx_oil=charge_hx_oil, discharge_hx_oil=discharge_hx_oil,
            OilLoop=OilLoop, oil_sg=oil_side_sg,
        )

        # --- Power block side ---
        # Unlike configuration 1 the bottoming cycle is not driven by the sun: it
        # is driven by the nuclear rejection heat, which never stops. The ORC
        # therefore runs at full flow all night with its superheater and reheater
        # simply switched out, and no trickle duty is needed to keep it solvable.
        if step["Q_to_pb"] <= 0 or Q_to_steam <= Q_MIN_BRANCH:
            Q_to_steam = 0.0

        P_turbine, P_pumps = solve_power_block(
            Q_to_steam, orc_superheater, orc_reheater,
            SteamCycle, turbine_list, pump_list, reheat_fraction=reheat_fraction,
            pr_heat_in=pr_orc_superheater, pr_reheater=pr_orc_reheater,
        )
        m_steam = s2.m.val

        step["hour"] = hour_num
        step["day_of_year"] = day_of_year
        step["DNI"] = DNI
        step["T_amb"] = T_amb
        step["Q_sg_oil"] = Q_to_steam
        step["m_oil_field"] = o3.m.val
        step["T_sg_oil_in"] = o10.T.val
        step["m_steam"] = m_steam
        step["m_orc"] = c1.m.val
        # Heat handed from the topping cycle to the bottoming cycle, and the heat
        # the bottoming cycle finally throws away to the cooling water.
        step["Q_nuclear_condenser"] = -nuclear_condenser.Q.val
        step["Q_orc_condenser"] = -condenser_secondary.Q.val
        step["T_orc_live"] = c3.T.val
        step["P_turbine"] = P_turbine
        step["P_pumps"] = P_pumps + htf_pump.P.val
        step["P_net"] = P_turbine - step["P_pumps"]
        # Both steam generators are on rating, so the nuclear heat input is twice
        # steam_generator_duty, not once.
        step["efficiency"] = step["P_net"] / (step["Q_sg_oil"] + 2 * steam_generator_duty)
        log.append(step)

        if verbose:
            print("\n" * 5)
            print(f"Turbine power: {step["P_turbine"]}")
            print(f"Pump power: {step["P_pumps"]}")
            print(f"Efficiency: {step["efficiency"]}")

            print_results_split(SteamCycle, [
                (banner("Nuclear steam cycle (topping)", Fore.MAGENTA),
                 nuclear_comps, nuclear_conns),
                (banner("Organic Rankine cycle (bottoming)", Fore.CYAN),
                 orc_comps, orc_conns),
            ])

            print(banner("Oil loop", Fore.GREEN))
            OilLoop.print_results()

    results = pd.DataFrame(log)
    if results_csv is not None:
        results.to_csv(results_csv, index=False)
    if log:
        print("\n" * 5)
        print(f"Turbine power: {step["P_turbine"]}")
        print(f"Pump power: {step["P_pumps"]}")
        print(f"Efficiency: {step["efficiency"]}")

    # The hourly run leaves the networks wherever the last hour put them, so
    # anything wanting to inspect the plant itself gets it back on design first.
    if design_point_out is not None:
        solve_design_point()
        design_point_out.update({"steam": SteamCycle, "oil": OilLoop})
    return results


if __name__ == "__main__":
    results = solve_configuration2()

    # ---------------------------------------------------------------------------
    # Annual summary
    # ---------------------------------------------------------------------------
    hours = dt / 3600
    to_GWh = hours / 1e9
    Q_incident = (results["DNI"] * collector_area).sum() * to_GWh
    operating = results["P_turbine"] > 0
