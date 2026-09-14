from envs.matlab_env.Lib import datetime
from envs.matlab_env.Lib.unittest import result
from matplotlib import pyplot, cm
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from multiprocessing import Pool, cpu_count
import os
from datetime import datetime

from Configuration_1 import solve_configuration1
from Configuration_2 import solve_configuration2, Q_design_thermal as Q_DESIGN_REF
from AP1000V5 import solve_ap1000
from Andasol1 import solve_andasol1
from CoolProp.CoolProp import PropsSI



def get_month(day_number, year=2026):
    date = datetime.strptime(f"{year}-{day_number}", "%Y-%j")
    return date.strftime("%B")

def percentage(num_list):

    return [x * 100 for x in num_list]

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

#-----------------------------------------------------------------------#
#
#Config 1 Study
#
#-----------------------------------------------------------------------#
def plotting_mass_flow_rate():
    #2D oil and working fluid
    pass




#-----------------------------------------------------------------------#
#
#Config 2 Study
#
#-----------------------------------------------------------------------#

#Plot :
#   Bar graphs of working fluids
#   p_nuclear condenser
#   p_evaporatpr_secondary
#   reheat fraction
#   T_field_out
#   p_condenser_secondary : gonna be interesting

def plotting_fluids_2():
    list_of_fluids = [
        "ISOPENTANE",
        "ISOBUTANE",
        "CYCLOPENTANE",
        "HEXANE",
        "TOLUENE",
        "HEXAMETHYLDISILOXANE",
        "R1233ZDE",
        "R245FA",
    ]

    fluids = [{x: 1} for x in list_of_fluids]



    labels = [
        name.lower()
        for name in list_of_fluids
    ]

    T_cond = PropsSI("T", "P", 1.9e5, "Q", 0, "R245fa")
    T_evap = PropsSI("T", "P", 10.0e5, "Q", 0, "R245fa")
    p_hp_frac = np.log(4.5e5 / 1.9e5) / np.log(10.0e5 / 1.9e5)

    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for fluid in fluids:
        fluid_name = next(iter(fluid))
        try:
            T_evap_fluid = min(T_evap, 0.95 * PropsSI("Tcrit", fluid_name))

            p_condenser = PropsSI("P", "T", T_cond, "Q", 0, fluid_name)
            p_evaporator = PropsSI("P", "T", T_evap_fluid, "Q", 0, fluid_name)
            p_hp_exhaust = p_condenser * (p_evaporator / p_condenser) ** p_hp_frac
            results = solve_configuration2(secondary_fluid=fluid, p_evaporator_secondary=p_evaporator,
                                           p_hp_exhaust_secondary=p_hp_exhaust, p_condenser_secondary=p_condenser,
                                           hourly=False, print_results=False)
            power_values.append(results["P_net"])
            efficiency_values.append(results["efficiency"])
            solar_efficiency_values.append(results["solar_efficiency"])
            exergy_efficiency_values.append(results["efficiency_II"])
        except:
            power_values.append(1)
            efficiency_values.append(1)
            solar_efficiency_values.append(1)
            exergy_efficiency_values.append(1)

    fig, ax = pyplot.subplots(2, 2, figsize=(20, 20))
    ax[0, 0].bar(labels, power_values)
    ax[0, 0].set_ylabel("Power (W)")
    ax[0, 0].set_xlabel("Fluid")
    ax[0, 0].set_title("Power Output by Working Fluids")

    ax[0, 1].bar(labels, percentage(efficiency_values))
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Fluid")
    ax[0, 1].set_title("Efficiency by Working Fluids")

    ax[1, 1].bar(labels, percentage(solar_efficiency_values))
    ax[1, 1].set_ylabel("Efficiency (%)")
    ax[1, 1].set_xlabel("Fluid")
    ax[1, 1].set_title("Solar Efficiency by Working Fluids")

    ax[1, 0].bar(labels, percentage(exergy_efficiency_values))
    ax[1, 0].set_ylabel("Exergy (%)")
    ax[1, 0].set_xlabel("Fluid")
    ax[1, 0].set_title("Exergy by Working Fluids")

    for axis in ax.flat:
        axis.grid(True, axis="y", alpha=0.3)
        axis.tick_params(axis="x", labelrotation=20)

    Title = "Effect of ORC Working Fluid on System Performance"
    fig.suptitle(Title, fontsize=16, fontweight="bold")
    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches="tight")
    pyplot.show()

def plotting_p_nuclear_condenser_2():
    """
    LP turbine stage 3 to condenser merge
    :return:
    """
    pressure_values = np.linspace(0.85e5, 1.15e5, 50)
    #There is something stoppping from dropping pressure
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for pressure in pressure_values:
        results = solve_configuration2(p_nuclear_condenser=pressure, hourly=False, print_results=False)
        power_values.append(results["P_net"])
        efficiency_values.append(results["efficiency"])
        solar_efficiency_values.append(results["solar_efficiency"])
        exergy_efficiency_values.append(results["efficiency_II"])

    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))
    # Power plot
    ax[0, 0].plot([x / 1000 for x in pressure_values], power_values,linewidth=2)
    ax[0, 0].set_ylabel("Power (W)")
    ax[0, 0].set_xlabel("Pressure (kPa)")
    ax[0,0].set_title("Power Output Vs. LP Turbine Outlet Pressure", fontsize=13)


    # Efficiency Plot
    ax[0, 1].plot([x / 1000 for x in pressure_values], percentage(efficiency_values),linewidth=2)
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Pressure (kPa)")
    ax[0, 1].set_title("Efficiency Vs. LP Turbine Outlet Pressure", fontsize=13)

    # Solar Efficiency Plot
    ax[1, 1].plot([x / 1000 for x in pressure_values], percentage(solar_efficiency_values),linewidth=2)
    ax[1, 1].set_ylabel("Efficiency (%)")
    ax[1, 1].set_xlabel("Pressure (kPa)")
    ax[1, 1].set_title("Solar Efficiency Vs. LP Turbine Outlet Pressure", fontsize=13)

    # Exergy Efficiency Plot
    ax[1, 0].plot([x / 1000 for x in pressure_values], percentage(exergy_efficiency_values),linewidth=2)
    ax[1, 0].set_ylabel("Exergy (%)")
    ax[1, 0].set_xlabel("Pressure (kPa)")
    ax[1, 0].set_title("Exergy Vs. LP Turbine Outlet Pressure", fontsize=13)

    ax[0, 0].grid(True)
    ax[0, 1].grid(True)
    ax[1, 0].grid(True)
    ax[1, 1].grid(True,alpha=0.3)

    Title = "Effect of LP Turbine Outlet Pressure on System Performance"
    fig.suptitle(
        Title,
        fontsize=16,
        fontweight="bold"
    )


    pyplot.tight_layout()
    pyplot.show()
    pyplot.savefig(fr"ModelResults\{Title}",dpi=150,bbox_inches='tight')

def plotting_evaporator_secondary_2():
    """
    p_evaporator_secondary is nulcear condenser out to ORC superheater in
    """
    pressure_values = np.linspace(6e5, 1.1e6, 70)
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for pressure in pressure_values:
        results = solve_configuration2(p_nuclear_condenser=0.90e5, p_evaporator_secondary=pressure, hourly=False,
                                       print_results=False)
        power_values.append(results["P_net"])
        efficiency_values.append(results["efficiency"])
        solar_efficiency_values.append(results["solar_efficiency"])
        exergy_efficiency_values.append(results["efficiency_II"])

    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))
    # Power plot
    ax[0, 0].plot([x / 1000 for x in pressure_values], power_values, linewidth=2)
    ax[0, 0].set_ylabel("Power (W)")
    ax[0, 0].set_xlabel("Pressure (Pa)")
    ax[0, 0].set_title("Power Output Vs. ORC Superheater inlet", fontsize=13)

    # Efficiency Plot
    ax[0, 1].plot([x / 1000 for x in pressure_values], percentage(efficiency_values), linewidth=2)
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Pressure (Pa)")
    ax[0, 1].set_title("Efficiency Vs.ORC Superheater inlet", fontsize=13)

    # Solar Efficiency Plot
    ax[1, 1].plot([x / 1000 for x in pressure_values], percentage(solar_efficiency_values), linewidth=2)
    ax[1, 1].set_ylabel("Efficiency (%)")
    ax[1, 1].set_xlabel("Pressure (Pa)")
    ax[1, 1].set_title("Solar Efficiency Vs. ORC Superheater inlet", fontsize=13)

    # Exergy Efficiency Plot
    ax[1, 0].plot([x / 1000 for x in pressure_values], percentage(exergy_efficiency_values), linewidth=2)
    ax[1, 0].set_ylabel("Exergy (%)")
    ax[1, 0].set_xlabel("Pressure (Pa)")
    ax[1, 0].set_title("Exergy Vs. ORC Superheater inlet", fontsize=13)

    ax[0, 0].grid(True)
    ax[0, 1].grid(True)
    ax[1, 0].grid(True)
    ax[1, 1].grid(True, alpha=0.3)

    fig.suptitle(
        "Effect of ORC Evaporator on System Performance",
        fontsize=16,
        fontweight="bold"
    )

    pyplot.tight_layout()
    pyplot.show()

def plotting_reheat_fraction_2():
    reheat_fraction_values = np.linspace(0.05, 0.5, 70)
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for reheat_fraction in reheat_fraction_values:
        results = solve_configuration2(reheat_fraction=reheat_fraction, hourly=False, print_results=False)
        power_values.append(results["P_net"])
        efficiency_values.append(results["efficiency"])
        solar_efficiency_values.append(results["solar_efficiency"])
        exergy_efficiency_values.append(results["efficiency_II"])

    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))
    # Power plot
    ax[0, 0].plot([x / 1000 for x in reheat_fraction_values], power_values, linewidth=2)
    ax[0, 0].set_ylabel("Power (W)")
    ax[0, 0].set_xlabel("Pressure (Pa)")
    ax[0, 0].set_title("Power Output Vs. Oil Reheat Fraction", fontsize=13)

    # Efficiency Plot
    ax[0, 1].plot([x / 1000 for x in reheat_fraction_values], percentage(efficiency_values), linewidth=2)
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Pressure (Pa)")
    ax[0, 1].set_title("Efficiency Vs. Oil Reheat Fraction", fontsize=13)

    # Solar Efficiency Plot
    ax[1, 1].plot([x / 1000 for x in reheat_fraction_values], percentage(solar_efficiency_values), linewidth=2)
    ax[1, 1].set_ylabel("Efficiency (%)")
    ax[1, 1].set_xlabel("Pressure (Pa)")
    ax[1, 1].set_title("Solar Efficiency Vs. Oil Reheat Fraction", fontsize=13)

    # Exergy Efficiency Plot
    ax[1, 0].plot([x / 1000 for x in reheat_fraction_values], percentage(exergy_efficiency_values), linewidth=2)
    ax[1, 0].set_ylabel("Exergy (%)")
    ax[1, 0].set_xlabel("Pressure (Pa)")
    ax[1, 0].set_title("Exergy Vs. Oil Reheat Fraction", fontsize=13)

    ax[0, 0].grid(True)
    ax[0, 1].grid(True)
    ax[1, 0].grid(True)
    ax[1, 1].grid(True, alpha=0.3)

    fig.suptitle(
        "Effect of Oil Reheat Fraction  on System Performance",
        fontsize=16,
        fontweight="bold"
    )

    pyplot.tight_layout()
    pyplot.show()


def _solve_single_point_pressure(args):
    """Worker function — must be top-level (picklable) for multiprocessing."""
    HP_pressure, LP_pressure = args
    results = solve_configuration2(p_nuclear_condenser=HP_pressure, p_evaporator_secondary=LP_pressure, hourly=False,
                               print_results=False)
    return (
        results["P_net"],
        results["efficiency"],
        results["solar_efficiency"],
        results["efficiency_II"],
    )

def plotting_HP_LP_Turbine_outlets_2():
    data_points = 10
    p_nuclear_condenser_values = np.linspace(0.85e5, 1.15e5, data_points)
    p_evaporator_secondary_values = np.linspace(6e5, 1.1e6, data_points)

    #HP_grid -> p_nuclear_condenser_values
    #LP_grid -> p_evaporaor_secondary_values
    LP_grid, HP_grid = np.meshgrid(p_evaporator_secondary_values, p_nuclear_condenser_values)
    grid_points = list(zip(HP_grid.ravel(), LP_grid.ravel()))

    with Pool(processes=max(cpu_count() - 1, 1)) as pool:
        raw_results = pool.map(_solve_single_point_pressure, grid_points)

    shape = HP_grid.shape
    power_values = np.array([r[0] for r in raw_results], dtype=float).reshape(shape)
    efficiency_values = np.array([r[1] for r in raw_results], dtype=float).reshape(shape)
    solar_efficiency_values = np.array([r[2] for r in raw_results], dtype=float).reshape(shape)
    exergy_efficiency_values = np.array([r[3] for r in raw_results], dtype=float).reshape(shape)

    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))

    power_plot = ax[0, 0].pcolormesh(
        LP_grid, HP_grid, power_values, cmap=cm.viridis, shading="auto")
    ax[0, 0].set_ylabel("Nuclear Condenser Back Pressure(Pa)")
    ax[0, 0].set_xlabel("ORC Superheater Inlet (Pa)")
    ax[0, 0].set_title("Power Output Vs. Secondary LP and HP Turbine Outlet Pressure", fontsize=13)
    cbar_1 = pyplot.colorbar(power_plot, ax=ax[0, 0])
    cbar_1.set_label("Power (W)")

    efficiency_plot = ax[0, 1].pcolormesh(
        LP_grid, HP_grid, np.multiply(efficiency_values, 100), cmap=cm.viridis, shading="auto")
    ax[0, 1].set_ylabel("Nuclear Condenser Back Pressure(Pa)")
    ax[0, 1].set_xlabel("ORC Superheater Inlet (Pa)")
    ax[0, 1].set_title("Efficiency Vs. Secondary LP and HP Turbine Outlet Pressure", fontsize=13)
    cbar_2 = pyplot.colorbar(efficiency_plot, ax=ax[0, 1])
    cbar_2.set_label("Efficiency (%)")

    solar_efficiency_plot = ax[1, 1].pcolormesh(
        LP_grid, HP_grid, np.multiply(solar_efficiency_values, 100), cmap=cm.viridis, shading="auto")
    ax[1, 1].set_ylabel("Nuclear Condenser Back Pressure(Pa)")
    ax[1, 1].set_xlabel("ORC Superheater Inlet (Pa)")
    ax[1, 1].set_title("Solar Efficiency Vs. Secondary LP and HP Turbine Outlet Pressure", fontsize=13)
    cbar_3 = pyplot.colorbar(solar_efficiency_plot, ax=ax[1, 1])
    cbar_3.set_label("Solar Efficiency (%)")

    exergy_plot = ax[1, 0].pcolormesh(
        LP_grid, HP_grid, np.multiply(exergy_efficiency_values, 100), cmap=cm.viridis, shading="auto")
    ax[1, 0].set_ylabel("Nuclear Condenser Back Pressure(Pa)")
    ax[1, 0].set_xlabel("ORC Superheater Inlet (Pa)")
    ax[1, 0].set_title("Exergy Vs. Secondary LP and HP Turbine Outlet Pressure", fontsize=13)
    cbar_4 = pyplot.colorbar(exergy_plot, ax=ax[1, 0])
    cbar_4.set_label("Exergy (%)")

    ax[0, 0].grid(True)
    ax[0, 1].grid(True)
    ax[1, 0].grid(True)
    ax[1, 1].grid(True, alpha=0.3)

    Title = "Effect of Nuclear Condenser Back Pressure and ORC Superheater Inlet Pressure on System Performance"
    fig.suptitle(Title, fontsize=16, fontweight="bold")

    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches='tight')  # save BEFORE show
    pyplot.show()




def _solve_q_design_month(args):
    """Worker: one Q_design over n_days of hourly weather. Must stay top-level for Windows multiprocessing."""
    Q_design, n_days, start_day, cache_path = args
    expected_hours = 24 * n_days
    if os.path.isfile(cache_path):
        cached = pd.read_csv(cache_path)
        if len(cached) == expected_hours:
            return Q_design, cached

    results = solve_configuration2(Q_design_thermal=Q_design, day_number=start_day, n_days=n_days, verbose=False,
                                   results_csv=cache_path, hourly=True, print_results=False)
    return Q_design, results


def plotting_Q_design_thermal(n_days=30,start_day=212,n_points=10,q_frac_min=0.40,q_frac_max=1.00,use_cache=True,):
    """Month-long Q_design sweep for the solar section (Configuration 2).

    Method
    ------
    Overlaying 10 raw 720-hour traces is unreadable, so each Q_design is compared——
    at two levels that share the same weather window:

    1. Monthly energy-weighted KPIs vs Q_design (the parametric result).
       Totals, not hourly averages, so shutdown hours cannot inflate efficiency.
    2. Fluctuation shape, held on a common time axis:
       - mean diurnal P_net and tank SoC (hour-of-day averaged over the month)
       - box plot of daily net energy (day-to-day spread at each Q_design)
       - stacked dispatch-mode hours (direct test of the "more active hours" claim)



    Results are cached under ModelResults/q_design_study/ so replotting does not
    rerun TESPy. Drop those CSVs, or set use_cache=False, to force a new sweep.
    """
    nuclear_heat_input = 2 * 1707e6
    dispatch_modes = [
        "charging",
        "direct_plus_discharge",
        "direct_partial",
        "charging_only",
        "discharging",
        "shutdown",
    ]

    def cache_path_for(cache_dir, Q_design):
        return os.path.join(cache_dir, f"qdesign_{Q_design / 1e6:.1f}MW.csv")

    def numeric(series):
        return pd.to_numeric(series, errors="coerce")

    def summarise_month(df, Q_design):
        """Energy-weighted monthly KPIs. Do not arithmetic-mean hourly efficiency."""
        P_net = numeric(df["P_net"])
        Q_sg = numeric(df["Q_sg_oil"])
        Q_to_pb = numeric(df["Q_to_pb"])
        Q_defocus = numeric(df["Q_defocus"])
        Q_solar = numeric(df["Q_solar"])
        eta_solar = numeric(df["solar_efficiency"])
        soc = numeric(df["tank_soc"])
        Q_in = Q_sg + nuclear_heat_input

        active = Q_to_pb > 0
        solar_on = Q_sg > 0
        hours_to_MWh = 1e-6

        work = df.copy()
        work["P_net"] = P_net
        work["tank_soc"] = soc
        daily_energy = work.groupby("day_of_year")["P_net"].sum() * hours_to_MWh
        diurnal_P = work.groupby("hour")["P_net"].mean()
        diurnal_soc = work.groupby("hour")["tank_soc"].mean()

        P_active = P_net[active]
        cov = float(P_active.std() / P_active.mean()) if P_active.mean() else float("nan")

        eta_s_num = (eta_solar[solar_on] * Q_sg[solar_on]).sum()
        eta_s_den = Q_sg[solar_on].sum()

        if "ex_nuclear" in df.columns and "ex_solar" in df.columns:
            ex_in = numeric(df["ex_nuclear"]) + numeric(df["ex_solar"])
            eta_II = float(P_net.sum() / ex_in.sum()) if ex_in.sum() else float("nan")
        elif "efficiency_II" in df.columns:
            eta_II = float(numeric(df["efficiency_II"]).mean())
        else:
            eta_II = float("nan")

        mode_hours = (
            df["mode"].value_counts().reindex(dispatch_modes, fill_value=0).astype(int)
            if "mode" in df.columns else pd.Series(0, index=dispatch_modes)
        )

        return {
            "Q_design": Q_design,
            "n_hours": len(df),
            "E_net_MWh": float(P_net.sum() * hours_to_MWh),
            "eta_I": float(P_net.sum() / Q_in.sum()) if Q_in.sum() else float("nan"),
            "eta_solar": float(eta_s_num / eta_s_den) if eta_s_den else float("nan"),
            "eta_II": eta_II,
            "active_hours": int(active.sum()),
            "capacity_factor": float(Q_to_pb.mean() / Q_design) if Q_design else float("nan"),
            "defocus_fraction": float(Q_defocus.sum() / Q_solar.sum()) if Q_solar.sum() else 0.0,
            "cov_P_net_active": cov,
            "daily_energy_MWh": daily_energy,
            "diurnal_P_net": diurnal_P,
            "diurnal_soc": diurnal_soc,
            "mode_hours": mode_hours,
        }

    q_values = [float(q) for q in Q_DESIGN_REF * np.linspace(q_frac_min, q_frac_max, n_points)]
    cache_dir = os.path.join("ModelResults", "q_design_study")
    os.makedirs(cache_dir, exist_ok=True)
    expected_hours = 24 * n_days

    loaded = {}
    jobs = []
    for Q_design in q_values:
        cache_path = cache_path_for(cache_dir, Q_design)
        if use_cache and os.path.isfile(cache_path):
            cached = pd.read_csv(cache_path)
            if len(cached) == expected_hours:
                loaded[Q_design] = cached
                continue
        jobs.append((Q_design, n_days, start_day, cache_path))


    if jobs:
        workers = min(len(jobs), max(cpu_count() - 1, 1), 4)
        with Pool(processes=workers) as pool:
            for Q_design, df in pool.map(_solve_q_design_month, jobs):
                loaded[float(Q_design)] = df

    summaries = [summarise_month(loaded[q], q) for q in q_values]
    q_mw = np.array(q_values) / 1e6

    summary_table = pd.DataFrame([
        {k: v for k, v in s.items()
         if k not in ("daily_energy_MWh", "diurnal_P_net", "diurnal_soc", "mode_hours")}
        for s in summaries
    ])
    summary_table.to_csv(os.path.join(cache_dir, "monthly_kpis.csv"), index=False)
    print(summary_table.to_string(index=False))

    # ------------------------------------------------------------------
    # Figure 1 — monthly KPIs (energy-weighted, one point per Q_design)
    # ------------------------------------------------------------------
    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))

    ax[0, 0].plot(q_mw, [s["E_net_MWh"] for s in summaries], linewidth=2, marker="o")
    ax[0, 0].set_ylabel("Monthly net energy (MWh)")
    ax[0, 0].set_xlabel("Q_design (MW)")
    ax[0, 0].set_title("Monthly Net Energy vs. Solar Q_design", fontsize=13)

    ax[0, 1].plot(q_mw, percentage([s["eta_I"] for s in summaries]), linewidth=2, marker="o")
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Q_design (MW)")
    ax[0, 1].set_title("Energy-Weighted Efficiency vs. Solar Q_design", fontsize=13)

    ax[1, 0].plot(q_mw, percentage([s["eta_II"] for s in summaries]), linewidth=2, marker="o")
    ax[1, 0].set_ylabel("Exergy (%)")
    ax[1, 0].set_xlabel("Q_design (MW)")
    ax[1, 0].set_title("Energy-Weighted Exergy vs. Solar Q_design", fontsize=13)

    ax[1, 1].plot(q_mw, percentage([s["eta_solar"] for s in summaries]), linewidth=2, marker="o")
    ax[1, 1].set_ylabel("Solar efficiency (%)")
    ax[1, 1].set_xlabel("Q_design (MW)")
    ax[1, 1].set_title("Energy-Weighted Solar Efficiency vs. Solar Q_design", fontsize=13)

    for axis in ax.flat:
        axis.grid(True, alpha=0.3)

    Title = f"Effect of Solar Q design on Monthly({get_month(day_number=start_day,year=2023)}, 2023) System Performance"
    fig.suptitle(Title, fontsize=16, fontweight="bold")
    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches="tight")
    pyplot.show()

    # ------------------------------------------------------------------
    # Figure 2 — hours, capacity factor, defocus, fluctuation intensity
    # ------------------------------------------------------------------
    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))

    ax[0, 0].plot(q_mw, [s["active_hours"] for s in summaries], linewidth=2, marker="o")
    ax[0, 0].set_ylabel("Active hours")
    ax[0, 0].set_xlabel("Q_design (MW)")
    ax[0, 0].set_title("Power-Block Active Hours vs. Solar Q_design", fontsize=13)

    ax[0, 1].plot(q_mw, percentage([s["capacity_factor"] for s in summaries]), linewidth=2, marker="o")
    ax[0, 1].set_ylabel("Capacity factor (%)")
    ax[0, 1].set_xlabel("Q_design (MW)")
    ax[0, 1].set_title("Thermal Capacity Factor vs. Solar Q_design", fontsize=13)

    ax[1, 0].plot(q_mw, percentage([s["defocus_fraction"] for s in summaries]), linewidth=2, marker="o")
    ax[1, 0].set_ylabel("Defocused solar heat (%)")
    ax[1, 0].set_xlabel("Q_design (MW)")
    ax[1, 0].set_title("Defocused Fraction vs. Solar Q_design", fontsize=13)

    ax[1, 1].plot(q_mw, [s["cov_P_net_active"] for s in summaries], linewidth=2, marker="o")
    ax[1, 1].set_ylabel("CoV of net Power (active hours)")
    ax[1, 1].set_xlabel("Q design (MW)")
    ax[1, 1].set_title("Output Fluctuation Intensity vs. Solar Q_design", fontsize=13)

    for axis in ax.flat:
        axis.grid(True, alpha=0.3)

    Title = f"Effect of Solar Q design on Utilisation in {get_month(day_number=start_day,year=2023)}, 2023"
    fig.suptitle(Title, fontsize=16, fontweight="bold")
    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches="tight")
    pyplot.show()

    # ------------------------------------------------------------------
    # Figure 3 — how the month looks at each Q_design (the fluctuation comparison)
    # ------------------------------------------------------------------
    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))
    norm = Normalize(vmin=q_mw.min(), vmax=q_mw.max())
    cmap = cm.viridis

    for s, q in zip(summaries, q_mw):
        colour = cmap(norm(q))
        ax[0, 0].plot(s["diurnal_P_net"].index, s["diurnal_P_net"].values / 1e6,
                      color=colour, linewidth=2)
        ax[0, 1].plot(s["diurnal_soc"].index, s["diurnal_soc"].values,
                      color=colour, linewidth=2)

    ax[0, 0].set_ylabel("Mean P_net (MW)")
    ax[0, 0].set_xlabel("Hour of day")
    ax[0, 0].set_title("Mean Diurnal Net Power (month-averaged)", fontsize=13)
    ax[0, 0].set_xlim(0, 23)

    ax[0, 1].set_ylabel("Mean tank SoC")
    ax[0, 1].set_xlabel("Hour of day")
    ax[0, 1].set_title("Mean Diurnal Storage State of Charge", fontsize=13)
    ax[0, 1].set_xlim(0, 23)

    sm = ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=ax[0, 0], label="Q_design (MW)")
    fig.colorbar(sm, ax=ax[0, 1], label="Q_design (MW)")

    box_data = [s["daily_energy_MWh"].values for s in summaries]
    ax[1, 0].boxplot(box_data, patch_artist=True)
    ax[1, 0].set_xticks(range(1, len(q_mw) + 1))
    ax[1, 0].set_xticklabels([f"{q:.0f}" for q in q_mw])
    ax[1, 0].set_ylabel("Daily net energy (MWh)")
    ax[1, 0].set_xlabel("Q_design (MW)")
    ax[1, 0].set_title("Day-to-Day Energy Spread Across the Month", fontsize=13)

    x = np.arange(len(q_values))
    bottom = np.zeros(len(q_values))
    mode_colours = cm.viridis(np.linspace(0.15, 0.85, len(dispatch_modes)))
    for mode, colour in zip(dispatch_modes, mode_colours):
        heights = np.array([s["mode_hours"].get(mode, 0) for s in summaries], dtype=float)
        ax[1, 1].bar(x, heights, bottom=bottom, label=mode.replace("_", " "), color=colour)
        bottom += heights
    ax[1, 1].set_xticks(x)
    ax[1, 1].set_xticklabels([f"{q:.0f}" for q in q_mw])
    ax[1, 1].set_ylabel("Hours")
    ax[1, 1].set_xlabel("Q_design (MW)")
    ax[1, 1].set_title("Dispatch-Mode Hours Across the Month", fontsize=13)
    ax[1, 1].legend(fontsize=8, loc="upper left")

    for axis in (ax[0, 0], ax[0, 1], ax[1, 0]):
        axis.grid(True, alpha=0.3)
    ax[1, 1].grid(True, axis="y", alpha=0.3)

    Title = "Month-Long Fluctuation Comparison Across Solar Q_design in {get_month(day_number=start_day,year=2023)}, 2023"
    fig.suptitle(Title, fontsize=16, fontweight="bold")
    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches="tight")
    pyplot.show()


def plotting_comparison(day_number=222):
    plants = {
        "AP1000": "#222222",
        "Configuration 1": "#1f77b4",
        "Configuration 2": "#d62728",
        "Andasol-1": "#2ca02c",
    }

    def pick(row, key):
        value = row.get(key, float("nan"))
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("nan")

    def frame_kpis(df):
        """Read the four log KPIs, sorted by hour."""
        work = df.copy()
        work["hour"] = pd.to_numeric(work["hour"], errors="coerce")
        work = work.sort_values("hour")
        hours, power, eta, eta_s, eta2 = [], [], [], [], []
        for _, row in work.iterrows():
            rec = row.to_dict()
            hours.append(pick(rec, "hour"))
            power.append(pick(rec, "P_net"))
            eta.append(pick(rec, "efficiency"))
            eta_s.append(pick(rec, "solar_efficiency"))
            eta2.append(pick(rec, "efficiency_II"))
        return hours, power, eta, eta_s, eta2

    ap = solve_ap1000(print_results=False)
    ap = pd.DataFrame([{**ap, "hour": hour} for hour in range(24)])
    c1 = solve_configuration1(day_number=day_number, hourly=True, verbose=False, results_csv=None)
    c2 = solve_configuration2(day_number=day_number, n_days=1, verbose=False, results_csv=None, hourly=True,
                              print_results=False)
    an = solve_andasol1(day_number=day_number, n_days=1, hourly=True, print_results=False, verbose=False, results_csv=None,
    )

    traces = {
        "AP1000": frame_kpis(ap),
        "Configuration 1": frame_kpis(c1),
        "Configuration 2": frame_kpis(c2),
        "Andasol-1": frame_kpis(an),
    }

    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))
    panels = (
        (ax[0, 0], 1, "Power (W)", False, "Net Power vs. Hour of Day"),
        (ax[0, 1], 2, "Efficiency (%)", True, "Efficiency vs. Hour of Day"),
        (ax[1, 1], 3, "Efficiency (%)", True, "Solar Efficiency vs. Hour of Day"),
        (ax[1, 0], 4, "Exergy (%)", True, "Exergy vs. Hour of Day"),
    )
    for axis, idx, ylabel, as_percent, title in panels:
        for name, colour in plants.items():
            x = traces[name][0]
            y = traces[name][idx]
            axis.plot(x, percentage(y) if as_percent else y,
                      color=colour, linewidth=2, label=name)
        axis.set_xlabel("Hour of day")
        axis.set_ylabel(ylabel)
        axis.set_title(title, fontsize=13)
        axis.set_xlim(0, 23)
        axis.grid(True, alpha=0.3)
        axis.legend()

    Title = "Plant Comparison over One Day"
    fig.suptitle(Title, fontsize=16, fontweight="bold")
    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches="tight")
    pyplot.show()


if __name__ == "__main__":
    # Config 2
    # plotting_fluids_2()
    #plotting_p_nuclear_condenser_2()
    #plotting_evaporator_secondary_2()
    plotting_HP_LP_Turbine_outlets_2()
    # plotting_reheat_fraction_2()
    #plotting_Q_design_thermal(start_day=212)
    # plotting_Q_design_thermal(start_day=1)

    # plotting_reheat_fraction_2()
    # plotting_condenser_secondary_2()
    # plotting_HP_LP_Turbine_outlets_2()
    # plotting_ttd_u_2()
    # plotting_Q_design_thermal()
    # plotting_comparison(223)
    #plotting_fluids_2()# Done

    # Config 1