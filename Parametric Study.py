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

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


def get_month(day_number, year=2026):
    date = datetime.strptime(f"{year}-{day_number}", "%Y-%j")
    return date.strftime("%B")

def percentage(num_list):

    return [x * 100 for x in num_list]



#-----------------------------------------------------------------------#
#
#Config 1 Study
#
#-----------------------------------------------------------------------#
def _config1_kpis(results):
    if isinstance(results, pd.DataFrame):
        results = results.iloc[-1]
    return (
        float(results["P_net"]),
        float(results["efficiency"]),
        float(results["solar_efficiency"]),
        float(results["efficiency_II"]),
    )


def _solve_config1_point(**kwargs):
    try:
        return _config1_kpis(solve_configuration1(hourly=False, print_results=False, verbose=False, results_csv=None, **kwargs))
    except Exception:
        return (float("nan"), float("nan"), float("nan"), float("nan"))


def _plot_config1_four(x, power, eta, eta_s, eta2, xlabel, titles, suptitle):
    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))
    series = (power, percentage(eta), percentage(eta2), percentage(eta_s))
    ylabels = ("Power (W)", "Efficiency (%)", "Exergy (%)", "Efficiency (%)")
    axes = (ax[0, 0], ax[0, 1], ax[1, 0], ax[1, 1])
    for axis, y, ylabel, title in zip(axes, series, ylabels, titles):
        axis.plot(x, y, linewidth=2)
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        axis.set_title(title, fontsize=13)
        axis.grid(True, alpha=0.3)
    fig.suptitle(suptitle, fontsize=16, fontweight="bold")
    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{suptitle}", dpi=150, bbox_inches="tight")
    pyplot.show()


def plotting_mass_flow_fraction_1():
    """Measures net power, first-law efficiency, solar incremental efficiency and exergy efficiency against the live-steam fraction bled to the solar reheater.

    This split is the mass coupling between the solar field and the nuclear Rankine cycle, so it shows how much HP turbine work is given up to raise LP admission enthalpy. The curve is what a designer would cite when choosing a bleed that does not starve the HP cylinder or leave the moisture-separator reheater under-fired. Configuration 2 has no live-steam bleed into a solar reheater, so this result is exclusive to Configuration 1.
    """
    mass_flow_fraction_values = np.linspace(0.020, 0.042, 16)
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for bleed in mass_flow_fraction_values:
        power, eta, eta_s, eta2 = _solve_config1_point(main_mass_flow_bleed=bleed, fix_main_steam_bleed=True)
        power_values.append(power)
        efficiency_values.append(eta)
        solar_efficiency_values.append(eta_s)
        exergy_efficiency_values.append(eta2)

    _plot_config1_four(
        [x * 100 for x in mass_flow_fraction_values],
        power_values, efficiency_values, solar_efficiency_values, exergy_efficiency_values,
        "Live-steam bleed fraction (%)",
        (
            "Power Output Vs. Live-Steam Bleed Fraction",
            "Efficiency Vs. Live-Steam Bleed Fraction",
            "Exergy Vs. Live-Steam Bleed Fraction",
            "Solar Efficiency Vs. Live-Steam Bleed Fraction",
        ),
        "Effect of Live-Steam Bleed Fraction on System Performance (Configuration 1)",
    )


def plotting_p_condenser_1(season="summer"):
    """Measures net power, first-law efficiency, solar incremental efficiency and exergy efficiency against condenser backpressure at the chosen winter or summer cooling-water temperatures.

    Rankine expansion work is uniquely sensitive to sink pressure, and Configuration 1 rejects heat to cooling water rather than to an ORC boiler, so seasonal cooling-water temperature appears directly as vacuum. The sweep is the evidence for how much summer derate versus winter gain the hybrid plant should be credited with. Changing season retargets both the cooling-water range and the pressure window so the condenser pinch stays physically feasible.
    """
    seasons = {
        "winter": dict(T_cw_in=283.15, T_cw_out=293.15, p_min=4.5e3, p_max=10.0e3),
        "summer": dict(T_cw_in=298.15, T_cw_out=310.15, p_min=8.0e3, p_max=18.0e3),
    }
    spec = seasons[season.lower()]
    p_floor = PropsSI("P", "T", spec["T_cw_out"], "Q", 0, "Water") + 1.5e3  # keep condenser above the cooling-water bubble point
    pressure_values = np.linspace(max(spec["p_min"], p_floor), spec["p_max"], 25)
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for pressure in pressure_values:
        power, eta, eta_s, eta2 = _solve_config1_point(
            p_condenser=pressure, T_cw_in=spec["T_cw_in"], T_cw_out=spec["T_cw_out"])
        power_values.append(power)
        efficiency_values.append(eta)
        solar_efficiency_values.append(eta_s)
        exergy_efficiency_values.append(eta2)

    label = season.lower().capitalize()
    _plot_config1_four(
        [p / 1000 for p in pressure_values],
        power_values, efficiency_values, solar_efficiency_values, exergy_efficiency_values,
        "Condenser pressure (kPa)",
        (
            f"Power Output Vs. Condenser Pressure ({label})",
            f"Efficiency Vs. Condenser Pressure ({label})",
            f"Exergy Vs. Condenser Pressure ({label})",
            f"Solar Efficiency Vs. Condenser Pressure ({label})",
        ),
        f"Effect of Condenser Pressure on System Performance in {label} (Configuration 1)",
    )


def plotting_reheat_fraction_1():
    """Measures net power, first-law efficiency, solar incremental efficiency and exergy efficiency against the fraction of solar duty sent to the reheater rather than the live-steam superheater.

    Configuration 1 injects solar heat into the nuclear steam itself, so this energy split changes HP inlet superheat and LP reheat together. That trade-off is what you discuss when arguing that the solar field is a topping heater on the AP1000 cycle rather than a separate power block. The result set is also the energy-side counterpart of the live-steam bleed test, because duty split and bleed mass are the two ways of stating the same integration.
    """
    reheat_fraction_values = np.linspace(0.05, 0.40, 20)
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for reheat_fraction in reheat_fraction_values:
        power, eta, eta_s, eta2 = _solve_config1_point(reheat_fraction=reheat_fraction)
        power_values.append(power)
        efficiency_values.append(eta)
        solar_efficiency_values.append(eta_s)
        exergy_efficiency_values.append(eta2)

    _plot_config1_four(
        [x * 100 for x in reheat_fraction_values],
        power_values, efficiency_values, solar_efficiency_values, exergy_efficiency_values,
        "Solar reheat duty fraction (%)",
        (
            "Power Output Vs. Solar Reheat Fraction",
            "Efficiency Vs. Solar Reheat Fraction",
            "Exergy Vs. Solar Reheat Fraction",
            "Solar Efficiency Vs. Solar Reheat Fraction",
        ),
        "Effect of Solar Reheat Fraction on System Performance (Configuration 1)",
    )


def plotting_T_field_out_1():
    """Measures net power, first-law efficiency, solar incremental efficiency and exergy efficiency against solar-field outlet temperature.

    Higher oil temperature raises steam superheat and reheat but increases collector thermal losses and approaches the Therminol VP-1 limit. The nuclear steam already sets a high source temperature, so the remaining solar temperature rise is small and this sweep shows whether chasing hotter oil is worth the field loss. Those numbers support the claim that Configuration 1 is temperature-constrained by the HTF rather than by the Rankine cycle.
    """
    T_values = np.linspace(630.0, 666.15, 15)
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for T_field_out in T_values:
        power, eta, eta_s, eta2 = _solve_config1_point(T_field_out=T_field_out)
        power_values.append(power)
        efficiency_values.append(eta)
        solar_efficiency_values.append(eta_s)
        exergy_efficiency_values.append(eta2)

    _plot_config1_four(
        [T - 273.15 for T in T_values],
        power_values, efficiency_values, solar_efficiency_values, exergy_efficiency_values,
        "Field outlet temperature (C)",
        (
            "Power Output Vs. Field Outlet Temperature",
            "Efficiency Vs. Field Outlet Temperature",
            "Exergy Vs. Field Outlet Temperature",
            "Solar Efficiency Vs. Field Outlet Temperature",
        ),
        "Effect of Solar Field Outlet Temperature on System Performance (Configuration 1)",
    )


def plotting_T_lp_inlet_1():
    """Measures net power, first-law efficiency, solar incremental efficiency and exergy efficiency against LP-turbine admission temperature after the solar reheater.

    This is the steam state the Configuration 1 solar reheater exists to produce, so the sweep is a direct test of the integration concept. It shows how much extra LP expansion work is bought per kelvin of reheat and where pinch or moisture would stop you. That is the plot to cite when comparing this layout with a conventional moisture-separator reheater on an unaugmented AP1000.
    """
    # Floor is Tsat of HP bleed 1 plus 2 K: below that the solar reheater pinch reverses.
    T_msr_stage1 = PropsSI("T", "P", 3.413025e6, "Q", 0, "Water")
    T_values = np.linspace(T_msr_stage1 + 2.0, 560.0, 16)
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for T_lp_inlet in T_values:
        power, eta, eta_s, eta2 = _solve_config1_point(T_lp_inlet=T_lp_inlet)
        power_values.append(power)
        efficiency_values.append(eta)
        solar_efficiency_values.append(eta_s)
        exergy_efficiency_values.append(eta2)

    _plot_config1_four(
        [T - 273.15 for T in T_values],
        power_values, efficiency_values, solar_efficiency_values, exergy_efficiency_values,
        "LP admission temperature (C)",
        (
            "Power Output Vs. LP Admission Temperature",
            "Efficiency Vs. LP Admission Temperature",
            "Exergy Vs. LP Admission Temperature",
            "Solar Efficiency Vs. LP Admission Temperature",
        ),
        "Effect of LP Admission Temperature on System Performance (Configuration 1)",
    )


def plotting_ttd_u_1():
    """Measures net power, first-law efficiency, solar incremental efficiency and exergy efficiency against closed-heater terminal temperature difference on the AP1000 feedwater train.

    Larger TTD cheapens the heaters and dumps more irreversibility into the feedwater train, which changes both nuclear heat rate and the room left for solar heat. Configuration 1 keeps the DCD heater train, so this is the sensitivity that links the hybrid to the licensed feedwater design. The results let you say whether the 4 F TTD is a binding constraint on the solar integration or a free parameter.
    """
    ttd_values = np.linspace(2.222, 12.0, 15)
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for ttd_u in ttd_values:
        power, eta, eta_s, eta2 = _solve_config1_point(ttd_u_fwh=ttd_u)
        power_values.append(power)
        efficiency_values.append(eta)
        solar_efficiency_values.append(eta_s)
        exergy_efficiency_values.append(eta2)

    _plot_config1_four(
        ttd_values,
        power_values, efficiency_values, solar_efficiency_values, exergy_efficiency_values,
        "Terminal temperature difference (K)",
        (
            "Power Output Vs. Heater TTD",
            "Efficiency Vs. Heater TTD",
            "Exergy Vs. Heater TTD",
            "Solar Efficiency Vs. Heater TTD",
        ),
        "Effect of Feedwater Heater TTD on System Performance (Configuration 1)",
    )


def plotting_seasonal_day_1(winter_day=15, summer_day=212):
    """Measures hourly net power, first-law efficiency, solar incremental efficiency and exergy efficiency for one winter day against one summer day, each with matching condenser vacuum and cooling-water temperatures.

    The overlay isolates solar resource from heat-sink temperature in a way a single Q_design month cannot. Configuration 1's condenser sees the ambient through cooling water, so summer versus winter is both a DNI story and a Rankine backpressure story. That paired day is the figure to discuss in a seasonal-operation chapter when claiming that the hybrid's condenser, not only the field, shifts with the weather.
    """
    cases = {
        "Winter": dict(day_number=winter_day, p_condenser=6.0e3, T_cw_in=283.15, T_cw_out=293.15, colour="#1f77b4"),
        "Summer": dict(day_number=summer_day, p_condenser=12.0e3, T_cw_in=298.15, T_cw_out=310.15, colour="#d62728"),
    }
    traces = {}
    for name, spec in cases.items():
        df = solve_configuration1(
            day_number=spec["day_number"], n_days=1, hourly=True, verbose=False,
            print_results=False, results_csv=None,
            p_condenser=spec["p_condenser"], T_cw_in=spec["T_cw_in"], T_cw_out=spec["T_cw_out"])
        traces[name] = (
            pd.to_numeric(df["hour"], errors="coerce"),
            pd.to_numeric(df["P_net"], errors="coerce"),
            pd.to_numeric(df["efficiency"], errors="coerce"),
            pd.to_numeric(df["solar_efficiency"], errors="coerce"),
            pd.to_numeric(df["efficiency_II"], errors="coerce"),
            spec["colour"],
        )

    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))
    panels = (
        (ax[0, 0], 1, "Power (W)", False, "Net Power vs. Hour of Day"),
        (ax[0, 1], 2, "Efficiency (%)", True, "Efficiency vs. Hour of Day"),
        (ax[1, 0], 4, "Exergy (%)", True, "Exergy vs. Hour of Day"),
        (ax[1, 1], 3, "Efficiency (%)", True, "Solar Efficiency vs. Hour of Day"),
    )
    for axis, idx, ylabel, as_percent, title in panels:
        for name, trace in traces.items():
            y = percentage(trace[idx]) if as_percent else trace[idx]
            axis.plot(trace[0], y, color=trace[5], linewidth=2, label=name)
        axis.set_xlabel("Hour of day")
        axis.set_ylabel(ylabel)
        axis.set_title(title, fontsize=13)
        axis.set_xlim(0, 23)
        axis.grid(True, alpha=0.3)
        axis.legend()

    Title = "Winter vs Summer Day with Seasonal Condenser Vacuum (Configuration 1)"
    fig.suptitle(Title, fontsize=16, fontweight="bold")
    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches="tight")
    pyplot.show()


def _solve_q_design_month_1(args):
    """Worker: one Q_design over n_days of hourly weather. Must stay top-level for Windows multiprocessing."""
    Q_design, n_days, start_day = args
    results = solve_configuration1(
        Q_design_thermal=Q_design, day_number=start_day, n_days=n_days, verbose=False,
        results_csv=None, hourly=True, print_results=False)
    return Q_design, results


def plotting_Q_design_thermal_1(n_days=30,start_day=212,n_points=10,q_frac_min=0.40,q_frac_max=1.00,):
    """Measures month-long net energy, energy-weighted first-law, solar and exergy efficiencies, power-block active hours, thermal capacity factor, defocused fraction, output fluctuation, diurnal power and tank SoC, daily energy spread and dispatch-mode hours against solar-section thermal rating.

    This is the storage-sizing question: a larger Q_design harvests more noon sun but spends more hours below minimum load and cycles the tank differently. Configuration 1 never shuts the nuclear block, so Q_design only moves the solar share and the store, which is a different story from a standalone CSP plant or from Configuration 2's ORC-coupled solar section. Every call reruns TESPy for the requested start_day window.
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

    def numeric(series):
        return pd.to_numeric(series, errors="coerce")

    def summarise_month(df, Q_design):
        """Energy-weighted monthly KPIs. Do not arithmetic-mean hourly efficiency."""
        P_net = numeric(df["P_net"])
        Q_sg = numeric(df["Q_sg_oil"])
        Q_to_pb = numeric(df["Q_to_pb"])
        Q_defocus = numeric(df["Q_defocus"])
        Q_solar = numeric(df["Q_solar"])
        soc = numeric(df["tank_soc"])
        Q_in = Q_sg + nuclear_heat_input

        active = Q_to_pb > 0
        solar_on = (Q_sg > 0) & P_net.notna()
        solar_off = (Q_sg <= 0) & P_net.notna()
        hours_to_MWh = 1e-6

        work = df.copy()
        work["P_net"] = P_net
        work["tank_soc"] = soc
        daily_energy = work.groupby("day_of_year")["P_net"].sum() * hours_to_MWh
        diurnal_P = work.groupby("hour")["P_net"].mean()
        diurnal_soc = work.groupby("hour")["tank_soc"].mean()

        P_active = P_net[active]
        cov = float(P_active.std() / P_active.mean()) if P_active.mean() else float("nan")

        P_base = float(P_net[solar_off].mean()) if solar_off.any() else float("nan")
        q_solar_sum = float(Q_sg[solar_on].sum())
        eta_solar = (
            float((P_net[solar_on] - P_base).sum() / q_solar_sum)
            if q_solar_sum and pd.notna(P_base) else float("nan")
        )

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
            "eta_solar": eta_solar,
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
    month_name = get_month(day_number=start_day, year=2023)
    out_dir = os.path.join("ModelResults", "q_design_study_config1", month_name)
    os.makedirs(out_dir, exist_ok=True)
    print(f"Q_design Config 1: {n_days} days from day {start_day} ({month_name} 2023), {n_points} points")

    jobs = [(Q_design, n_days, start_day) for Q_design in q_values]
    loaded = {}
    workers = min(len(jobs), max(cpu_count() - 1, 1), 4)
    with Pool(processes=workers) as pool:
        for Q_design, df in pool.map(_solve_q_design_month_1, jobs):
            loaded[float(Q_design)] = df

    summaries = [summarise_month(loaded[q], q) for q in q_values]
    q_mw = np.array(q_values) / 1e6

    summary_table = pd.DataFrame([
        {k: v for k, v in s.items()
         if k not in ("daily_energy_MWh", "diurnal_P_net", "diurnal_soc", "mode_hours")}
        for s in summaries
    ])
    summary_table.to_csv(os.path.join(out_dir, "monthly_kpis.csv"), index=False)
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

    Title = f"Effect of Solar Q design on Monthly({get_month(day_number=start_day,year=2023)}, 2023) System Performance(Configuration 1)"
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

    Title = f"Effect of Solar Q design on Utilisation in {get_month(day_number=start_day,year=2023)}, 2023(Configuration 1)"
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

    Title = f"Month-Long Fluctuation Comparison Across Solar Q_design in {get_month(day_number=start_day,year=2023)}, 2023(Configuration 1)"
    fig.suptitle(Title, fontsize=16, fontweight="bold")
    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches="tight")
    pyplot.show()




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
        "WATER",
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
            results = solve_configuration2(secondary_fluid=fluid,
                                           p_evaporator_secondary=p_evaporator,
                                           ttd_u_fwh=[2.22, 4.8, 2.22, 4, 8, 8],
                                           reheat_fraction=0.05,
                                           p_hp_exhaust_secondary=p_hp_exhaust, p_condenser_secondary=p_condenser,
                                           hourly=False, print_results=False)

            power_values.append(results["P_net"])
            efficiency_values.append(results["efficiency"])
            solar_efficiency_values.append(results["solar_efficiency"])
            exergy_efficiency_values.append(results["efficiency_II"])
        except:
            power_values.append(0)
            efficiency_values.append(0)
            solar_efficiency_values.append(0)
            exergy_efficiency_values.append(0)

    fig, ax = pyplot.subplots(2, 2, figsize=(20, 20))
    ax[0, 0].bar(labels, power_values,color=["orange"] + ["steelblue"] * (len(labels) - 1))
    ax[0, 0].set_ylabel("Power (W)")
    ax[0, 0].set_xlabel("Fluid")
    ax[0, 0].set_title("Power Output by Working Fluids")


    ax[0, 1].bar(labels, percentage(efficiency_values),color=["orange"] + ["steelblue"] * (len(labels) - 1))
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Fluid")
    ax[0, 1].set_title("Efficiency by Working Fluids")

    ax[1, 1].bar(labels, percentage(solar_efficiency_values),color=["orange"] + ["steelblue"] * (len(labels) - 1))
    ax[1, 1].set_ylabel("Efficiency (%)")
    ax[1, 1].set_xlabel("Fluid")
    ax[1, 1].set_title("Solar Efficiency by Working Fluids")

    ax[1, 0].bar(labels, percentage(exergy_efficiency_values),color=["orange"] + ["steelblue"] * (len(labels) - 1))
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
        results = solve_configuration2(secondary_fluid={"WATER":1},p_nuclear_condenser=pressure, hourly=False, print_results=False)
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
    ax[0, 0].set_xlabel("Pressure (kPa)")
    ax[0, 0].set_title("Power Output Vs. ORC Superheater inlet", fontsize=13)

    # Efficiency Plot
    ax[0, 1].plot([x / 1000 for x in pressure_values], percentage(efficiency_values), linewidth=2)
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Pressure (kPa)")
    ax[0, 1].set_title("Efficiency Vs.ORC Superheater inlet", fontsize=13)

    # Solar Efficiency Plot
    ax[1, 1].plot([x / 1000 for x in pressure_values], percentage(solar_efficiency_values), linewidth=2)
    ax[1, 1].set_ylabel("Efficiency (%)")
    ax[1, 1].set_xlabel("Pressure (kPa)")
    ax[1, 1].set_title("Solar Efficiency Vs. ORC Superheater inlet", fontsize=13)

    # Exergy Efficiency Plot
    ax[1, 0].plot([x / 1000 for x in pressure_values], percentage(exergy_efficiency_values), linewidth=2)
    ax[1, 0].set_ylabel("Exergy (%)")
    ax[1, 0].set_xlabel("Pressure (kPa)")
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
    ax[0, 1].plot([x * 100 for x in reheat_fraction_values], percentage(efficiency_values), linewidth=2)
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Pressure (Pa)")
    ax[0, 1].set_title("Efficiency Vs. Oil Reheat Fraction", fontsize=13)

    # Solar Efficiency Plot
    ax[1, 1].plot([x * 100 for x in reheat_fraction_values], percentage(solar_efficiency_values), linewidth=2)
    ax[1, 1].set_ylabel("Efficiency (%)")
    ax[1, 1].set_xlabel("Pressure (Pa)")
    ax[1, 1].set_title("Solar Efficiency Vs. Oil Reheat Fraction", fontsize=13)

    # Exergy Efficiency Plot
    ax[1, 0].plot([x * 100 for x in reheat_fraction_values], percentage(exergy_efficiency_values), linewidth=2)
    ax[1, 0].set_ylabel("Exergy (%)")
    ax[1, 0].set_xlabel("Pressure (Pa)")
    ax[1, 0].set_title("Exergy Vs. Oil Reheat Fraction", fontsize=13)

    ax[0, 0].grid(True)
    ax[0, 1].grid(True)
    ax[1, 0].grid(True)
    ax[1, 1].grid(True, alpha=0.3)
    for axis in ax.flat:
        axis.xaxis.set_major_locator(MaxNLocator(nbins=10))
        axis.grid(True, alpha=0.3)

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

def _solve_single_point_pinch(args):
    """Worker function — must be top-level (picklable) for multiprocessing."""
    HP_pressure, LP_pressure = args
    results = solve_configuration2(p_nuclear_condenser=HP_pressure, p_evaporator_secondary=LP_pressure,
                                   hourly=False, print_results=False)
    return results["T_pinch"]


def plotting_T_pinch_2():
    data_points = 50
    p_nuclear_condenser_values = np.linspace(0.82e5, 1.18e5, data_points)
    p_evaporator_secondary_values = np.linspace(6e5, 1.1e6, data_points)

    LP_grid, HP_grid = np.meshgrid(p_evaporator_secondary_values, p_nuclear_condenser_values)
    grid_points = list(zip(HP_grid.ravel(), LP_grid.ravel()))

    with Pool(processes=max(cpu_count() - 1, 1)) as pool:
        raw_results = pool.map(_solve_single_point_pinch, grid_points)

    shape = HP_grid.shape
    pinch_values = np.array(raw_results, dtype=float).reshape(shape)

    MIN_PINCH_K = 2.2

    fig, ax = pyplot.subplots(figsize=(10, 10))

    pinch_plot = ax.pcolormesh(
        LP_grid, HP_grid, pinch_values, cmap=cm.RdYlGn, shading="auto")
    ax.set_ylabel("Nuclear Condenser Back Pressure (Pa)")
    ax.set_xlabel("ORC Superheater Inlet (Pa)")
    ax.set_title("Nuclear Condenser Pinch Temperature Vs. Secondary LP and HP Turbine Outlet Pressure", fontsize=13)
    cbar = pyplot.colorbar(pinch_plot, ax=ax)
    cbar.set_label("T_pinch (K)")

    # Marks the exact line where the model switches results to NaN
    boundary = ax.contour(
        LP_grid, HP_grid, pinch_values, levels=[MIN_PINCH_K],
        colors="black", linewidths=2, linestyles="--")
    ax.clabel(boundary, fmt={MIN_PINCH_K: f"{MIN_PINCH_K} K limit"})

    ax.grid(True, alpha=0.3)

    Title = "Nuclear Condenser Pinch Temperature Across the Secondary Pressure Grid"
    fig.suptitle(Title, fontsize=16, fontweight="bold")

    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches='tight')
    pyplot.show()


def plotting_HP_LP_Turbine_outlets_2():
    data_points = 20
    p_nuclear_condenser_values = np.linspace(0.82e5, 1.18e5, data_points)
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
    for axis in ax.flat:
        axis.grid(True, alpha=0.3)
        axis.xaxis.set_major_locator(MaxNLocator(nbins=10))


    Title = "Effect of Nuclear Condenser Back Pressure and ORC Superheater Inlet Pressure on System Performance(Configuration 1)"
    fig.suptitle(Title, fontsize=16, fontweight="bold")

    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches='tight')  # save BEFORE show
    pyplot.show()


def _solve_q_design_month(args):
    """Worker: one Q_design over n_days of hourly weather. Must stay top-level for Windows multiprocessing."""
    Q_design, n_days, start_day = args
    results = solve_configuration2(Q_design_thermal=Q_design,
                                   p_nuclear_condenser=90e3,
                                   p_evaporator_secondary=1.05e6,
                                   ttd_u_fwh=[2.22,4.8,2.22,4,8,8],
                                   reheat_fraction=0.05,
                                   day_number=start_day, n_days=n_days, verbose=False,
                                   results_csv=None, hourly=True, print_results=False)
    return Q_design, results


def plotting_Q_design_thermal(n_days=30,start_day=212,n_points=10,q_frac_min=0.40,q_frac_max=1.00,):
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

    Every call reruns TESPy for the requested start_day window. Winter and summer
    must not share files, because the hourly CSVs were previously keyed only by
    Q_design and a January run would reuse July results.
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

    def numeric(series):
        return pd.to_numeric(series, errors="coerce")

    def summarise_month(df, Q_design):
        """Energy-weighted monthly KPIs. Do not arithmetic-mean hourly efficiency."""
        P_net = numeric(df["P_net"])
        Q_sg = numeric(df["Q_sg_oil"])
        Q_to_pb = numeric(df["Q_to_pb"])
        Q_defocus = numeric(df["Q_defocus"])
        Q_solar = numeric(df["Q_solar"])
        soc = numeric(df["tank_soc"])
        Q_in = Q_sg + nuclear_heat_input

        active = Q_to_pb > 0
        solar_on = (Q_sg > 0) & P_net.notna()
        solar_off = (Q_sg <= 0) & P_net.notna()
        hours_to_MWh = 1e-6

        work = df.copy()
        work["P_net"] = P_net
        work["tank_soc"] = soc
        daily_energy = work.groupby("day_of_year")["P_net"].sum() * hours_to_MWh
        diurnal_P = work.groupby("hour")["P_net"].mean()
        diurnal_soc = work.groupby("hour")["tank_soc"].mean()

        P_active = P_net[active]
        cov = float(P_active.std() / P_active.mean()) if P_active.mean() else float("nan")

        P_base = float(P_net[solar_off].mean()) if solar_off.any() else float("nan")
        q_solar_sum = float(Q_sg[solar_on].sum())
        eta_solar = (
            float((P_net[solar_on] - P_base).sum() / q_solar_sum)
            if q_solar_sum and pd.notna(P_base) else float("nan")
        )

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
            "eta_solar": eta_solar,
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
    month_name = get_month(day_number=start_day, year=2023)
    out_dir = os.path.join("ModelResults", "q_design_study", month_name)
    os.makedirs(out_dir, exist_ok=True)
    print(f"Q_design Config 2: {n_days} days from day {start_day} ({month_name} 2023), {n_points} points")

    jobs = [(Q_design, n_days, start_day) for Q_design in q_values]
    loaded = {}
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
    summary_table.to_csv(os.path.join(out_dir, "monthly_kpis.csv"), index=False)
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

    Title = f"Effect of Solar Q design on Monthly({get_month(day_number=start_day,year=2023)}, 2023) System Performance(Configuration 2)"
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

    Title = f"Effect of Solar Q design on Utilisation in {get_month(day_number=start_day,year=2023)}, 2023(Configuration 2)"
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

    Title = f"Month-Long Fluctuation Comparison Across Solar Q_design in {get_month(day_number=start_day,year=2023)}, 2023(Configuration 2)"
    fig.suptitle(Title, fontsize=16, fontweight="bold")
    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches="tight")
    pyplot.show()


def _config2_comparison_kwargs(T_cw_in=288.15, T_cw_out=300.15):
    """Cyclopentane plant used in plotting_comparison, with ORC pressures mapped to that cycle's saturation temperatures."""
    fluid = "Cyclopentane"
    T_cond = PropsSI("T", "P", 1.9e5, "Q", 0, "R245fa")
    T_evap = PropsSI("T", "P", 1.05e6, "Q", 0, "R245fa")
    p_hp_frac = np.log(4.5e5 / 1.9e5) / np.log(1.05e6 / 1.9e5)
    T_evap_fluid = min(T_evap, 0.95 * PropsSI("Tcrit", fluid))
    p_cond = max(
        PropsSI("P", "T", T_cond, "Q", 0, fluid),
        PropsSI("P", "T", T_cw_out + 4.0, "Q", 0, fluid),
    )
    p_evap = PropsSI("P", "T", T_evap_fluid, "Q", 0, fluid)
    p_hp = float(p_cond * (p_evap / p_cond) ** p_hp_frac)
    return dict(
        Q_design_thermal=80e6,
        secondary_fluid={"CYCLOPENTANE": 1},
        p_nuclear_condenser=90e3,
        p_evaporator_secondary=p_evap,
        p_hp_exhaust_secondary=p_hp,
        p_condenser_secondary=p_cond,
        ttd_u_fwh=[2.22, 4.8, 2.22, 4, 8, 8],
        reheat_fraction=0.01,
        T_cw_in=T_cw_in,
        T_cw_out=T_cw_out,
    )


def plotting_seasonal_day_2(winter_day=15, summer_day=212):
    """Measures hourly net power, first-law efficiency, solar incremental efficiency and exergy efficiency for one winter day against one summer day on Configuration 2, using the cyclopentane plant from the comparison and the same seasonal cooling-water temperatures as Configuration 1.

    The overlay holds the nuclear-to-ORC coupling fixed and lets weather plus ORC sink temperature move together, which is the Configuration 2 counterpart of the Configuration 1 vacuum overlay. Nuclear condenser pressure stays at the comparison value because that duty is the ORC boiler, not the ambient sink. The figure is the one to cite when the bottoming cycle's cooling water, not only DNI, is claimed to shift summer versus winter output.
    """
    cases = {
        "Winter": dict(day_number=winter_day, T_cw_in=283.15, T_cw_out=293.15, colour="#1f77b4"),
        "Summer": dict(day_number=summer_day, T_cw_in=298.15, T_cw_out=310.15, colour="#d62728"),
    }
    traces = {}
    for name, spec in cases.items():
        df = solve_configuration2(
            **_config2_comparison_kwargs(T_cw_in=spec["T_cw_in"], T_cw_out=spec["T_cw_out"]),
            day_number=spec["day_number"], n_days=1, hourly=True, verbose=False,
            print_results=False, results_csv=None)
        traces[name] = (
            pd.to_numeric(df["hour"], errors="coerce"),
            pd.to_numeric(df["P_net"], errors="coerce"),
            pd.to_numeric(df["efficiency"], errors="coerce"),
            pd.to_numeric(df["solar_efficiency"], errors="coerce"),
            pd.to_numeric(df["efficiency_II"], errors="coerce"),
            spec["colour"],
        )

    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))
    panels = (
        (ax[0, 0], 1, "Power (W)", False, "Net Power vs. Hour of Day"),
        (ax[0, 1], 2, "Efficiency (%)", True, "Efficiency vs. Hour of Day"),
        (ax[1, 0], 4, "Exergy (%)", True, "Exergy vs. Hour of Day"),
        (ax[1, 1], 3, "Efficiency (%)", True, "Solar Efficiency vs. Hour of Day"),
    )
    for axis, idx, ylabel, as_percent, title in panels:
        for name, trace in traces.items():
            y = percentage(trace[idx]) if as_percent else trace[idx]
            axis.plot(trace[0], y, color=trace[5], linewidth=2, label=name)
        axis.set_xlabel("Hour of day")
        axis.set_ylabel(ylabel)
        axis.set_title(title, fontsize=13)
        axis.set_xlim(0, 23)
        axis.grid(True, alpha=0.3)
        axis.legend()

    Title = "Winter vs Summer Day with Seasonal Cooling Water (Configuration 2)"
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



    c2 = solve_configuration2(
        **_config2_comparison_kwargs(),
        day_number=day_number, n_days=1, verbose=False,
        results_csv=None, hourly=True, print_results=False)

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


def plotting_ttd_u():
    ttd_u_values = np.linspace(2.22, 15, 25)
    FWHs = ["LP FWH 1", "LP FWH 2", "LP FWH 3", "LP FWH 4", "HP FWH 1", "HP FWH 2"]

    power_values = []
    Q_nuclear_condenser_values = []

    for i, FWH in enumerate(FWHs):
        current_power_values = []
        current_Q_values = []
        ttd_u_input = [2.222, 2.222, 2.222, 2.222, 2.222, 2.222]

        for ttd_u in ttd_u_values:
            print(f"FWH: {FWH}, TTD: {ttd_u}")
            ttd_u_input[i] = ttd_u
            results = solve_configuration2(ttd_u_fwh=ttd_u_input, hourly=False, print_results=False)
            current_power_values.append(results["P_net"])
            current_Q_values.append(results["Q_nuclear_condenser"])

        power_values.append(current_power_values)
        Q_nuclear_condenser_values.append(current_Q_values)

    for index, FWH in enumerate(FWHs):
        fig, ax = pyplot.subplots(1, 2, figsize=(12, 6))

        ax[0].plot(ttd_u_values, power_values[index], linewidth=2)
        ax[0].set_ylabel("Power (W)")
        ax[0].set_xlabel("Terminal Temperature Difference (K)")
        ax[0].set_title("Power Output Vs. Terminal Temperature Difference", fontsize=13)

        ax[1].plot(ttd_u_values, Q_nuclear_condenser_values[index], linewidth=2)
        ax[1].set_ylabel("Q, Condenser Reject Heat (W)")
        ax[1].set_xlabel("Terminal Temperature Difference (K)")
        ax[1].set_title("Nuclear Condenser Reject Heat Vs. Terminal Temperature Difference", fontsize=13)

        for axis in ax:
            axis.xaxis.set_major_locator(MaxNLocator(nbins=10))
            axis.grid(True, alpha=0.3)

        Title = f"Effect of Terminal Temperature Difference of {FWH} on System Performance"
        fig.suptitle(Title, fontsize=16, fontweight="bold")

        pyplot.tight_layout()
        pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches='tight')
        pyplot.show()

    # Combined power vs reject heat, coloured by ttd_u, all FWHs on one plot
    fig, ax = pyplot.subplots(figsize=(9, 7))
    cmap = pyplot.cm.viridis
    markers = ["o", "s", "^", "D", "v", "P"]

    for index, FWH in enumerate(FWHs):
        sc = ax.scatter(
            power_values[index],
            Q_nuclear_condenser_values[index],
            c=ttd_u_values,
            cmap=cmap,
            marker=markers[index % len(markers)],
            s=40,
            edgecolors="k",
            linewidths=0.3,
            label=FWH,
        )

    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("Terminal Temperature Difference (K)")
    ax.set_xlabel("Power (W)")
    ax.set_ylabel("Q, Condenser Reject Heat (W)")
    ax.set_title("Power Vs. Condenser Reject Heat Across TTD Sweep", fontsize=14, fontweight="bold")
    ax.legend(title="FWH", loc="best")
    ax.xaxis.set_major_locator(MaxNLocator(nbins=10))
    ax.grid(True, alpha=0.3)

    Combined_Title = "Power vs Condenser Reject Heat Trade Off Across FWHs"
    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{Combined_Title}")


if __name__ == "__main__":
    # Config 2

    #plotting_p_nuclear_condenser_2()
    #plotting_evaporator_secondary_2()
    #plotting_ttd_u()
    #plotting_HP_LP_Turbine_outlets_2()
    # plotting_T_pinch_2()
    #plotting_reheat_fraction_2()
    # plotting_Q_design_thermal(start_day=212)
    # plotting_Q_design_thermal(start_day=1)
    #plotting_fluids_2()
    #plotting_seasonal_day_2()


    # Config 1
    plotting_mass_flow_fraction_1()
    plotting_p_condenser_1(season="summer")
    plotting_p_condenser_1(season="winter")
    plotting_reheat_fraction_1()
    plotting_T_field_out_1()
    plotting_T_lp_inlet_1()
    plotting_ttd_u_1()
    plotting_seasonal_day_1()
    plotting_Q_design_thermal_1(start_day=212)

    #plotting_comparison()