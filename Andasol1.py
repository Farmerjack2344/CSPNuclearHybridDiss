import pandas as pd
import math
import numpy as np
from colorama import Fore, Style, init
init(autoreset=True)

from tespy.networks import Network
from tespy.components import (
    SimpleHeatExchanger, Splitter, Merge, CycleCloser,
    Source, Sink, Pump, Condenser, HeatExchanger, Valve,
    ParabolicTrough,
)
from tespy.connections import Connection

from MultistageTurbine import MultiStageExtractionTurbine
from MoltenSaltTank import MoltenSaltTank, dispatch
from MoltenSalt import MoltenSalt


def highlight(text):
    return Fore.GREEN + Style.BRIGHT + text + Style.RESET_ALL


def state(number, text, mark=False):
    return f"{number:02d} {highlight(text) if mark else text}"


# Siemens Andasol-1 flowsheet (Asfand et al. 2020, Table 4). T in C, p in bar,
# h in kJ/kg, m in kg/s. Duties in kW. A blank means the figure does not give
# that quantity.
SIEMENS_STREAMS = [
    ("Inlet of HP steam turbine",        381.0, 104.988, 3020.2, 60.9355),
    ("Outlet of HP steam turbine",       214.2,  20.772, 2728.1, 54.8800),
    ("Inlet of LP steam turbine",        380.0,  18.229, 3207.2, 49.9055),
    ("Outlet of LP steam turbine",        38.0,   0.0655, 2305.9, 38.9022),
    ("Outlet of condenser",               38.0,   0.0655,  159.3, 47.8055),
    ("Discharge of LP feed-water pump",   39.2,  13.00,   165.3, 47.8055),
    ("Outlet of LP feed-water heater 1",  73.9,  13.00,   310.6, 47.8055),
    ("Outlet of LP feed-water heater 2", 104.7,  13.00,   439.7, 47.8055),
    ("Outlet of LP feed-water heater 3", 144.7,  13.00,   609.7, 47.8055),
    ("Outlet of deaerator",              180.1,  10.04,   763.5, 61.5500),
    ("Discharge of HP feed-water pump",  182.5, 129.00,   780.8, 61.5500),
    ("Outlet of HP feed-water heater 4", 210.9, 129.00,   905.5, 61.5500),
    ("Outlet of HP feed-water heater 5", 250.4, 129.00,  1087.5, 61.5500),
    ("Cooling water at condenser inlet",  27.0,   None,    None,  2502.0),
    ("Cooling water at condenser outlet", 35.0,   None,    None,  2502.0),
]
SIEMENS_DUTIES = [
    ("Boiler heat duty (kWt)", 118958.0),
    ("Reheater heat duty (kWt)", 21479.0),
    ("Condenser heat duty (kWt)", 83597.0),
    ("Gross power (kWe)", 55000.0),
]


def _pct_change(model, reference):
    if reference is None or reference == 0:
        return None
    return 100.0 * (model - reference) / abs(reference)


def _siemens_cell(value):
    return "" if value is None else value


def export_andasol_siemens_comparison(stream_model, duty_model, path):
    """Write model vs Siemens flowsheet values with no sheet styling."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Connection Results"
    ws.append([
        "Stream/Variable",
        "T model (C)", "T Siemens (C)", "T deviation (%)",
        "p model (bar)", "p Siemens (bar)", "p deviation (%)",
        "h model (kJ/kg)", "h Siemens (kJ/kg)", "h deviation (%)",
        "m model (kg/s)", "m Siemens (kg/s)", "m deviation (%)",
    ])
    for name, T_ref, p_ref, h_ref, m_ref in SIEMENS_STREAMS:
        model = stream_model[name]
        T_m, p_m, h_m, m_m = model["T"], model["p"], model["h"], model["m"]
        ws.append([
            name,
            T_m, _siemens_cell(T_ref), _pct_change(T_m, T_ref),
            p_m, _siemens_cell(p_ref), _pct_change(p_m, p_ref),
            h_m, _siemens_cell(h_ref), _pct_change(h_m, h_ref),
            m_m, _siemens_cell(m_ref), _pct_change(m_m, m_ref),
        ])
    ws.append([])
    ws.append(["Duty", "Model (kW)", "Siemens (kW)", "Deviation (%)"])
    for name, ref in SIEMENS_DUTIES:
        model = duty_model[name]
        ws.append([name, model, ref, _pct_change(model, ref)])

    wb.save(path)
    print(f"Wrote Siemens comparison to {path}")

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
    df = pd.read_csv("Timeseries_37.320.csv", skiprows=11)
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
# ---------------------------------------------------------------------------


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
# ---------------------------------------------------------------------------
T_oil_cold = T_htf_in            # cold header / field inlet, K
T_oil_hot = 273.15 + 393         # field outlet, K (Therminol VP-1 upper limit)
T_oil_from_storage = T_hot_salt - 5.0  # oil leaving the discharge HX, K
M_MIN = 1.0                      # kg/s trickle flow kept in idle branches
Q_MIN_BRANCH = 1e5               # W below which a branch counts as idle


def set_duty_branch(m_conn, T_conn, component, Q, T_out):
    if abs(Q) > Q_MIN_BRANCH:
        component.set_attr(Q=Q)
        m_conn.set_attr(m=None)
        T_conn.set_attr(T=T_out)
    else:
        component.set_attr(Q=0)
        T_conn.set_attr(T=None)
        m_conn.set_attr(m=M_MIN)


def solve_andasol1(
        T_field_out=T_oil_hot,
        T_cold_header=T_oil_cold,
        T_discharge_out=T_oil_from_storage,
        p_cold_header=28e5,
        Q_design_thermal=Q_design_thermal,
        day_number=222,
        n_days=1,
        hourly=True,
        verbose=True,
        print_results=True,
        results_csv="ModelResults/andasol1_hourly.csv",
):
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


    o1.set_attr(fluid=oil_fluid, p=p_cold_header, T=T_cold_header)

    htf_pump.set_attr(eta_s=0.8)
    solar_field.set_attr(A=collector_area,pr=0.65)
    oil_side_sg.set_attr(pr=0.95)

    # ---------------------------------------------------------------------------
    # NETWORK 2 -- Steam Rankine cycle (power block)
    # ---------------------------------------------------------------------------
    SteamCycle = Network()
    SteamCycle.units.set_defaults(
        temperature="K", pressure="Pa", pressure_difference="Pa",
        enthalpy="J/kg", heat="W", power="W", mass_flow="kg/s",
    )
    SteamCycle.iterinfo = False

    cycle_closer_steam = CycleCloser("Steam Cycle Closer")
    steam_side_sg = SimpleHeatExchanger("Steam Generator (steam side)")
    HP_turbine = MultiStageExtractionTurbine("HP Turbine", num_stages=2)
    hp_exhaust_split = Splitter("HP exhaust splitter", num_out=2)
    steam_side_reheater = SimpleHeatExchanger("Reheater")
    LP_turbine = MultiStageExtractionTurbine("LP Turbine", num_stages=5)

    condenser_merge = Merge("condenser merge", num_in=2)
    condenser = Condenser("Condenser")
    condensate_pump = Pump("Condensate Pump")
    main_steam_split = Splitter("main steam leak-off splitter", num_out=2)
    gland_leak = Sink("gland steam leak-off")
    makeup_water = Source("makeup water")

    LP_FWH_1 = HeatExchanger("LP FWH 1")
    LP_FWH_1_merge = Merge("LP FWH 1 shell merge", num_in=2)
    LP_FWH_1_valve = Valve("LP FWH 1 drain valve")
    LP_FWH_2 = HeatExchanger("LP FWH 2")
    LP_FWH_2_merge = Merge("LP FWH 2 shell merge", num_in=2)
    LP_FWH_2_valve = Valve("LP FWH 2 drain valve")
    LP_FWH_3 = HeatExchanger("LP FWH 3")
    LP_FWH_3_valve = Valve("LP FWH 3 drain valve")
    lp_to_da_valve = Valve("LP FWH 3 to deaerator valve")

    deaerator = Merge("Deaerator", num_in=5)
    feed_pump = Pump("Feed Water Pump")
    HP_FWH_4 = HeatExchanger("HP FWH 4")
    HP_FWH_4_valve = Valve("HP FWH 4 drain valve")
    HP_FWH_5 = HeatExchanger("HP FWH 5")
    HP_FWH_5_valve = Valve("HP FWH 5 drain valve")

    cooling_water_in = Source("Cooling water in")
    cooling_water_out = Sink("Cooling water out")

    s1 = Connection(cycle_closer_steam, "out1", steam_side_sg, "in1",
                    label="s1 closer to SG")
    s_sg = Connection(steam_side_sg, "out1", main_steam_split, "in1",
                      label="SG outlet to leak-off splitter")
    s2 = Connection(main_steam_split, "out1", HP_turbine, "in1",
                    label="Inlet of HP steam turbine")
    s_leak = Connection(main_steam_split, "out2", gland_leak, "in1",
                        label="gland steam leak-off")
    s_makeup = Connection(makeup_water, "out1", deaerator, "in5",
                          label="makeup water to deaerator")
    s_hp_b5 = Connection(HP_turbine, "out1", HP_FWH_5, "in1",
                         label="HP extraction to FWH 5")
    s3 = Connection(HP_turbine, "out2", hp_exhaust_split, "in1",
                    label="Outlet of HP steam turbine")
    s4 = Connection(hp_exhaust_split, "out1", steam_side_reheater, "in1",
                    label="HP exhaust to reheater")
    s_hp_b4 = Connection(hp_exhaust_split, "out2", HP_FWH_4, "in1",
                         label="HP exhaust to FWH 4")
    s5 = Connection(steam_side_reheater, "out1", LP_turbine, "in1",
                    label="Inlet of LP steam turbine")
    s_da_stm = Connection(LP_turbine, "out1", deaerator, "in2",
                          label="LP extraction to deaerator")
    s_lp_b3 = Connection(LP_turbine, "out2", LP_FWH_3, "in1",
                         label="LP extraction to FWH 3")
    s_lp_b2 = Connection(LP_turbine, "out3", LP_FWH_2_merge, "in2",
                         label="LP extraction to FWH 2")
    s_lp_b1 = Connection(LP_turbine, "out4", LP_FWH_1_merge, "in2",
                         label="LP extraction to FWH 1")
    s8 = Connection(LP_turbine, "out5", condenser_merge, "in1",
                    label="Outlet of LP steam turbine")

    s_fwh3_d = Connection(LP_FWH_3, "out1", LP_FWH_3_valve, "in1")
    s_fwh3_dv = Connection(LP_FWH_3_valve, "out1", LP_FWH_2_merge, "in1")
    s_fwh2_shell = Connection(LP_FWH_2_merge, "out1", LP_FWH_2, "in1")
    s_fwh2_d = Connection(LP_FWH_2, "out1", LP_FWH_2_valve, "in1")
    s_fwh2_dv = Connection(LP_FWH_2_valve, "out1", LP_FWH_1_merge, "in1")
    s_fwh1_shell = Connection(LP_FWH_1_merge, "out1", LP_FWH_1, "in1")
    s_fwh1_d = Connection(LP_FWH_1, "out1", LP_FWH_1_valve, "in1")
    s_fwh1_dv = Connection(LP_FWH_1_valve, "out1", condenser_merge, "in2")

    s6 = Connection(condenser_merge, "out1", condenser, "in1")
    s9 = Connection(condenser, "out1", condensate_pump, "in1",
                    label="Outlet of condenser")
    s10 = Connection(condensate_pump, "out1", LP_FWH_1, "in2",
                     label="Discharge of LP feed-water pump")
    s_fwh1 = Connection(LP_FWH_1, "out2", LP_FWH_2, "in2",
                        label="Outlet of LP feed-water heater 1")
    s_fwh2 = Connection(LP_FWH_2, "out2", LP_FWH_3, "in2",
                        label="Outlet of LP feed-water heater 2")
    s_fwh3 = Connection(LP_FWH_3, "out2", lp_to_da_valve, "in1",
                        label="Outlet of LP feed-water heater 3")
    s_fwh3_da = Connection(lp_to_da_valve, "out1", deaerator, "in1")

    s12 = Connection(deaerator, "out1", feed_pump, "in1",
                     label="Outlet of deaerator")
    s13 = Connection(feed_pump, "out1", HP_FWH_4, "in2",
                     label="Discharge of HP feed-water pump")
    s_fwh4 = Connection(HP_FWH_4, "out2", HP_FWH_5, "in2",
                        label="Outlet of HP feed-water heater 4")
    s16 = Connection(HP_FWH_5, "out2", cycle_closer_steam, "in1",
                     label="Outlet of HP feed-water heater 5")
    s_fwh4_d = Connection(HP_FWH_4, "out1", HP_FWH_4_valve, "in1")
    s_fwh4_dv = Connection(HP_FWH_4_valve, "out1", deaerator, "in3")
    s_fwh5_d = Connection(HP_FWH_5, "out1", HP_FWH_5_valve, "in1")
    s_fwh5_dv = Connection(HP_FWH_5_valve, "out1", deaerator, "in4")

    s17 = Connection(cooling_water_in, "out1", condenser, "in2",
                     label="Cooling water at condenser inlet")
    s18 = Connection(condenser, "out2", cooling_water_out, "in1",
                     label="Cooling water at condenser outlet")

    SteamCycle.add_conns(
        s1, s_sg, s2, s_leak, s_makeup, s_hp_b5, s3, s4, s_hp_b4, s5,
        s_da_stm, s_lp_b3, s_lp_b2, s_lp_b1, s8,
        s_fwh3_d, s_fwh3_dv, s_fwh2_shell, s_fwh2_d, s_fwh2_dv,
        s_fwh1_shell, s_fwh1_d, s_fwh1_dv,
        s6, s9, s10, s_fwh1, s_fwh2, s_fwh3, s_fwh3_da,
        s12, s13, s_fwh4, s16, s_fwh4_d, s_fwh4_dv, s_fwh5_d, s_fwh5_dv,
        s17, s18,
    )

    # Siemens live-steam / reheat / condenser pressures. Closed-heater
    # extraction pressures are Tsat = T_fw + 3.4 K, the TTD implied by FWH 4
    # (Tsat at 20.772 bar is 214.3 C, feedwater leaves at 210.9 C).
    p_hp_in = 104.988e5
    p_hp_fwh5 = 42.377e5
    p_hp_exh = 20.772e5
    p_lp_in = 18.229e5
    p_da = 10.04e5
    p_lp_fwh3 = 4.524e5
    p_lp_fwh2 = 1.345e5
    p_lp_fwh1 = 0.425e5
    p_cond = 0.0655e5
    p_lp_fw = 13.00e5
    p_hp_fw = 129.00e5

    # Stage efficiencies from the Siemens HP and LP end states. The last
    # stage of each turbine is left free so the figure's exhaust enthalpy
    # can be imposed on that outlet.
    HP_turbine.set_attr(eta_s1=0.8628)
    LP_turbine.set_attr(
        eta_s1=0.8947, eta_s2=0.8947, eta_s3=0.8947, eta_s4=0.8947,
    )
    condenser.set_attr(pr1=1, pr2=0.98)
    # LP-pump eta is the value implied by 159.3 -> 165.3 kJ/kg on the figure.
    condensate_pump.set_attr(eta_s=0.217)
    feed_pump.set_attr(eta_s=0.773)
    for heater in (LP_FWH_1, LP_FWH_2, LP_FWH_3, HP_FWH_4, HP_FWH_5):
        heater.set_attr(pr1=1.0, pr2=1.0)

    M_LIVE_DESIGN = 60.9355
    M_FW_DESIGN = 61.5500
    M_LEAK_DESIGN = M_FW_DESIGN - M_LIVE_DESIGN
    s2.set_attr(fluid=rankine_cycle_fluid, p=p_hp_in, T=381.0 + 273.15,
                m=M_LIVE_DESIGN, h0=3.0202e6)
    s_leak.set_attr(m=M_LEAK_DESIGN)
    s_makeup.set_attr(fluid=rankine_cycle_fluid, T=38.0 + 273.15, m=M_LEAK_DESIGN)
    s_hp_b5.set_attr(p=p_hp_fwh5, m0=6.06)
    s3.set_attr(p=p_hp_exh, h=2.7281e6)
    s_hp_b4.set_attr(m0=4.97)
    s5.set_attr(p=p_lp_in, T=380.0 + 273.15, h0=3.2072e6)
    s_da_stm.set_attr(p=p_da, m0=2.7)
    s_lp_b3.set_attr(p=p_lp_fwh3, m0=4.0)
    s_lp_b2.set_attr(p=p_lp_fwh2, m0=2.5)
    s_lp_b1.set_attr(p=p_lp_fwh1, m0=2.2)
    s8.set_attr(p=p_cond, h=2.3059e6)

    s10.set_attr(p=p_lp_fw)
    s_fwh1.set_attr(T=73.9 + 273.15)
    s_fwh2.set_attr(T=104.7 + 273.15)
    s_fwh3.set_attr(T=144.7 + 273.15)
    s12.set_attr(x=0)
    s13.set_attr(p=p_hp_fw)
    s_fwh4.set_attr(T=210.9 + 273.15)
    s16.set_attr(T=250.4 + 273.15)

    s_fwh5_d.set_attr(x=0, m0=6.06)
    s_fwh4_d.set_attr(x=0, m0=4.97)
    s_fwh3_d.set_attr(x=0, m0=4.0)
    s_fwh2_d.set_attr(x=0, m0=6.5)
    s_fwh1_d.set_attr(x=0, m0=8.9)

    s17.set_attr(fluid=cooling_fluid, m=2502, T=27.0 + 273.15, p=1.2e5)

    def solve_oil_loop(Q_field, Q_to_storage, Q_from_storage):
        set_duty_branch(o3, o4, solar_field, Q_field, T_field_out)
        set_duty_branch(o6, o7, charge_hx_oil, -Q_to_storage, T_cold_header)
        set_duty_branch(o8, o9, discharge_hx_oil, Q_from_storage, T_discharge_out)
        OilLoop.solve("design")
        return max(-oil_side_sg.Q.val, 0.0)


    def solve_power_block(Q_to_steam):
        in_service = Q_to_steam > 0
        if not in_service:
            return 0.0, 0.0
        scale = Q_to_steam / Q_design_thermal
        s2.set_attr(m=M_LIVE_DESIGN * scale)
        s_leak.set_attr(m=M_LEAK_DESIGN * scale)
        s_makeup.set_attr(m=M_LEAK_DESIGN * scale)
        steam_side_sg.set_attr(Q=None)
        steam_side_reheater.set_attr(Q=None)
        SteamCycle.solve("design", max_iter=200)
        P_turbine = -(HP_turbine.P.val + LP_turbine.P.val)
        P_pumps = condensate_pump.P.val + feed_pump.P.val
        return P_turbine, P_pumps

    def solve_design_point():
        Q_to_steam_design = solve_oil_loop(Q_design_thermal, 0.0, 0.0)
        return solve_power_block(Q_to_steam_design)

    P_turbine_design, P_pumps_design = solve_design_point()
    tank.m_hot = tank.m_total
    tank.m_cold = 0.0

    start = max(24 * day_number - 1, 0)
    if hourly:
        hourly_rows = DNI_values[start:start + 24 * n_days]
    else:
        hourly_rows = DNI_values[start + 12:start + 13]



    for hour_num, day_of_year, DNI, T_amb, solar_elevation in hourly_rows:
        T_amb_K = T_amb + 273.15

        Q_solar = Q_solar_field(
            hour_num=hour_num, DNI=DNI, T_amb_K=T_amb_K,
            collector_area=collector_area, optical_efficiency=optical_efficiency,
            T_htf_in=T_htf_in, mdot_htf=mdot_htf, htf=htf,
            day_of_year=day_of_year, solar_elevation_deg=solar_elevation,
        )
        step = dispatch(Q_solar=Q_solar, Q_design=Q_design_thermal, tank=tank, dt=dt)

        Q_to_steam = solve_oil_loop(
            Q_solar - step["Q_defocus"], step["Q_to_storage"], step["Q_from_storage"]
        )

        if step["Q_to_pb"] <= 0 or Q_to_steam <= Q_MIN_BRANCH:
            Q_to_steam = 0.0

        P_turbine, P_pumps = solve_power_block(Q_to_steam)
        m_steam = s2.m.val if Q_to_steam > 0 else 0.0

        step["hour"] = hour_num
        step["day_of_year"] = day_of_year
        step["DNI"] = DNI
        step["T_amb"] = T_amb
        step["Q_solar"] = Q_solar
        step["Q_sg_oil"] = Q_to_steam
        step["m_oil_field"] = o3.m.val
        step["T_sg_oil_in"] = o10.T.val
        step["m_steam"] = m_steam
        step["P_turbine"] = P_turbine
        step["P_pumps"] = P_pumps + htf_pump.P.val
        step["P_net"] = P_turbine - step["P_pumps"]
        step["efficiency"] = step["P_net"] / Q_to_steam if Q_to_steam > 0 else float("nan")
        try:
            step["solar_efficiency"] = step["P_net"] / Q_solar
        except ZeroDivisionError:
            step["solar_efficiency"] = float("nan")
        step["ex_nuclear"] = 0.0
        if step["Q_sg_oil"] > 0:
            step["ex_solar"] = step["Q_sg_oil"] * (1 - T_amb_K / step["T_sg_oil_in"])
        else:
            step["ex_solar"] = 0.0
        try:
            step["efficiency_II"] = step["P_net"] / (step["ex_nuclear"] + step["ex_solar"])
        except ZeroDivisionError:
            step["efficiency_II"] = float("nan")
        log.append(step)

    results = pd.DataFrame(log)
    if results_csv is not None:
        results.to_csv(results_csv, index=False)

    if print_results:
        hours = dt / 3600
        to_GWh = hours / 1e9
        Q_incident = (results["DNI"] * collector_area).sum() * to_GWh
        operating = results["P_turbine"] > 0

        print(results["mode"].value_counts().to_string())
        solve_power_block(Q_design_thermal)
        SteamCycle.print_results()

    return results


if __name__ == "__main__":
    solve_andasol1()
