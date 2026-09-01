import pandas as pd
import math
import numpy as np

from tespy.networks import Network
from tespy.components import (SimpleHeatExchanger, Splitter, Merge, CycleCloser,
                              Source, Sink, Pump, SteamTurbine, Condenser, HeatExchanger)
from tespy.connections import Connection

from MoltenSaltTank import MoltenSaltTank, dispatch
from MoltenSalt import MoltenSalt

rankine_cycle_fluid = {"water": 1}
cooling_fluid = {"water": 1}
oil_fluid = {"INCOMP::TVP1": 1}


# ---------------------------------------------------------------------------
# Solar field helper functions: to calculate thermal loss
# ---------------------------------------------------------------------------
def cos_theta(day_of_year, solar_hour):
    delta = np.radians(23.45 * np.sin(np.radians(360 * (284 + day_of_year) / 365)))
    omega = np.radians(15 * (solar_hour - 12))
    return np.sqrt(max(1 - np.cos(delta) ** 2 * np.sin(omega) ** 2, 0))


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

    sun_height_rad = np.radians(df["H_sun"])
    with np.errstate(divide="ignore", invalid="ignore"):
        df["DNI"] = np.where(df["H_sun"] > 0, df["Gb(i)"] / np.sin(sun_height_rad), 0.0)

    df["T_amb"] = df["T2m"]
    return list(df[["hour", "DNI", "T_amb"]].itertuples(index=False, name=None))


def Q_solar_field(hour_num, DNI, T_amb_K, collector_area, optical_efficiency,
                   T_htf_in, mdot_htf, htf, day_of_year=202):
    """

    :param hour_num: Hour after midnight
    :param DNI: Direct Normal Irraidiance
    :param T_amb_K: AMbient temperature in Kelvin
    :param collector_area: Area of the colelctor
    :param optical_efficiency:
    :param T_htf_in:
    :param mdot_htf:
    :param htf:
    :param day_of_year:
    :return:
    """
    Q_ideal = collector_area * DNI * optical_efficiency
    Q_real = Q_ideal
    cos = cos_theta(day_of_year, hour_num)

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
salt_cp_avg = htf.cp((T_hot_salt + T_cold_salt) / 2)

tank = MoltenSaltTank(
    cp_avg=salt_cp_avg,
    T_cold=T_cold_salt,
    T_hot=T_hot_salt,
    total_salt_mass=total_salt_mass,
    initial_hot_mass=0.0,  # cold start; set >0 to warm-start SoC
)

# ---------------------------------------------------------------------------
# Field parameters
# ---------------------------------------------------------------------------

Q_design_thermal = 50e6
collector_area = 0.5e6       # m^2
optical_efficiency = 0.75
T_htf_in = 273.15 + 285        # K
mdot_htf = 618.1              # kg/s

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
solar_field = SimpleHeatExchanger("Solar Field")
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

o1.set_attr(fluid=oil_fluid, p=16e5, T=T_oil_cold)

htf_pump.set_attr(eta_s=0.8)
solar_field.set_attr(pr=0.98)
oil_side_sg.set_attr(pr=0.97)
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
# ---------------------------------------------------------------------------
SteamCycle = Network()
SteamCycle.units.set_defaults(
    temperature="K", pressure="Pa", pressure_difference="Pa",
    enthalpy="J/kg", heat="W", power="W", mass_flow="kg/s",
)
SteamCycle.iterinfo = False

cycle_closer_steam = CycleCloser("Steam Cycle Closer")
steam_side_sg = SimpleHeatExchanger("Steam Generator (steam side)")
HP_turbine = SteamTurbine("Power block Turbine")
steam_side_reheater = SimpleHeatExchanger("Reheater")
LP_turbine = SteamTurbine("LP Turbine")
condenser = Condenser("Condenser")
pump = Pump("Power block Pump")
cooling_water_in = Source("Cooling water in")
cooling_water_out = Sink("Cooling water out")

s1 = Connection(cycle_closer_steam, "out1", steam_side_sg, "in1", label="s1_closer_to_sg")
s2 = Connection(steam_side_sg, "out1", HP_turbine, "in1", label="s2_sg_to_turbine")
s3 = Connection(HP_turbine, "out1", steam_side_reheater, "in1", label="s3_sg_to_reheater")
s4 = Connection(steam_side_reheater, "out1", LP_turbine, "in1", label="s4_sg_to_reheater")
s5 = Connection(LP_turbine, "out1", condenser, "in1", label="s3_turbine_to_condenser")
s6 = Connection(condenser, "out1", pump, "in1", label="s4_condenser_to_pump")
s7 = Connection(pump, "out1", cycle_closer_steam, "in1", label="s5_pump_to_closer")
s8 = Connection(cooling_water_in, "out1", condenser, "in2", label="s6_cw_in")
s9 = Connection(condenser, "out2", cooling_water_out, "in1", label="s7_cw_out")

SteamCycle.add_conns(s1, s2, s3, s4, s5, s6, s7, s8, s9)


HP_turbine.set_attr(eta_s=0.848)
LP_turbine.set_attr(eta_s=0.916)
steam_side_sg.set_attr(pr=0.95)
condenser.set_attr(pr1=1, pr2=0.98)
pump.set_attr(eta_s=0.9)

# Live steam state is held fixed; the steam mass flow is what follows from the
# duty handed over by the oil loop, so it must NOT be fixed here as well.
s2.set_attr(fluid=rankine_cycle_fluid, p=105e5, T=654.15)
s3.set_attr(p=20.72e5)

# Reheat outlet temperature is free: the reheater duty is set per timestep from
# the oil-side duty split, and fixing both would over-determine the reheater.
s4.set_attr(p=18.29e5)
s5.set_attr(p=0.065e5)

s8.set_attr(fluid=cooling_fluid, m=2502, T=293.15, p=1.2e5)

# Fraction of the oil-side duty that goes to reheat rather than to the main
# steam generator.
reheat_fraction = 0.1

for hour_num, DNI, T_amb in DNI_values:
    T_amb_K = T_amb + 273.15

    Q_solar = Q_solar_field(
        hour_num=hour_num, DNI=DNI, T_amb_K=T_amb_K,
        collector_area=collector_area, optical_efficiency=optical_efficiency,
        T_htf_in=T_htf_in, mdot_htf=mdot_htf, htf=htf,
    )
    step = dispatch(Q_solar=Q_solar, Q_design=Q_design_thermal, tank=tank, dt=dt)

    # --- Oil loop side ---
    # The field carries only the heat the plant can actually use; the rest is
    # defocused, otherwise a full hot tank would push its surplus into the
    # power block.
    set_duty_branch(o3, o4, solar_field, Q_solar - step["Q_defocus"], T_oil_hot)
    set_duty_branch(o6, o7, charge_hx_oil, -step["Q_to_storage"], T_oil_cold)
    set_duty_branch(o8, o9, discharge_hx_oil, step["Q_from_storage"], T_oil_from_storage)

    OilLoop.solve("design")

    # What the steam generator actually picks up once the field, the storage
    # branches and the pump work are balanced. Cross-check this against the
    # dispatch bookkeeping value Q_to_pb.
    Q_to_steam = max(-oil_side_sg.Q.val, 0.0)

    # --- Steam cycle side ---
    # Matched duty: exactly what the oil side gave up, the steam side
    # receives. This is the only coupling between the two networks.
    if Q_to_steam > Q_MIN_BRANCH:
        steam_side_sg.set_attr(Q=Q_to_steam * (1 - reheat_fraction))
        steam_side_reheater.set_attr(Q=Q_to_steam * reheat_fraction)
        SteamCycle.solve("design")
        P_gross = -(HP_turbine.P.val + LP_turbine.P.val + pump.P.val)
        m_steam = s2.m.val
    else:
        # Below this the power block is off. Solving it would drive the steam
        # mass flow to zero and the network with it.
        P_gross = 0.0
        m_steam = 0.0

    step["hour"] = hour_num
    step["Q_sg_oil"] = Q_to_steam
    step["m_oil_field"] = o3.m.val
    step["T_sg_oil_in"] = o10.T.val
    step["m_steam"] = m_steam
    step["P_gross"] = P_gross
    log.append(step)

results = pd.DataFrame(log)
print(results[["hour", "Q_solar", "mode", "Q_to_pb", "Q_sg_oil", "tank_soc", "P_gross"]])