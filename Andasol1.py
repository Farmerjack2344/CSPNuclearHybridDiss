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
# NETWORK 1 -- Oil loop (Therminol VP-1)
# Solar field -> [charge / discharge storage branches] -> oil side of the
# steam generator -> back to field. This is the ONLY network the molten
# salt tank interacts with (indirectly, via Q= on the charge/discharge HXs).
# ---------------------------------------------------------------------------
OilLoop = Network()
OilLoop.units.set_defaults(
    temperature="K", pressure="Pa", pressure_difference="Pa",
    enthalpy="J/kg", heat="W", power="W", mass_flow="kg/s",
)

cycle_closer_oil = CycleCloser("Oil Cycle Closer")
solar_field = SimpleHeatExchanger("Solar Field")
splitter_field = Splitter("Post-field splitter", num_out=2)
charge_hx_oil = SimpleHeatExchanger("Charge HX (oil side)")
discharge_hx_oil = SimpleHeatExchanger("Discharge HX (oil side)")
merge_pb = Merge("Pre-steam-generator merge", num_in=2)
oil_side_sg = SimpleHeatExchanger("Steam Generator (oil side)")

o1 = Connection(cycle_closer_oil, "out1", solar_field, "in1", label="o1_closer_to_field")
o2 = Connection(solar_field, "out1", splitter_field, "in1", label="o2_field_to_splitter")
o3 = Connection(splitter_field, "out1", merge_pb, "in1", label="o3_splitter_to_merge_direct")
o4 = Connection(splitter_field, "out2", charge_hx_oil, "in1", label="o4_splitter_to_charge")
o5 = Connection(charge_hx_oil, "out1", discharge_hx_oil, "in1", label="o5_charge_to_discharge")
o6 = Connection(discharge_hx_oil, "out1", merge_pb, "in2", label="o6_discharge_to_merge")
o7 = Connection(merge_pb, "out1", oil_side_sg, "in1", label="o7_merge_to_sg")
o8 = Connection(oil_side_sg, "out1", cycle_closer_oil, "in1", label="o8_sg_to_closer")

OilLoop.add_conns(o1, o2, o3, o4, o5, o6, o7, o8)

# TODO (oil loop): fluid "INCOMP::TVP1" + mass flow guess on o1; pr= on
# solar_field/charge_hx_oil/discharge_hx_oil/oil_side_sg.
# splitter_field's split is controlled per-timestep via m= on o3/o4 below.


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

SteamCycle.add_conns(s1, s2, s3, s4, s6, s7, s8, s9)


HP_turbine.set_attr(eta_s=0.848)#,pr=0.197)
LP_turbine.set_attr(eta_s=0.916)
steam_side_reheater.set_attr(Q=21.479e3)
pump.set_attr(eta_s=0.9)

s2.set_attr(m=60.935, p=105e5, T=654.15)
s3.set_attr(p=20.72e5)

s4.set_attr(p=18.29e5,T=653.15)
s5.set_attr(p=0.065e5)

s8.set_attr(fluid=cooling_fluid, m=2502)

print("NOTE: component parameters (pr, eta_s, fluids) are not yet specified "
      "on either network -- neither will solve until those are added. "
      "See TODOs above.")


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


Q_design_thermal = 50e6
if Q_design_thermal is None:
    raise ValueError(
        "Q_design_thermal is not set. Define the power block's design "
        "thermal input (W) before running the time-marching loop."
    )


# ---------------------------------------------------------------------------
# Field parameters
# ---------------------------------------------------------------------------
collector_area = 0.5e6       # m^2
optical_efficiency = 0.75
T_htf_in = 273.15 + 285        # K
mdot_htf = 618.1              # kg/s

DNI_values = meteorolgoical_values()
dt = 3600  # s, hourly PVGIS data

log = []

for hour_num, DNI, T_amb in DNI_values:
    T_amb_K = T_amb + 273.15

    Q_solar = Q_solar_field(
        hour_num=hour_num, DNI=DNI, T_amb_K=T_amb_K,
        collector_area=collector_area, optical_efficiency=optical_efficiency,
        T_htf_in=T_htf_in, mdot_htf=mdot_htf, htf=htf,
    )

    step = dispatch(Q_solar=Q_solar, Q_design=Q_design_thermal, tank=tank, dt=dt)

    # --- Oil loop side ---
    charge_hx_oil.set_attr(Q=-step["Q_to_storage"] if step["Q_to_storage"] > 0 else 0)
    o4.set_attr(m=step["m_dot_charge"] if step["m_dot_charge"] > 0 else None)

    discharge_hx_oil.set_attr(Q=step["Q_from_storage"] if step["Q_from_storage"] > 0 else 0)
    o6.set_attr(m=step["m_dot_discharge"] if step["m_dot_discharge"] > 0 else None)

    oil_side_sg.set_attr(Q=-step["Q_to_pb"])  # heat leaving the oil side

    # --- Steam cycle side ---
    # Matched duty: exactly what the oil side gave up, the steam side
    # receives. This is the only coupling between the two networks.
    steam_side_sg.set_attr(Q=step["Q_to_pb"] * 0.9)
    steam_side_reheater.set_attr(Q=step["Q_to_pb"] * 0.1)
    # OilLoop.solve("design")     # TODO: uncomment once oil-loop params are set
    # SteamCycle.solve("design")  # TODO: uncomment once steam-cycle params are set

    step["hour"] = hour_num
    log.append(step)

results = pd.DataFrame(log)
print(results[["hour", "Q_solar", "mode", "Q_to_pb", "tank_soc"]])