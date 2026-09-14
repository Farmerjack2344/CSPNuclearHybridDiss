import pandas as pd
import math
import numpy as np
from colorama import Fore,Back,Style,init
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

def highlight(text):
    return Fore.GREEN + Style.BRIGHT + text + Style.RESET_ALL


def state(number, text, mark=False):
    return f"{number:02d} {highlight(text) if mark else text}"


def trim_results(*networks):
    for network in networks:
        for conn in network.conns["object"]:
            if not conn.label[0].isdigit():
                conn.set_attr(printout=False)
        for comp in network.comps["object"]:
            if isinstance(comp, Valve):
                comp.set_attr(printout=False)

# ---------------------------------------------------------------------------
# Solar field helper functions: to calculate thermal loss
# ---------------------------------------------------------------------------
def cos_theta(day_of_year, solar_hour, solar_elevation_deg):
    """Incidence angle factor for a north-south axis, east-west tracking trough.

    Duffie & Beckman eq. 1.7.2a.
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
        Calculates the heat transferred to the thermal oil in the collector

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

def solve_oil_loop(Q_field, Q_to_storage, Q_from_storage, oil_conns,
                   solar_field, T_field_out, T_charge_out, T_discharge_out,
                   charge_hx_oil=None, discharge_hx_oil=None, OilLoop=None,
                   oil_sg=None):
    """Solve the HTF loop for one timestep and return the duty.

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


def solve_power_block(Q_to_steam, heat_in_component, reheater, Steam_network, turbine_list, pump_list,
                      reheat_fraction=0.2, pr_heat_in=1.0, pr_reheater=1.0):
    """Solve the steam cycle against the duty the HTF loop gave up.

    Returns gross turbine output and the feed water pumping parasitics, both W.

    When there is no heat for the oil to give to the steam the pressure ratio is set to 0.
    So that the Solar super heater and the SOlar reheater dont represent losses and times
    of CSP shutdown

    :param reheat_fraction: percentage of oil bled away to reheat
    :param pr_heat_in: superheater pressure ratio while it is in service
    :param pr_reheater: reheater pressure ratio while it is in service
    """
    in_service = Q_to_steam > 0
    heat_in_component.set_attr(Q=Q_to_steam * (1 - reheat_fraction),
                               pr=pr_heat_in if in_service else 1.0)
    reheater.set_attr(Q=Q_to_steam * reheat_fraction,
                      pr=pr_reheater if in_service else 1.0)
    Steam_network.solve("design")
    P_turbine =  -1 * (sum([i.P.val for i in turbine_list]))
    P_pumps = (sum([i.P.val for i in pump_list]))
    return P_turbine, P_pumps

def set_duty_branch(m_conn, T_conn, component, Q, T_out):
    """Drive a branch from its duty, or park it at a trickle flow when idle.

    """
    if abs(Q) > Q_MIN_BRANCH:
        component.set_attr(Q=Q)
        m_conn.set_attr(m=None)
        T_conn.set_attr(T=T_out)
    else:
        component.set_attr(Q=0)
        T_conn.set_attr(T=None)
        m_conn.set_attr(m=M_MIN)

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
    initial_hot_mass=0.0,
)

# ---------------------------------------------------------------------------
# Field parameters
#----------------------------------------------------------------------------

# Power block design THERMAL input
Q_design_thermal = 118.958e6 + 21.479e6
collector_area = 510120      # m^2, Andasol-1 aperture
optical_efficiency = 0.75
T_htf_in = 273.15 + 293        # K, HTF returned to the field from the SG
mdot_htf = 618.1              # kg/s, design HTF flow

DNI_values = meteorolgoical_values()
dt = 3600  # s, hourly

# ---------------------------------------------------------------------------
# NETWORK 1 -- Oil loop (Therminol VP-1)
# ---------------------------------------------------------------------------
T_oil_cold = T_htf_in            # cold header / field inlet, K
T_oil_hot = 273.15 + 393         # field outlet, K (Therminol VP-1 upper limit)
T_oil_from_storage = T_hot_salt - 5.0  # oil leaving the discharge HX, K
M_MIN = 1.0                      # kg/s trickle flow kept in idle branches
Q_MIN_BRANCH = 1e5               # W below which a branch counts as idle


cooling_fluid = {"water": 1}
oil_fluid = {"INCOMP::TVP1": 1}
working_fluid = {"water": 1}
fluids = [working_fluid,cooling_fluid, oil_fluid]
def solve_configuration1(
        fluids=fluids,
        # --- HTF loop operating states ---
        T_field_out=T_oil_hot,               # K, oil leaving the solar field
        T_cold_header=T_oil_cold,            # K, oil returned to the field / SG outlet
        T_discharge_out=T_oil_from_storage,  # K, oil leaving the discharge HX
        p_cold_header=28e5,                  # Pa, HTF pump discharge pressure


        # --- Solar heat injection into the nuclear steam ---
        reheat_fraction=21.479 / (118.958 + 21.479),  # solar duty sent to the reheater
        #
        main_mass_flow_bleed=66/1891,

        # --- Live steam state ---
        p_main_steam=5.571e6,                # Pa
        h_main_steam=2785.6e3,               # J/kg
        # --- HP turbine extraction / exhaust pressures ---
        p_hp_bleed_1=3.413025e6,  # 495 psia, 1st-stage reheat (DCD Fig 10.1-1)
        p_hp_bleed_2=2.8269e6,               # Pa, 410 psia HP FWH 7
        p_hp_bleed_3=1.7306e6,               # Pa, 251 psia HP FWH 6
        p_hp_exhaust=1.1328e6,               # Pa, 164.3 psia HP exhaust / MSH
        # --- Interstage reheat outlet temperatures ---
        T_reheat_stage_1=490.0,              # K, after the first reheat stage
        T_lp_inlet=527.7,                    # K, 490.2 F at the CIV
        # --- LP turbine extraction / exhaust pressures ---
        p_lp_bleed_1=0.2889e6,               # Pa, 41.9 psia -> LP FWH 4
        p_lp_bleed_4=0.2565e6,               # Pa, 37.2 psia -> LP FWH 3
        p_lp_bleed_2=0.08660e6,              # Pa, 12.56 psia -> LP FWH 2
        p_lp_bleed_3=0.03930e6,              # Pa, 5.70 psia -> LP FWH 1
        p_condenser=8466.0,                  # Pa, 2.50 inHg abs
        # --- Feedwater train ---
        p_condensate=1.28e6,                 # Pa, condensate pump discharge
        p_lp_fwh_4_shell=0.4137e6,           # unused; LP FWH 4 follows p_lp_bleed_1
        ttd_u_fwh=2.222,                     # K, 4 F heater TTD on Fig 10.1-1
        ttd_l_drain_cooler=5.556,            # K, 10 F drain-cooler approach

        # --- Condenser cooling water ---
        T_cw_in=288.15,                      # K
        T_cw_out=300.15,                     # K
        p_cw=1.2e5,                          # Pa
        # --- Simulation window / output ---
        day_number=183,
        verbose=True,
        results_csv="ModelResults/configuration_1_hourly.csv",
        design_point_out=None,
        hourly=True,
):
    """Solve configuration 1: solar heat injected into the nuclear steam cycle.
    :param fluids:
    :param design_point_out: dict to receive the networks, left at the design
        point rather than at the last hour of the run. This is what ts_diagram
        plots, since a cycle diagram of the small hours would show the plant
        with its solar equipment valved out.
    :param hourly: if False, stop after the design-point solve. The T-s
        diagram script uses that so it does not have to run a weather day.


    """
    main_mass_flow = 1891
    # --- Turbomachinery efficiencies ---
    eta_s_hp_turbine = 0.84
    eta_s_lp_turbine = 0.873
    eta_s_condensate_pump = 0.804
    eta_s_feed_pump = 0.804

    # --- Nuclear heat input ---
    steam_generator_duty = 1707e6  # W per steam generator (two fitted)
    pr_steam_generator = 0.97

    eta_s_htf_pump = 0.8
    pr_solar_field = 0.65
    pr_solar_superheater = 0.97
    pr_solar_reheater = 0.97
    pr_oil_sg = 0.95

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
                    label=state(5, "hot header -> solar superheater + reheater (direct)"))
    o6 = Connection(splitter_hot, "out2", charge_hx_oil, "in1",
                    label=state(6, "hot header -> charge HX", mark=True))
    o7 = Connection(charge_hx_oil, "out1", merge_cold, "in2",
                    label=state(7, "charge HX -> cold header", mark=True))
    o8 = Connection(splitter_cold, "out2", discharge_hx_oil, "in1",
                    label=state(8, "cold header -> discharge HX", mark=True))
    o9 = Connection(discharge_hx_oil, "out1", merge_hot, "in2",
                    label=state(9, "discharge HX -> hot header", mark=True))
    # The oil side of the solar heat injection. Its duty is handed to the steam
    # cycle's solar superheater and solar reheater, so the labels name those two
    # rather than the nuclear steam generators further down the steam network.
    o10 = Connection(merge_hot, "out1", oil_side_sg, "in1",
                     label=state(10, "hot header -> solar superheater + reheater", mark=True))
    o11 = Connection(oil_side_sg, "out1", merge_cold, "in1",
                     label=state(11, "solar superheater + reheater -> cold header", mark=True))
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
    # NETWORK 2 -- Steam Rankine cycle (power block)
    # Physically separate fluid loop from the oil loop above. The two are
    # linked ONLY by matching duty: steam_side_sg.Q = -oil_side_sg.Q each
    # timestep (energy in = energy out, no shared TESPy connection since they
    # are different fluids in different networks).
    #
    # Andasol-1 regenerates feed water through three LP heaters, a deaerator and
    # two HP heaters, reaching 250 C before the boiler. That train is lumped here
    # into two open heaters: a deaerator on an LP extraction at 10.04 bar (180 C,
    # the paper's deaerator state) and a second heater on the HP exhaust at
    # 20.72 bar, which takes feed water to about 214 C. Without any regeneration
    # the boiler would be fed at condenser temperature, which cannot be squared
    # with an HTF loop that returns to the field at 293 C. Keeping the larger of
    # the two extractions downstream of the reheater also matters: bleed it all off
    # the HP exhaust instead and the reheater has so little steam to heat that its
    # outlet comes out hotter than the 393 C oil supposedly heating it.
    # ---------------------------------------------------------------------------
    log = []

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



    cwso = Source("cooling water source")
    cwsi = Sink("cooling water sink")

    cc = CycleCloser("cycle closer")

    # Two steam generators, as built: the feedwater splits between them and the two
    # main steam headers recombine ahead of the turbine stop valves.
    steam_generator_1 = SimpleHeatExchanger("steam generator 1")
    steam_generator_2 = SimpleHeatExchanger("steam generator 2")

    super_heater = SimpleHeatExchanger("super heater 0 : Solar input")
    feedwater_split = Splitter("feedwater splitter", num_out=2)
    main_steam_merge = Merge("main steam merge", num_in=2)

    condenser = Condenser("main condenser")
    condenser_merge = Merge("condenser merge", num_in=2)
    HP_turbine = MultiStageExtractionTurbine("HP turbine", num_stages=4)

    main_steam_split = Splitter("main steam splitter", num_out=2)

    moisture_separator = DropletSeparator("moisture separator")

    # Two-stage interstage reheat in process order. Heater 1 is the low-temperature
    # stage (HP turbine stage-1 bleed on the hot inlet). Heater 2 follows it and is
    # the high-temperature stage (main steam, after the solar reheater).
    interstage_heater_0 = SimpleHeatExchanger("interstage heater 0 : Solar input")
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

    s1 = Connection(cc, "out1", super_heater, "in1",
                    label=state(1, "main steam header -> solar superheater", mark=True))

    s1a = Connection(super_heater, "out1", main_steam_split, "in1",
                     label=state(2, "solar superheated main steam", mark=True))
    s1b = Connection(main_steam_split, "out1", HP_turbine, "in1",
                     label=state(3, "main steam -> HP turbine inlet", mark=True))
    s1c = Connection(main_steam_split, "out2", interstage_heater_0, "in1",
                     label=state(4, "main steam bleed -> solar reheater", mark=True))
    s1d = Connection(interstage_heater_0, "out1", interstage_heater_2, "in1",
                     label=state(5, "solar reheater outlet -> reheat stage 2 shell", mark=True))



    # MultiStageExtrastionTurbine: out1 is after stage 1 (highest outlet P),
    # outN is the exhaust (lowest P). Stage i+1 uses out{i}'s (p, h) as its inlet.
    s2_hp = Connection(HP_turbine, "out4", hp_exhaust_split, "in1",
                       label=state(9, "HP turbine exhaust -> splitter", mark=True))
    s2 = Connection(hp_exhaust_split, "out1", moisture_separator, "in1",
                    label=state(9, "HP exhaust -> moisture separator", mark=True))
    s2_da = Connection(hp_exhaust_split, "out2", deaerator, "in4",
                       label=state(9, "HP exhaust steam -> deaerator"))

    # DropletSeparator: out1 is the saturated liquid drain, out2 the saturated vapour
    # that goes on to the interstage reheaters and the LP turbine.
    s2a = Connection(moisture_separator, "out2", interstage_heater_1, "in2",
                     label=state(11, "separated vapour -> reheat stage 1", mark=True))

    s2d = Connection(interstage_heater_1, "out2", interstage_heater_2, "in2",
                     label=state(12, "reheat stage 1 outlet -> reheat stage 2"))
    s2b = Connection(interstage_heater_2, "out2", LP_inlet_split, "in1",
                     label=state(13, "reheated steam -> LP turbine inlet splitter", mark=True))
    s2b1 = Connection(LP_inlet_split, "out1", LP_turbine_1, "in1",
                      label=state(13, "LP inlet splitter -> LP turbine 1"))
    s2b2 = Connection(LP_inlet_split, "out2", LP_turbine_2, "in1",
                      label=state(13, "LP inlet splitter -> LP turbine 2"))
    s2b3 = Connection(LP_inlet_split, "out3", LP_turbine_3, "in1",
                      label=state(13, "LP inlet splitter -> LP turbine 3", mark=True))
    s2c = Connection(moisture_separator, "out1", msr_to_da_valve, "in1",
                     label=state(10, "separator drain -> deaerator valve"))
    s2c_da = Connection(msr_to_da_valve, "out1", deaerator, "in3")

    # Interstage heater shell sides and their sascaded drains.
    s30 = Connection(HP_turbine, "out1", interstage_heater_1, "in1",
                     label=state(6, "HP bleed 1 -> reheat stage 1 shell", mark=True))
    s31 = Connection(interstage_heater_2, "out1", interstage_heater_2_valve, "in1")
    s32 = Connection(interstage_heater_2_valve, "out1", interstage_drain_merge, "in1")
    s33 = Connection(interstage_heater_1, "out1", interstage_drain_merge, "in2")
    s34 = Connection(interstage_drain_merge, "out1", RH_FWH, "in1",
                     label=state(39, "merged reheater drains -> reheater drain FWH shell"))
    s35 = Connection(RH_FWH, "out1", RH_FWH_valve, "in1")
    s36 = Connection(RH_FWH_valve, "out1", HP_FWH_2_shell_merge, "in2")

    s3 = Connection(HP_turbine, "out2", HP_FWH_2_shell_merge, "in1",
                    label=state(7, "HP bleed 2 -> HP FWH 2 shell", mark=True))
    s37 = Connection(HP_FWH_2_shell_merge, "out1", HP_FWH_2, "in1",
                     label=state(40, "merged HP FWH 2 shell inlet"))

    s40 = Connection(LP_turbine_1, "out1", LP_FWH_4, "in1",
                     label=state(14, "LP turbine 1 exhaust -> LP FWH 4", mark=True))
    s40b = Connection(LP_turbine_2, "out1", LP_FWH_3_merge, "in2",
                      label=state(15, "LP turbine 2 extraction -> LP FWH 3", mark=True))
    s42 = Connection(LP_turbine_2, "out2", LP_FWH_2_merge, "in2",
                     label=state(16, "LP turbine 2 exhaust -> LP FWH 2", mark=True))
    s45 = Connection(LP_turbine_3, "out1", LP_FWH_1_merge, "in2",
                     label=state(19, "LP turbine 3 extraction -> LP FWH 1", mark=True))
    s5 = Connection(LP_turbine_3, "out2", condenser_merge, "in1",
                    label=state(21, "LP turbine 3 exhaust -> condenser merge", mark=True))

    s6 = Connection(condenser_merge, "out1", condenser, "in1",
                    label=state(22, "condenser merge -> main condenser inlet", mark=True))

    s7 = Connection(condenser, "out1", condensate_pump, "in1",
                    label=state(23, "condensate -> condensate pump", mark=True))

    # Feedwater climbs the LP train from the condenser: FWH 1 -> 2 -> 3 -> 4.
    s8 = Connection(condensate_pump, "out1", LP_FWH_1, "in2",
                    label=state(24, "condensate pump discharge -> LP FWH 1", mark=True))
    s60 = Connection(LP_FWH_1, "out2", LP_FWH_2, "in2",
                     label=state(25, "feedwater LP FWH 1 -> LP FWH 2"))
    s61 = Connection(LP_FWH_2, "out2", LP_FWH_3, "in2",
                     label=state(26, "feedwater LP FWH 2 -> LP FWH 3"))
    s62 = Connection(LP_FWH_3, "out2", LP_FWH_4, "in2",
                     label=state(27, "feedwater LP FWH 3 -> LP FWH 4"))
    s9 = Connection(LP_FWH_4, "out2", lp_to_da_valve, "in1",
                    label=state(28, "feedwater LP FWH 4 -> deaerator valve"))
    s9d = Connection(lp_to_da_valve, "out1", deaerator, "in1")
    s9a = Connection(deaerator, "out1", HP_pump, "in1",
                     label=state(29, "deaerator -> feed pump", mark=True))

    s18 = Connection(HP_FWH_valve_1, "out1", deaerator, "in2",
                     label=state(42, "HP FWH 1 drain -> deaerator"))
    s19 = Connection(LP_FWH_4, "out1", LP_FWH_4_valve, "in1")
    s20 = Connection(LP_FWH_4_valve, "out1", LP_FWH_3_merge, "in1")
    s63 = Connection(LP_FWH_3_merge, "out1", LP_FWH_3, "in1",
                     label=state(43, "merged LP FWH 3 shell inlet"))
    s64 = Connection(LP_FWH_3, "out1", LP_FWH_3_valve, "in1")
    s65 = Connection(LP_FWH_3_valve, "out1", LP_FWH_2_merge, "in1")
    s66 = Connection(LP_FWH_2_merge, "out1", LP_FWH_2, "in1",
                     label=state(44, "merged LP FWH 2 shell inlet"))
    s67 = Connection(LP_FWH_2, "out1", LP_FWH_2_valve, "in1")
    s68 = Connection(LP_FWH_2_valve, "out1", LP_FWH_1_merge, "in1")
    s69 = Connection(LP_FWH_1_merge, "out1", LP_FWH_1, "in1",
                     label=state(45, "merged LP FWH 1 shell inlet"))
    s70 = Connection(LP_FWH_1, "out1", LP_FWH_1_valve, "in1")
    s71 = Connection(LP_FWH_1_valve, "out1", condenser_merge, "in2")

    s10 = Connection(HP_pump, "out1", HP_FWH_1, "in2",
                     label=state(30, "feed pump discharge -> HP FWH 1", mark=True))

    s11 = Connection(HP_FWH_1, "out2", HP_FWH_2, "in2",
                     label=state(31, "feedwater HP FWH 1 -> HP FWH 2"))

    s12 = Connection(HP_FWH_valve_2, "out1", HP_FWH_M, "in1")
    s13 = Connection(HP_turbine, "out3", HP_FWH_M, "in2",
                     label=state(8, "HP bleed 3 -> HP FWH 1 shell", mark=True))

    s14 = Connection(HP_FWH_M, "out1", HP_FWH_1, "in1",
                     label=state(41, "merged HP FWH 1 shell inlet"))
    s15 = Connection(HP_FWH_1, "out1", HP_FWH_valve_1, "in1")

    s16 = Connection(HP_FWH_2, "out2", RH_FWH, "in2",
                     label=state(32, "feedwater HP FWH 2 -> reheater drain FWH"))
    s38 = Connection(RH_FWH, "out2", feedwater_split, "in1",
                     label=state(33, "reheater drain FWH -> feedwater splitter", mark=True))

    s17 = Connection(HP_FWH_2, "out1", HP_FWH_valve_2, "in1")

    s39 = Connection(feedwater_split, "out1", steam_generator_1, "in1",
                     label=state(34, "feedwater -> steam generator 1", mark=True))
    s72 = Connection(feedwater_split, "out2", steam_generator_2, "in1",
                     label=state(35, "feedwater -> steam generator 2", mark=True))
    s73 = Connection(steam_generator_1, "out1", main_steam_merge, "in1",
                     label=state(36, "steam generator 1 -> main steam header", mark=True))
    s74 = Connection(steam_generator_2, "out1", main_steam_merge, "in2",
                     label=state(37, "steam generator 2 -> main steam header", mark=True))

    s0 = Connection(main_steam_merge, "out1", cc, "in1",
                    label=state(38, "main steam header -> cycle closer"))

    # Condenser sooling connections
    s1_1 = Connection(cwso, "out1", condenser, "in2",
                      label=state(46, "cooling water in"))
    s1_2 = Connection(condenser, "out2", cwsi, "in1",
                      label=state(47, "cooling water out"))

    condenser.set_attr(pr1=1, pr2=0.98)

    # Each steam generator carries its DCD rating of 1707 MWt, so the total NSSS heat
    # input is 3414 MWt and the main steam flow follows from the two duties. Only one
    # of the two shells may carry a pressure spec: both outlets are pinned to the main
    # steam header pressure by the merge, so a second pr equation would be redundant
    # with it and leave the Jacobian singular.
    steam_generator_1.set_attr(pr=pr_steam_generator, Q=steam_generator_duty)
    steam_generator_2.set_attr(Q=steam_generator_duty)

    
    super_heater.set_attr(pr=pr_solar_superheater)
    interstage_heater_0.set_attr(pr=pr_solar_reheater)

    # Isentropic efficiencies are the DCD-consistent values that land the shaft output
    # at 1200 MW: the wet LP stages run well below dry-expansion efficiency.
    HP_turbine.set_attr(
        eta_s1=eta_s_hp_turbine, eta_s2=eta_s_hp_turbine,
        eta_s3=eta_s_hp_turbine, eta_s4=eta_s_hp_turbine,
    )
    LP_turbine_1.set_attr(eta_s=eta_s_lp_turbine)
    LP_turbine_2.set_attr(eta_s1=eta_s_lp_turbine, eta_s2=eta_s_lp_turbine)
    LP_turbine_3.set_attr(eta_s1=eta_s_lp_turbine, eta_s2=eta_s_lp_turbine)

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

    LP_FWH_1.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)
    LP_FWH_2.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)
    LP_FWH_3.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)
    LP_FWH_4.set_attr(ttd_u=ttd_u_fwh, pr1=0.97, pr2=0.97)

    HP_pump.set_attr(eta_s=eta_s_feed_pump)

    # Condenser cooling connections
    s1_1.set_attr(T=T_cw_in, p=p_cw, fluid=cooling_fluid)
    s1_2.set_attr(T=T_cw_out)

    # Main steam, DCD Fig 10.1-1: 808 psia / 1197.6 BTU/lb. The flow follows from the
    # two steam generator duties, so only a start value is given here.
    s1.set_attr(p=p_main_steam, h=h_main_steam, m0=main_mass_flow, fluid=working_fluid)
    s1b.set_attr(m0=main_mass_flow * (1 - main_mass_flow_bleed), h0=2.786e6)  # main steam -> HP turbine
    s1c.set_attr(m0=main_mass_flow * main_mass_flow_bleed, h0=2.786e6)  # main steam bleed -> solar reheater / interstage 2

    # HP turbine outlets: pressures fall along the stage order out1 -> ... -> out4.
    # Extrastion masses are results of each heater's ttd_u. c13 sits at 2.0 MPa so
    # that Tsat = 485.5 K supports the DCD's 478 K feedwater point ahead of the
    # final heater, and s3 at 2.83 MPa (Tsat = 503.6 K) the 500.9 K SG inlet.
    s2_hp.set_attr(p=p_hp_exhaust, m0=1452, h0=2.540e6)
    s2.set_attr(m0=1323, h0=2.540e6)
    s2_da.set_attr(m0=129, h0=2.540e6)
    s2a.set_attr(m0=1280, h0=2.782e6)
    s2d.set_attr(m0=1280, h0=2.863e6)
    s2b.set_attr(T=T_lp_inlet, m0=1280, h0=2.950e6)
    s2b1.set_attr(m0=43, h0=2.950e6)
    s2b2.set_attr(m0=118, h0=2.950e6)
    s2b3.set_attr(m0=1119, h0=2.950e6)
    s2c.set_attr(m0=172, h0=7.87e5)
    s2c_da.set_attr(m0=172, h0=7.87e5)
    s30.set_attr(p=p_hp_bleed_1, m=83.07, h0=2.740e6)
    s3.set_attr(p=p_hp_bleed_2, m0=92, h0=2.690e6)
    s13.set_attr(p=p_hp_bleed_3, m0=200, h0=2.620e6)

    # Interstage heater drains.
    s31.set_attr(x=0, m0=66, h0=1.179e6)
    s32.set_attr(m0=66, h0=1.179e6)
    s33.set_attr(x=0, m0=60, h0=1.079e6)
    s34.set_attr(m0=126, h0=1.132e6)
    s35.set_attr(m0=126, h0=9.93e5)
    s36.set_attr(m0=126, h0=9.93e5)
    s37.set_attr(m0=218, h0=1.706e6)

    s40.set_attr(p=p_lp_bleed_1, m0=43, h0=2.775e6)
    s40b.set_attr(p=p_lp_bleed_4, m0=75, h0=2.770e6)
    s42.set_attr(p=p_lp_bleed_2, m0=43, h0=2.550e6)
    s45.set_attr(p=p_lp_bleed_3, m0=50, h0=2.490e6)

    s5.set_attr(p=p_condenser, m0=1069, h0=2.350e6)

    s8.set_attr(p=p_condensate, m0=1286, h0=1.81e5)
    s60.set_attr(m0=1286, h0=2.03e5)
    s61.set_attr(m0=1286, h0=3.09e5)
    s62.set_attr(m0=1286, h0=3.90e5)
    s9.set_attr(m0=1286, h0=5.27e5)
    s9d.set_attr(m0=1286, h0=5.27e5)
    s9a.set_attr(x=0, m0=main_mass_flow, h0=7.81e5)

    s10.set_attr(m0=main_mass_flow, h0=6.203e5)
    s11.set_attr(m0=main_mass_flow, h0=8.873e5)
    s16.set_attr(m0=main_mass_flow, h0=9.706e5)
    s38.set_attr(m0=main_mass_flow, h0=9.798e5)

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

    s18.set_attr(m0=306, h0=9.015e5)
    s19.set_attr(x=0, m0=43, h0=6.65e5)
    s20.set_attr(m0=43, h0=6.65e5)

    s63.set_attr(m0=118, h0=9.29e5)
    s64.set_attr(x=0, m0=118, h0=5.52e5)
    s65.set_attr(m0=118, h0=5.52e5)

    s66.set_attr(m0=794, h0=5.891e5)
    s67.set_attr(x=0, m0=794, h0=3.965e5)
    s68.set_attr(m0=794, h0=3.965e5)

    s69.set_attr(m0=884, h0=6.023e5)
    s70.set_attr(x=0, m0=884, h0=3.158e5)
    s71.set_attr(m0=884, h0=3.158e5)

    SteamCycle.add_conns(
        s1, s1a, s1b, s1c, s1d, s2_hp, s2, s2_da, s2a, s2b, s2b1, s2b2, s2b3,
        s2c, s2c_da, s2d, s3, s5,
        s6, s7, s8, s9, s9d, s9a, s10, s11, s12, s13, s14, s15,
        s16, s17, s18, s19, s20, s0, s1_1, s1_2,
        s30, s31, s32, s33, s34, s35, s36, s37, s38, s39,
        s40, s40b, s42, s45,
        s60, s61, s62, s63, s64, s65, s66, s67, s68, s69, s70, s71,
        s72, s73, s74
    )

    trim_results(OilLoop, SteamCycle)



    turbine_list = [HP_turbine, LP_turbine_1, LP_turbine_2, LP_turbine_3]
    pump_list = [condensate_pump, HP_pump]


    # ---------------------------------------------------------------------------
    # Design point check against Asfand et al. (2020), Tables 1 and 4
    # ---------------------------------------------------------------------------
    def solve_design_point():
        """Put the plant on its design duty: full field, no storage exchange."""
        Q_to_steam_design = solve_oil_loop(Q_design_thermal, 0.0, 0.0, oil_conns=[o3,o4,o6,o7,o8,o9],
                                           solar_field=solar_field,
                                           T_field_out=T_field_out,
                                           T_charge_out=T_cold_header,
                                           T_discharge_out=T_discharge_out,
                                           charge_hx_oil=charge_hx_oil,discharge_hx_oil=discharge_hx_oil,
                                           OilLoop=OilLoop,oil_sg=oil_side_sg)
        return solve_power_block(Q_to_steam_design, super_heater, interstage_heater_0,
                                 SteamCycle, turbine_list, pump_list,
                                 reheat_fraction=reheat_fraction,
                                 pr_heat_in=pr_solar_superheater,
                                 pr_reheater=pr_solar_reheater)

    P_turbine_design, P_pumps_design = solve_design_point()

    # ---------------------------------------------------------------------------
    # Annual simulation
    # ---------------------------------------------------------------------------
    day = (24 * day_number)
    eod = day + 24
    tick = 0
    hourly_rows = DNI_values[day:eod] if hourly else DNI_values[day + 11: day + 12]
    for hour_num, day_of_year, DNI, T_amb, solar_elevation in hourly_rows:
        progress_total = len(DNI_values[day:eod])
        progress = tick / progress_total


        T_amb_K = T_amb + 273.15

        Q_solar = Q_solar_field(
            hour_num=hour_num, DNI=DNI, T_amb_K=T_amb_K,
            collector_area=collector_area, optical_efficiency=optical_efficiency,
            T_htf_in=T_htf_in, mdot_htf=mdot_htf, htf=htf,
            day_of_year=day_of_year, solar_elevation_deg=solar_elevation,
        )
        print(f"DNI: {DNI}, Q Solar: {Q_solar}")
        solar_field.set_attr(Q=Q_solar)
        step = dispatch(Q_solar=Q_solar, Q_design=Q_design_thermal, tank=tank, dt=dt)

        # --- Oil loop side ---
        # The field carries only the heat the plant can actually use; the rest is
        # defocused, otherwise a full hot tank would push its surplus into the
        # power block.

        Q_to_steam = solve_oil_loop(Q_solar - step["Q_defocus"],
                                    step["Q_to_storage"], step["Q_from_storage"],
                                    oil_conns=[o3, o4, o6, o7, o8, o9],
                                    solar_field=solar_field,
                                    T_field_out=T_field_out,
                                    T_charge_out=T_cold_header,
                                    T_discharge_out=T_discharge_out,
                                    charge_hx_oil=charge_hx_oil,
                                    discharge_hx_oil=discharge_hx_oil,
                                    OilLoop=OilLoop, oil_sg=oil_side_sg)
        # --- Steam cycle side ---
        # Matched duty: exactly what the oil side gave up, the steam side
        # receives. This is the only coupling between the two networks.
        #
        # The two nuclear steam generators are always at rating, so the block never
        # shuts down with the field. When there is no solar heat the block is still
        # solved, just with zero duty on the solar superheater and interstage
        # heater, which is the unaugmented Rankine cycle.
        if step["Q_to_pb"] <= 0 or Q_to_steam <= Q_MIN_BRANCH:
            Q_to_steam = 0.0

        P_turbine, P_pumps = solve_power_block(Q_to_steam, super_heater, interstage_heater_0, SteamCycle, turbine_list,
                                               pump_list, reheat_fraction=reheat_fraction,
                                               pr_heat_in=pr_solar_superheater,
                                               pr_reheater=pr_solar_reheater)
        m_steam = s2.m.val

        step["day_of_year"] = day_of_year
        step["hour"] = hour_num
        step["DNI(K)"] = DNI
        step["T_amb(K)"] = T_amb
        step["Q_sg_oil"] = Q_to_steam
        step["m_oil_field"] = o3.m.val
        step["T_sg_oil_in"] = o10.T.val
        step["m_steam"] = m_steam
        step["P_turbine"] = P_turbine
        step["P_pumps"] = P_pumps + htf_pump.P.val
        step["P_net"] = P_turbine - step["P_pumps"]
        # Both steam generators are on rating, so the nuclear heat input is twice
        # steam_generator_duty, not once.
        step["efficiency"] = step["P_net"] / (step["Q_sg_oil"] + 2 * steam_generator_duty)
        try:
            step["solar_efficiency"] = (step["P_net"] - 2 * steam_generator_duty * step["efficiency"]) / Q_to_steam
        except ZeroDivisionError:
            step["solar_efficiency"] = float("nan")

        Q_nuclear = 2 * steam_generator_duty
        T_in = 273.15 + 324.7
        T_out = 273.15 + 281.835
        T_nuclear = (T_in - T_out) / math.log(T_in / T_out)
        step["ex_nuclear"] = Q_nuclear * (1 - (T_amb_K / T_nuclear))
        if step["Q_sg_oil"] > 0:
            step["ex_solar"] = step["Q_sg_oil"] * (1 - T_amb_K / step["T_sg_oil_in"])
        else:
            step["ex_solar"] = 0.0
        step["efficiency_II"] = step["P_net"] / (step["ex_nuclear"] + step["ex_solar"])
        log.append(step)

        tick += 1
        if not verbose:
            continue
        print("\n" * 5)
        print(f"Turbine power: {step["P_turbine"]}")
        print(f"Pump power: {step["P_pumps"]}")
        print(f"Efficiency: {step["efficiency"]}")

        print(Style.BRIGHT + Fore.MAGENTA +"""\n\n\n\n
                ###########################################################################################
                #                                                                                         #
                #                                Steam Cycle                                              #
                #                                                                                         #
                ###########################################################################################
                """)
        SteamCycle.print_results()
        print(Style.BRIGHT + Fore.MAGENTA +"""\n\n\n\n
                ###########################################################################################
                #                                                                                         #
                #                                Steam Cycle                                              #
                #                                                                                         #
                ###########################################################################################
                """)

        print(Style.BRIGHT + Fore.GREEN + """\n\n\n\n
                        ###########################################################################################
                        #                                                                                         #
                        #                                Oil loop                                                 #
                        #                                                                                         #
                        ###########################################################################################
                        """)
        OilLoop.print_results()
        print(Style.BRIGHT + Fore.GREEN + """\n\n\n\n
                        ###########################################################################################
                        #                                                                                         #
                        #                                Oil loop                                              #
                        #                                                                                         #
                        ###########################################################################################
                        """)


    results = pd.DataFrame(log)
    if results_csv is not None:
        results.to_csv(results_csv, index=False)

    # The hourly run leaves the networks wherever the last hour put them, so
    # anything wanting to inspect the plant itself gets it back on design first.
    if design_point_out is not None:
        solve_design_point()
        design_point_out.update({"steam": SteamCycle, "oil": OilLoop})

    return results


if __name__ == "__main__":
    results = solve_configuration1(hourly=False)
    # ---------------------------------------------------------------------------
    # Annual summary
    # ---------------------------------------------------------------------------
    hours = dt / 3600
    to_GWh = hours / 1e9
    Q_incident = (results["DNI(K)"] * collector_area).sum() * to_GWh
    operating = results["P_turbine"] > 0




