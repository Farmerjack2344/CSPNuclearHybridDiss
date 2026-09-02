import pandas as pd
import math
import numpy as np

from tespy.networks import Network
from tespy.components import (SimpleHeatExchanger, Splitter, Merge, CycleCloser,
                              Source, Sink, Pump, SteamTurbine, Condenser, HeatExchanger, SolarCollector,
                                ParabolicTrough
                              )
from tespy.connections import Connection

from MoltenSaltTank import MoltenSaltTank, dispatch
from MoltenSalt import MoltenSalt
from tespy.networks import Network
from tespy.components import (
    CycleCloser, Pump, Condenser, Turbine,
    SimpleHeatExchanger, Source, Sink,
    HeatExchanger, Merge, Splitter, Valve,
    DropletSeparator
)

from MultistageTurbine import MultiStageExtractionTurbine

from tespy.connections import Connection

rankine_cycle_fluid = {"water": 1}
cooling_fluid = {"water": 1}
oil_fluid = {"INCOMP::TVP1": 1}


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

log = []

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

o1 = Connection(cycle_closer_oil, "out1", htf_pump, "in1", label="o1_closer_to_pump")
o2 = Connection(htf_pump, "out1", splitter_cold, "in1", label="o2_pump_to_cold_splitter")
o3 = Connection(splitter_cold, "out1", solar_field, "in1", label="o3_cold_to_field")
o4 = Connection(solar_field, "out1", splitter_hot, "in1", label="o4_field_to_hot_splitter")
o5 = Connection(splitter_hot, "out1", merge_hot, "in1", label="o5_field_direct_to_sg")
o6 = Connection(splitter_hot, "out2", charge_hx_oil, "in1", label="o6_hot_to_charge")
o7 = Connection(charge_hx_oil, "out1", merge_cold, "in2", label="o7_charge_to_cold_header")
o8 = Connection(splitter_cold, "out2", discharge_hx_oil, "in1", label="o8_cold_to_discharge")
o9 = Connection(discharge_hx_oil, "out1", merge_hot, "in2", label="o9_discharge_to_sg")
o10 = Connection(merge_hot, "out1", oil_side_sg, "in1", label="o10_merge_to_sg")
o11 = Connection(oil_side_sg, "out1", merge_cold, "in1", label="o11_sg_to_cold_header")
o12 = Connection(merge_cold, "out1", cycle_closer_oil, "in1", label="o12_cold_header_to_closer")

OilLoop.add_conns(o1, o2, o3, o4, o5, o6, o7, o8, o9, o10, o11, o12)

# The cold header is held at 28 bar so that after the field pressure drop the
# hot end still sits well above the ~10.6 bar vapour pressure of Therminol
# VP-1 at 393 C. A collector loop drops roughly 10 bar, which is what makes
# HTF circulation a MW-scale parasitic rather than a rounding error.
o1.set_attr(fluid=oil_fluid, p=28e5, T=T_oil_cold)

htf_pump.set_attr(eta_s=0.8)
solar_field.set_attr(A=collector_area,pr=0.65)
oil_side_sg.set_attr(pr=0.95)
# The storage HXs sit in parallel branches whose inlet and outlet pressures are
# both pinned by the splitters/merges, so their pr has to stay free: giving them
# one as well would close a pressure loop and over-determine the network.


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

cooling_fluid = {"water": 1}
working_fluid = {"water": 1}

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

# Two-stage interstage reheat. Heater 2 is the low-temperature stage (fed by the
# HP turbine stage-1 bleed), heater 1 the high-temperature stage (fed by main
# steam bled upstream of the HP turbine).
interstage_heater_0 = SimpleHeatExchanger("interstage heater 0 : Solar input")
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

s1 =  Connection(cc, "out1", super_heater, "in1")


s1a = Connection(super_heater, "out1", main_steam_split, "in1")
s1b = Connection(main_steam_split, "out1", HP_turbine, "in1")
s1c = Connection(main_steam_split, "out2", interstage_heater_0, "in1")
s1d = Connection(interstage_heater_0, "out1", interstage_heater_1, "in1")



# MultiStageExtrastionTurbine: out1 is after stage 1 (highest outlet P),
# outN is the exhaust (lowest P). Stage i+1 uses out{i}'s (p, h) as its inlet.
s2 = Connection(HP_turbine, "out4", moisture_separator, "in1")

# DropletSeparator: out1 is the saturated liquid drain, out2 the saturated vapour
# that goes on to the interstage reheaters and the LP turbine.
s2a = Connection(moisture_separator, "out2", interstage_heater_2, "in2")
s2d = Connection(interstage_heater_2, "out2", interstage_heater_1, "in2")
s2b = Connection(interstage_heater_1, "out2", LP_turbine_stg1, "in1")
s2c = Connection(moisture_separator, "out1", MSR_FWH, "in1")

# Interstage heater shell sides and their sascaded drains.
s30 = Connection(HP_turbine, "out1", interstage_heater_2, "in1")
s31 = Connection(interstage_heater_1, "out1", interstage_heater_1_valve, "in1")
s32 = Connection(interstage_heater_1_valve, "out1", interstage_drain_merge, "in1")
s33 = Connection(interstage_heater_2, "out1", interstage_drain_merge, "in2")
s34 = Connection(interstage_drain_merge, "out1", RH_FWH, "in1")
s35 = Connection(RH_FWH, "out1", RH_FWH_valve, "in1")
s36 = Connection(RH_FWH_valve, "out1", HP_FWH_2_shell_merge, "in2")

s3 = Connection(HP_turbine, "out2", HP_FWH_2_shell_merge, "in1")
s37 = Connection(HP_FWH_2_shell_merge, "out1", HP_FWH_2, "in1")

# LP expansion and the three LP bleeds.
s40 = Connection(LP_turbine_stg1, "out1", LP_FWH_2_merge, "in2")
s41 = Connection(LP_turbine_stg1, "out2", LP_bleed_split_1, "in1")
s42 = Connection(LP_bleed_split_1, "out1", LP_FWH_3_merge, "in2")
s43 = Connection(LP_bleed_split_1, "out2", LP_turbine_stg2, "in1")
s44 = Connection(LP_turbine_stg2, "out1", LP_bleed_split_2, "in1")
s45 = Connection(LP_bleed_split_2, "out1", LP_FWH_4_merge, "in2")
s46 = Connection(LP_bleed_split_2, "out2", LP_turbine_stg3, "in1")

s5 = Connection(LP_turbine_stg3, "out1", condenser_merge, "in1")

s6 = Connection(condenser_merge, "out1", condenser, "in1")

s7 = Connection(condenser, "out1", condensate_pump, "in1")

# Feedwater slimbs the LP train from the coldest heater upwards.
s8 = Connection(condensate_pump, "out1", LP_FWH_4, "in2")
s60 = Connection(LP_FWH_4, "out2", LP_FWH_3, "in2")
s61 = Connection(LP_FWH_3, "out2", LP_FWH_2, "in2")
s62 = Connection(LP_FWH_2, "out2", LP_FWH, "in2")
s9 = Connection(LP_FWH, "out2", MSR_FWH, "in2")
s9a = Connection(MSR_FWH, "out2", HP_pump, "in1")

# Cassaded LP shell drains: HP FWH 1 -> LP FWH 1 -> 2 -> 3 -> 4 -> sondenser.
s18 = Connection(HP_FWH_valve_1, "out1", LP_FWH, "in1")
s19 = Connection(LP_FWH, "out1", LP_FWH_valve, "in1")
s20 = Connection(LP_FWH_valve, "out1", LP_FWH_2_merge, "in1")
s63 = Connection(LP_FWH_2_merge, "out1", LP_FWH_2, "in1")
s64 = Connection(LP_FWH_2, "out1", LP_FWH_2_valve, "in1")
s65 = Connection(LP_FWH_2_valve, "out1", LP_FWH_3_merge, "in1")
s66 = Connection(LP_FWH_3_merge, "out1", LP_FWH_3, "in1")
s67 = Connection(LP_FWH_3, "out1", LP_FWH_3_valve, "in1")
s68 = Connection(LP_FWH_3_valve, "out1", LP_FWH_4_merge, "in1")
s69 = Connection(LP_FWH_4_merge, "out1", LP_FWH_4, "in1")
s70 = Connection(LP_FWH_4, "out1", LP_FWH_4_valve, "in1")
s71 = Connection(LP_FWH_4_valve, "out1", condenser_merge, "in2")

# The MSR drain leaves its cooler at ~420 K. Flashing it straight to the
# condenser threw away ~50 MW; cascading it into the top of the LP shell train
# instead lets that heat displace bleed steam.
s21 = Connection(MSR_FWH, "out1", MSR_FWH_valve, "in1")
s22 = Connection(MSR_FWH_valve, "out1", LP_FWH_2_merge, "in3")

s10 = Connection(HP_pump, "out1", HP_FWH_1, "in2")

s11 = Connection(HP_FWH_1, "out2", HP_FWH_2, "in2")

s12 = Connection(HP_FWH_valve_2, "out1", HP_FWH_M, "in1")
s13 = Connection(HP_turbine, "out3", HP_FWH_M, "in2")

s14 = Connection(HP_FWH_M, "out1", HP_FWH_1, "in1")
s15 = Connection(HP_FWH_1, "out1", HP_FWH_valve_1, "in1")

s16 = Connection(HP_FWH_2, "out2", RH_FWH, "in2")
s38 = Connection(RH_FWH, "out2", feedwater_split, "in1")

s17 = Connection(HP_FWH_2, "out1", HP_FWH_valve_2, "in1")

s39 = Connection(feedwater_split, "out1", steam_generator_1, "in1")
s72 = Connection(feedwater_split, "out2", steam_generator_2, "in1")
s73 = Connection(steam_generator_1, "out1", main_steam_merge, "in1")
s74 = Connection(steam_generator_2, "out1", main_steam_merge, "in2")

s0 = Connection(main_steam_merge, "out1", cc, "in1")

# Condenser sooling connections
s1_1 = Connection(cwso, "out1", condenser, "in2", label="11")
s1_2 = Connection(condenser, "out2", cwsi, "in1", label="12")

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
s1_1.set_attr(T=288.15, p=1.2e5, fluid=cooling_fluid)
s1_2.set_attr(T=300.15)

# Main steam, DCD Fig 10.1-1: 808 psia / 1197.6 BTU/lb. The flow follows from the
# two steam generator duties, so only a start value is given here.
s1.set_attr(p=5.571e6, h=2785.6e3, m0=1891, fluid=working_fluid)
s1b.set_attr(m0=1824, h0=2.786e6)  # main steam -> HP turbine
s1c.set_attr(m0=66, h0=2.786e6)  # main steam bleed -> interstage heater 1

# HP turbine outlets: pressures fall along the stage order out1 -> ... -> out4.
# Extrastion masses are results of each heater's ttd_u. c13 sits at 2.0 MPa so
# that Tsat = 485.5 K supports the DCD's 478 K feedwater point ahead of the
# final heater, and s3 at 2.83 MPa (Tsat = 503.6 K) the 500.9 K SG inlet.
s2.set_attr(p=1.133e6, m0=1388, h0=2.55e6)  # HP exhaust -> moisture separator
s2a.set_attr(m0=1216, h0=2.782e6)  # separated vapour -> interstage heater 2
s2d.set_attr(T=490, m0=1216, h0=2.863e6)  # first reheat stage outlet
s2b.set_attr(T=527.7, m0=1216, h0=2.950e6)  # reheated steam -> LP turbine
s2c.set_attr(m0=172, h0=7.87e5)  # separator drain -> MSR drain FWH
s30.set_attr(p=4.0e6, m0=60, h0=2.740e6)  # stage-1 bleed -> interstage heater 2
s3.set_attr(p=2.83e6, m0=92, h0=2.690e6)  # stage-2 extraction -> HP FWH 2
s13.set_attr(p=2.0e6, m0=284, h0=2.640e6)  # stage-3 extraction -> HP FWH merge

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

# LP bleed pressures, DCD LP extraction stages. Spreading them 0.289 / 0.086 /
# 0.0405 MPa puts Tsat at 405 / 369 / 349 K against condensate entering at
# 312 K, which is the ladder the DCD feedwater temperatures imply.
s40.set_attr(p=0.289e6, m0=104, h0=2.710e6)  # LP bleed 1 -> LP FWH 2
s41.set_attr(p=0.086e6, m0=1112, h0=2.535e6)  # LP stage 1 exhaust
s42.set_attr(m0=16, h0=2.535e6)  # LP bleed 2 -> LP FWH 3
s43.set_attr(m0=1096, h0=2.535e6)
s44.set_attr(p=0.0405e6, m0=1096, h0=2.435e6)  # LP stage 2 exhaust
s45.set_attr(m0=90, h0=2.435e6)  # LP bleed 3 -> LP FWH 4
s46.set_attr(m0=1006, h0=2.435e6)

# Condenser backpressure. The DCD's 5.66 psia is the last LP extraction, not
# condenser vacuum; the hotwell sits at 7 kPa, which is the 118.7 F / 86.7
# BTU/lb condensate point on the heat balance.
s5.set_attr(p=7000, m0=1006, h0=2.230e6)  # LP turbine exhaust

s8.set_attr(p=1.2e6, m0=1891, h0=1.65e5)

s60.set_attr(m0=1891, h0=2.988e5)
s61.set_attr(m0=1891, h0=3.797e5)
s62.set_attr(m0=1891, h0=5.352e5)
s9.set_attr(m0=1891, h0=5.979e5)
s9a.set_attr(m0=1891, h0=6.132e5)

s10.set_attr(m0=1891, h0=6.203e5)
s11.set_attr(m0=1891, h0=8.873e5)
s16.set_attr(m0=1891, h0=9.706e5)
s38.set_attr(m0=1891, h0=9.798e5)

# Even split between the two steam generators: fixing the enthalpy leaving shell 1
# at the main steam value forces the merge to hand shell 2 the same outlet state,
# so the two duties are carried by equal mass flows.
s39.set_attr(m0=945, h0=9.798e5)
s72.set_attr(m0=945, h0=9.798e5)
s73.set_attr(h=2785.6e3, m0=945)
s74.set_attr(m0=945, h0=2.786e6)

s14.set_attr(m0=502, h0=1.908e6)
s15.set_attr(x=0, m0=502, h0=9.015e5)  # HP FWH 1 drain leaves as saturated liquid
s17.set_attr(x=0, m0=218, h0=9.854e5)  # HP FWH 2 drain leaves as saturated liquid

# LP FWH 1 shell pressure. Tsat(0.6 MPa) = 432 K against feedwater at 400 K, so
# the throttled HP FWH 1 drain arrives wet (x ~ 0.11) and condenses out.
s18.set_attr(p=0.60e6, m0=502, h0=9.015e5)
s19.set_attr(x=0, m0=502, h0=6.652e5)
s20.set_attr(m0=502, h0=6.652e5)

s63.set_attr(m0=778, h0=9.293e5)
s64.set_attr(x=0, m0=778, h0=5.516e5)
s65.set_attr(m0=778, h0=5.516e5)

s66.set_attr(m0=794, h0=5.891e5)
s67.set_attr(x=0, m0=794, h0=3.965e5)
s68.set_attr(m0=794, h0=3.965e5)

s69.set_attr(m0=884, h0=6.023e5)
s70.set_attr(x=0, m0=884, h0=3.158e5)
s71.set_attr(m0=884, h0=3.158e5)

s21.set_attr(m0=172, h0=6.194e5)
s22.set_attr(m0=172, h0=6.194e5)

SteamCycle.add_conns(
    s1, s1b, s1c, s1d, s2, s2a, s2b, s2c, s2d, s3, s5,
    s6, s7, s8, s9, s9a, s10, s11, s12, s13, s14, s15,
    s16, s17, s18, s19, s20, s21, s22, s0, s1_1, s1_2,
    s30, s31, s32, s33, s34, s35, s36, s37, s38, s39,
    s40, s41, s42, s43, s44, s45, s46,
    s60, s61, s62, s63, s64, s65, s66, s67, s68, s69, s70, s71,
    s72, s73, s74
)





turbine_list = [HP_turbine, LP_turbine_stg1,LP_turbine_stg2, LP_turbine_stg3]
pump_list = [condensate_pump, HP_pump]
reheat_fraction = 21.479 / (118.958 + 21.479)


def solve_oil_loop(Q_field, Q_to_storage, Q_from_storage):
    """Solve the HTF loop for one timestep and return the duty it hands over."""
    set_duty_branch(o3, o4, solar_field, Q_field, T_oil_hot)
    set_duty_branch(o6, o7, charge_hx_oil, -Q_to_storage, T_oil_cold)
    set_duty_branch(o8, o9, discharge_hx_oil, Q_from_storage, T_oil_from_storage)
    OilLoop.solve("design")
    return max(-oil_side_sg.Q.val, 0.0)


def solve_power_block(Q_to_steam, heat_in_component, reheater, Steam_network, turbine_list, pump_list):
    """Solve the steam cycle against the duty the HTF loop gave up.

    Returns gross turbine output and the feed water pumping parasitics, both W.
    """
    heat_in_component.set_attr(Q=Q_to_steam * (1 - reheat_fraction))
    reheater.set_attr(Q=Q_to_steam * reheat_fraction)
    Steam_network.solve("design")
    P_turbine =  -1 * (sum([i.P.val for i in turbine_list]))
    P_pumps = -1 * (sum([i.P.val for i in pump_list]))
    return P_turbine, P_pumps


# ---------------------------------------------------------------------------
# Design point check against Asfand et al. (2020), Tables 1 and 4
# ---------------------------------------------------------------------------
Q_to_steam_design = solve_oil_loop(Q_design_thermal, 0.0, 0.0)
P_turbine_design, P_pumps_design = solve_power_block(Q_to_steam_design, super_heater, interstage_heater_0, SteamCycle, turbine_list, pump_list)

print("Design point vs. Asfand et al. (2020) Andasol-1 flowsheet")
print(f"{'quantity':<32}{'model':>12}{'paper':>12}")
for label, model_value, paper_value in [
    ("HTF mass flow, kg/s", o3.m.val, 618.1),
    ("HTF field outlet, C", o4.T.val - 273.15, 393.0),
    ("HTF return to field, C", o12.T.val - 273.15, 293.0),
    ("Boiler duty, MW", steam_side_sg.Q.val / 1e6, 118.958),
    ("Reheater duty, MW", steam_side_reheater.Q.val / 1e6, 21.479),
    ("Live steam flow, kg/s", s2.m.val, 60.935),
    ("HP turbine outlet, C", s3.T.val - 273.15, 214.2),
    ("LP turbine inlet, C", s5.T.val - 273.15, 380.0),
    ("Deaerator outlet, C", s12.T.val - 273.15, 180.1),
    ("Feed water to boiler, C", s16.T.val - 273.15, 250.4),
    ("Condenser steam flow, kg/s", s8.m.val, 38.902),
    ("Condenser duty, MW", -condenser.Q.val / 1e6, 83.597),
    ("Cooling water outlet, C", s18.T.val - 273.15, 35.0),
    ("Gross turbine output, MW", P_turbine_design / 1e6, 55.0),
]:
    print(f"{label:<32}{model_value:>12.2f}{paper_value:>12.2f}")
print()

# ---------------------------------------------------------------------------
# Annual simulation
# ---------------------------------------------------------------------------

for hour_num, day_of_year, DNI, T_amb, solar_elevation in DNI_values[202:232]:
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
        Q_solar - step["Q_defocus"], step["Q_to_storage"], step["Q_from_storage"]
    )

    # --- Steam cycle side ---
    # Matched duty: exactly what the oil side gave up, the steam side
    # receives. This is the only coupling between the two networks.
    if step["Q_to_pb"] > 0 and Q_to_steam > Q_MIN_BRANCH:
        P_turbine, P_pumps = solve_power_block(Q_to_steam, steam_side_sg,steam_side_reheater,SteamCycle,turbine_list,pump_list)
        m_steam = s2.m.val
    else:
        # The block is off: solving it would drive the steam mass flow to zero
        # and the network with it.
        Q_to_steam = 0.0
        P_turbine, P_pumps, m_steam = 0.0, 0.0, 0.0

    step["hour"] = hour_num
    step["day_of_year"] = day_of_year
    step["DNI"] = DNI
    step["T_amb"] = T_amb
    step["Q_sg_oil"] = Q_to_steam
    step["m_oil_field"] = o3.m.val
    step["T_sg_oil_in"] = o10.T.val
    step["m_steam"] = m_steam
    step["P_turbine"] = P_turbine
    step["P_net"] = P_turbine - P_pumps - htf_pump.P.val
    log.append(step)

results = pd.DataFrame(log)
results.to_csv("andasol1_hourly.csv", index=False)

# ---------------------------------------------------------------------------
# Annual summary
# ---------------------------------------------------------------------------
hours = dt / 3600
to_GWh = hours / 1e9
Q_incident = (results["DNI"] * collector_area).sum() * to_GWh
operating = results["P_turbine"] > 0

print("Annual results")
print(f"  DNI on the aperture          {Q_incident:8.1f} GWh")
print(f"  Collected by the field       {results['Q_solar'].sum() * to_GWh:8.1f} GWh")
print(f"  Defocused                    {results['Q_defocus'].sum() * to_GWh:8.1f} GWh")
print(f"  Delivered to the power block {results['Q_to_pb'].sum() * to_GWh:8.1f} GWh")
print(f"  Gross generation             {results['P_turbine'].sum() * to_GWh:8.1f} GWh")
print(f"  Net of pumping               {results['P_net'].sum() * to_GWh:8.1f} GWh")
print(f"  Operating hours              {operating.sum():8d} h")
print(f"  Equivalent full load hours   "
      f"{results['P_turbine'].sum() / P_turbine_design:8.0f} h")
print(f"  Gross capacity factor        "
      f"{results['P_turbine'].sum() / (P_turbine_design * len(results)):8.1%}")
print()
print("Hours by dispatch mode")
print(results["mode"].value_counts().to_string())

