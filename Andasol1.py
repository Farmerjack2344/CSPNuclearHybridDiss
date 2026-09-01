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
    :return:
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

# The cold header is held at 28 bar so that after the field pressure drop the
# hot end still sits well above the ~10.6 bar vapour pressure of Therminol
# VP-1 at 393 C. A collector loop drops roughly 10 bar, which is what makes
# HTF circulation a MW-scale parasitic rather than a rounding error.
o1.set_attr(fluid=oil_fluid, p=28e5, T=T_oil_cold)

htf_pump.set_attr(eta_s=0.8)
solar_field.set_attr(pr=0.65)
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
    temperature="K", pressure="Pa", pressure_difference="Pa",
    enthalpy="J/kg", heat="W", power="W", mass_flow="kg/s",
)
SteamCycle.iterinfo = False

cycle_closer_steam = CycleCloser("Steam Cycle Closer")
steam_side_sg = SimpleHeatExchanger("Steam Generator (steam side)")
HP_turbine = SteamTurbine("HP Turbine")
hp_extraction = Splitter("HP exhaust extraction", num_out=2)
steam_side_reheater = SimpleHeatExchanger("Reheater")
LP_turbine_1 = SteamTurbine("LP Turbine (to extraction)")
lp_extraction = Splitter("LP extraction", num_out=2)
LP_turbine_2 = SteamTurbine("LP Turbine (to condenser)")
condenser = Condenser("Condenser")
condensate_pump = Pump("Condensate Pump")
deaerator = Merge("Deaerator", num_in=2)
booster_pump = Pump("Booster Pump")
hp_heater = Merge("HP Feed Water Heater", num_in=2)
feed_pump = Pump("Feed Water Pump")
cooling_water_in = Source("Cooling water in")
cooling_water_out = Sink("Cooling water out")

s1 = Connection(cycle_closer_steam, "out1", steam_side_sg, "in1", label="s1_closer_to_sg")
s2 = Connection(steam_side_sg, "out1", HP_turbine, "in1", label="s2_live_steam")
s3 = Connection(HP_turbine, "out1", hp_extraction, "in1", label="s3_hp_exhaust")
s4 = Connection(hp_extraction, "out1", steam_side_reheater, "in1", label="s4_to_reheater")
s5 = Connection(steam_side_reheater, "out1", LP_turbine_1, "in1", label="s5_reheated_steam")
s6 = Connection(LP_turbine_1, "out1", lp_extraction, "in1", label="s6_lp_extraction_point")
s7 = Connection(lp_extraction, "out1", LP_turbine_2, "in1", label="s7_to_lp_stage_2")
s8 = Connection(LP_turbine_2, "out1", condenser, "in1", label="s8_turbine_to_condenser")
s9 = Connection(condenser, "out1", condensate_pump, "in1", label="s9_condensate")
s10 = Connection(condensate_pump, "out1", deaerator, "in1", label="s10_condensate_to_dea")
s11 = Connection(lp_extraction, "out2", deaerator, "in2", label="s11_extraction_to_dea")
s12 = Connection(deaerator, "out1", booster_pump, "in1", label="s12_dea_outlet")
s13 = Connection(booster_pump, "out1", hp_heater, "in1", label="s13_to_hp_heater")
s14 = Connection(hp_extraction, "out2", hp_heater, "in2", label="s14_extraction_to_hp_heater")
s15 = Connection(hp_heater, "out1", feed_pump, "in1", label="s15_hp_heater_outlet")
s16 = Connection(feed_pump, "out1", cycle_closer_steam, "in1", label="s16_feed_water")
s17 = Connection(cooling_water_in, "out1", condenser, "in2", label="s17_cw_in")
s18 = Connection(condenser, "out2", cooling_water_out, "in1", label="s18_cw_out")

SteamCycle.add_conns(s1, s2, s3, s4, s5, s6, s7, s8, s9, s10,
                     s11, s12, s13, s14, s15, s16, s17, s18)


HP_turbine.set_attr(eta_s=0.848)
LP_turbine_1.set_attr(eta_s=0.916)
LP_turbine_2.set_attr(eta_s=0.916)
steam_side_sg.set_attr(pr=0.95)
condenser.set_attr(pr1=1, pr2=0.98)
condensate_pump.set_attr(eta_s=0.9)
booster_pump.set_attr(eta_s=0.9)
feed_pump.set_attr(eta_s=0.9)

# Live steam state is held fixed; the steam mass flow is what follows from the
# duty handed over by the oil loop, so it must NOT be fixed here as well.
s2.set_attr(fluid=rankine_cycle_fluid, p=105e5, T=654.15)
s3.set_attr(p=20.72e5)

# Reheat outlet temperature is free: the reheater duty is set per timestep from
# the oil-side duty split, and fixing both would over-determine the reheater.
s5.set_attr(p=18.29e5)
s6.set_attr(p=10.04e5)
s8.set_attr(p=0.065e5)

# Saturated liquid out of each open heater is what sizes its extraction: the
# solver picks the bled steam flow that exactly saturates the feed water.
s12.set_attr(x=0)
s15.set_attr(x=0)

s17.set_attr(fluid=cooling_fluid, m=2502, T=300.15, p=1.2e5)

# Fraction of the oil-side duty that goes to reheat rather than to the main
# steam generator. Asfand et al. split the HTF mass flow 90/10, which comes out
# as 21.479/140.437 of the duty because the reheater cools its HTF stream
# further than the steam generator does.
reheat_fraction = 21.479 / (118.958 + 21.479)

def solve_oil_loop(Q_field, Q_to_storage, Q_from_storage):
    """Solve the HTF loop for one timestep and return the duty it hands over."""
    set_duty_branch(o3, o4, solar_field, Q_field, T_oil_hot)
    set_duty_branch(o6, o7, charge_hx_oil, -Q_to_storage, T_oil_cold)
    set_duty_branch(o8, o9, discharge_hx_oil, Q_from_storage, T_oil_from_storage)
    OilLoop.solve("design")
    return max(-oil_side_sg.Q.val, 0.0)


def solve_power_block(Q_to_steam):
    """Solve the steam cycle against the duty the HTF loop gave up.

    Returns gross turbine output and the feed water pumping parasitics, both W.
    """
    steam_side_sg.set_attr(Q=Q_to_steam * (1 - reheat_fraction))
    steam_side_reheater.set_attr(Q=Q_to_steam * reheat_fraction)
    SteamCycle.solve("design")
    P_turbine = -(HP_turbine.P.val + LP_turbine_1.P.val + LP_turbine_2.P.val)
    P_pumps = condensate_pump.P.val + booster_pump.P.val + feed_pump.P.val
    return P_turbine, P_pumps


# ---------------------------------------------------------------------------
# Design point check against Asfand et al. (2020), Tables 1 and 4
# ---------------------------------------------------------------------------
Q_to_steam_design = solve_oil_loop(Q_design_thermal, 0.0, 0.0)
P_turbine_design, P_pumps_design = solve_power_block(Q_to_steam_design)

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
for hour_num, day_of_year, DNI, T_amb, solar_elevation in DNI_values:
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
        P_turbine, P_pumps = solve_power_block(Q_to_steam)
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