from envs.matlab_env.Lib.unittest import result
from matplotlib import pyplot, cm
from multiprocessing import Pool, cpu_count

from Configuration_1 import solve_configuration1
from Configuration_2 import solve_configuration2

def percentage(num_list):

    return [x * 100 for x in num_list]

import numpy as np
import matplotlib.pyplot as plt
#solve_configuration1()
#TODO: find what I need to plot
#Config 1 Study
def plotting_mass_flow_rate():
    pass




#Config 2 study
#solve_configuration2()
#Plot :
#   Bar graphs of working fluids
#   p_nuclear condenser
#   p_evaporatpr_secondary
#   reheat fraction
#   T_field_out
#   p_condenser_secondary : gonna be interesting



# Recommended metric set per sweep point
# Net power output (P_net, already in your log)
# First-law (thermal) efficiency — your existing step["efficiency"] calculation, kept as the baseline/comparable metric against Andasol-1 and AP1000 standalone
# Second-law (exergy) efficiency — worth adding, since it directly supports the "waste heat is low-grade, CSP top-up upgrades it" narrative that's central to Configuration 2's novelty
# Solar-specific incremental efficiency — extra net power generated per unit of solar thermal input added (isolates whether the CSP contribution itself is being used well, independent of the fixed nuclear baseline)

def plotting_fluids_2():
    list_of_fluids = ["ISOPENTANE", "ISOBUTANE", "HEXAMETHYLDISILOXANE", "CYCLOPENTANE", "R1233ZDE", "R245fa"]
    fluids = [{x:1} for x in list_of_fluids]
    #TODO: Fill this in with fluids and then bar chart to find most efficient/power
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for fluid in fluids:
        results = solve_configuration2(secondary_fluid=fluid, hourly=False, print_results=False)
        power_values.append(results["P_net"])
        efficiency_values.append(results["efficiency"])
        solar_efficiency_values.append(results["solar_efficiency"])
        exergy_efficiency_values.append(results["efficiency_II"])


    fig, ax = pyplot.subplots(2,2)
    power_plot = ax[0,0].bar([fluid.lower().capitalize() for fluid in list_of_fluids],power_values)
    power_plot.set_ylabel("Power (W)")
    power_plot.set_xlabel("Fluid")
    power_plot.set_title("Power Output by Working Fluids")

    efficiency_plot = ax[0,1].bar([fluid.lower().capitalize() for fluid in list_of_fluids],[x * 100  for x in efficiency_values])
    efficiency_plot.set_ylabel("Efficiency (%)")
    efficiency_plot.set_xlabel("Fluid")
    efficiency_plot.set_title("Efficiency by Working Fluids")

    solar_efficiency_plot = ax[1,1].bar([fluid.lower().capitalize() for fluid in list_of_fluids],[x * 100  for x in solar_efficiency_values])
    solar_efficiency_plot.set_ylabel("Efficiency (%)")
    solar_efficiency_plot.set_xlabel("Fluid")
    solar_efficiency_plot.set_title("Solar Efficiency by Working Fluids")

    exergy_efficiency_plot = ax[1,0].bar([fluid.lower().capitalize() for fluid in list_of_fluids],[x * 100  for x in exergy_efficiency_values])
    exergy_efficiency_plot.set_ylabel("Exergy (%)")
    exergy_efficiency_plot.set_xlabel("Fluid")
    exergy_efficiency_plot.set_title("Exergy by Working Fluids")

def plotting_p_nuclear_condenser_2():
    # The pressure coming out of the turbine
    pressure_values = np.linspace( 7e3,0.45e4, 50)
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
    ax[0, 0].set_xlabel("Pressure (Pa)")
    ax[0,0].set_title("Power Output Vs. LP Turbine Outlet Pressure", fontsize=13)


    # Efficiency Plot
    ax[0, 1].plot([x / 1000 for x in pressure_values], percentage(efficiency_values),linewidth=2)
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Pressure (Pa)")
    ax[0, 1].set_title("Efficiency Vs. LP Turbine Outlet Pressure", fontsize=13)

    # Solar Efficiency Plot
    ax[1, 1].plot([x / 1000 for x in pressure_values], percentage(solar_efficiency_values),linewidth=2)
    ax[1, 1].set_ylabel("Efficiency (%)")
    ax[1, 1].set_xlabel("Pressure (Pa)")
    ax[1, 1].set_title("Solar Efficiency Vs. LP Turbine Outlet Pressure", fontsize=13)

    # Exergy Efficiency Plot
    ax[1, 0].plot([x / 1000 for x in pressure_values], percentage(exergy_efficiency_values),linewidth=2)
    ax[1, 0].set_ylabel("Exergy (%)")
    ax[1, 0].set_xlabel("Pressure (Pa)")
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
    pressure_values = np.linspace(5e5, 1.25e6, 70)
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for pressure in pressure_values:
        results = solve_configuration2(p_evaporator_secondary=pressure, hourly=False, print_results=False)
        power_values.append(results["P_net"])
        efficiency_values.append(results["efficiency"])
        solar_efficiency_values.append(results["solar_efficiency"])
        exergy_efficiency_values.append(results["efficiency_II"])

    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))
    # Power plot
    ax[0, 0].plot([x / 1000 for x in pressure_values], power_values, linewidth=2)
    ax[0, 0].set_ylabel("Power (W)")
    ax[0, 0].set_xlabel("Pressure (Pa)")
    ax[0, 0].set_title("Power Output Vs. LP Turbine Outlet Pressure", fontsize=13)

    # Efficiency Plot
    ax[0, 1].plot([x / 1000 for x in pressure_values], percentage(efficiency_values), linewidth=2)
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Pressure (Pa)")
    ax[0, 1].set_title("Efficiency Vs. LP Turbine Outlet Pressure", fontsize=13)

    # Solar Efficiency Plot
    ax[1, 1].plot([x / 1000 for x in pressure_values], percentage(solar_efficiency_values), linewidth=2)
    ax[1, 1].set_ylabel("Efficiency (%)")
    ax[1, 1].set_xlabel("Pressure (Pa)")
    ax[1, 1].set_title("Solar Efficiency Vs. LP Turbine Outlet Pressure", fontsize=13)

    # Exergy Efficiency Plot
    ax[1, 0].plot([x / 1000 for x in pressure_values], percentage(exergy_efficiency_values), linewidth=2)
    ax[1, 0].set_ylabel("Exergy (%)")
    ax[1, 0].set_xlabel("Pressure (Pa)")
    ax[1, 0].set_title("Exergy Vs. LP Turbine Outlet Pressure", fontsize=13)

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
    ax[0, 0].set_title("Power Output Vs. LP Turbine Outlet Pressure", fontsize=13)

    # Efficiency Plot
    ax[0, 1].plot([x / 1000 for x in reheat_fraction_values], percentage(efficiency_values), linewidth=2)
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Pressure (Pa)")
    ax[0, 1].set_title("Efficiency Vs. LP Turbine Outlet Pressure", fontsize=13)

    # Solar Efficiency Plot
    ax[1, 1].plot([x / 1000 for x in reheat_fraction_values], percentage(solar_efficiency_values), linewidth=2)
    ax[1, 1].set_ylabel("Efficiency (%)")
    ax[1, 1].set_xlabel("Pressure (Pa)")
    ax[1, 1].set_title("Solar Efficiency Vs. LP Turbine Outlet Pressure", fontsize=13)

    # Exergy Efficiency Plot
    ax[1, 0].plot([x / 1000 for x in reheat_fraction_values], percentage(exergy_efficiency_values), linewidth=2)
    ax[1, 0].set_ylabel("Exergy (%)")
    ax[1, 0].set_xlabel("Pressure (Pa)")
    ax[1, 0].set_title("Exergy Vs. LP Turbine Outlet Pressure", fontsize=13)

    ax[0, 0].grid(True)
    ax[0, 1].grid(True)
    ax[1, 0].grid(True)
    ax[1, 1].grid(True, alpha=0.3)

    fig.suptitle(
        "Effect of LP Turbine Outlet Pressure on System Performance",
        fontsize=16,
        fontweight="bold"
    )

    pyplot.tight_layout()
    pyplot.show()

def plotting_condenser_secondary_2():
    temperature_values = np.linspace(0.05, 0.5, 70)
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for temperature in temperature_values:
        results = solve_configuration2(T_field_out=temperature, hourly=False, print_results=False)
        power_values.append(results["P_net"])
        efficiency_values.append(results["efficiency"])
        solar_efficiency_values.append(results["solar_efficiency"])
        exergy_efficiency_values.append(results["efficiency_II"])

    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))
    # Power plot
    ax[0, 0].plot([x / 1000 for x in temperature_values], power_values, linewidth=2)
    ax[0, 0].set_ylabel("Power (W)")
    ax[0, 0].set_xlabel("Pressure (Pa)")
    ax[0, 0].set_title("Power Output Vs. LP Turbine Outlet Pressure", fontsize=13)

    # Efficiency Plot
    ax[0, 1].plot([x / 1000 for x in temperature_values], percentage(efficiency_values), linewidth=2)
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Pressure (Pa)")
    ax[0, 1].set_title("Efficiency Vs. LP Turbine Outlet Pressure", fontsize=13)

    # Solar Efficiency Plot
    ax[1, 1].plot([x / 1000 for x in temperature_values], percentage(solar_efficiency_values), linewidth=2)
    ax[1, 1].set_ylabel("Efficiency (%)")
    ax[1, 1].set_xlabel("Pressure (Pa)")
    ax[1, 1].set_title("Solar Efficiency Vs. LP Turbine Outlet Pressure", fontsize=13)

    # Exergy Efficiency Plot
    ax[1, 0].plot([x / 1000 for x in temperature_values], percentage(exergy_efficiency_values), linewidth=2)
    ax[1, 0].set_ylabel("Exergy (%)")
    ax[1, 0].set_xlabel("Pressure (Pa)")
    ax[1, 0].set_title("Exergy Vs. LP Turbine Outlet Pressure", fontsize=13)

    ax[0, 0].grid(True)
    ax[0, 1].grid(True)
    ax[1, 0].grid(True)
    ax[1, 1].grid(True, alpha=0.3)

    fig.suptitle(
        "Effect of LP Turbine Outlet Pressure on System Performance",
        fontsize=16,
        fontweight="bold"
    )

    pyplot.tight_layout()
    pyplot.show()



def _solve_single_point(args):
    """Worker function — must be top-level (picklable) for multiprocessing."""
    HP_pressure, LP_pressure = args
    results = solve_configuration2(
        p_hp_exhaust_secondary=HP_pressure,
        p_condenser_secondary=LP_pressure,
        hourly=False,
        print_results=False
    )
    return (
        results["P_net"],
        results["efficiency"],
        results["solar_efficiency"],
        results["efficiency_II"],
    )


def plotting_HP_LP_Turbine_outlets_2():
    HP_pressure_values = np.linspace(5e5, 3e5, 70)
    LP_pressure_values = np.linspace(2e5, 0.9e5, 70)

    # Build every (HP, LP) combination as a flat list of tuples
    # Order matches nested loop: LP outer, HP inner
    grid_points = [
        (HP, LP)
        for LP in LP_pressure_values
        for HP in HP_pressure_values
    ]

    # Run solves in parallel across available cores
    with Pool(processes=max(cpu_count() - 1, 1)) as pool:
        raw_results = pool.map(_solve_single_point, grid_points)

    # Unpack and reshape into proper 2D grids: shape (len(LP), len(HP))
    n_lp, n_hp = len(LP_pressure_values), len(HP_pressure_values)
    power_values = np.array([r[0] for r in raw_results]).reshape(n_lp, n_hp)
    efficiency_values = np.array([r[1] for r in raw_results]).reshape(n_lp, n_hp)
    solar_efficiency_values = np.array([r[2] for r in raw_results]).reshape(n_lp, n_hp)
    exergy_efficiency_values = np.array([r[3] for r in raw_results]).reshape(n_lp, n_hp)

    fig, ax = pyplot.subplots(2, 2, figsize=(12, 12))

    power_plot = ax[0, 0].contourf(LP_pressure_values, HP_pressure_values, power_values, cmap=cm.viridis)
    ax[0, 0].set_ylabel("HP turbine outlet pressure (Pa)")
    ax[0, 0].set_xlabel("LP turbine outlet Pressure (Pa)")
    ax[0, 0].set_title("Power Output Vs. Secondary LP and HP Turbine Outlet Pressure", fontsize=13)
    cbar_1 = pyplot.colorbar(power_plot, ax=ax[0, 0], cmap=cm.viridis)
    cbar_1.set_label("Power (W)")

    efficiency_plot = ax[0, 1].contourf(LP_pressure_values, HP_pressure_values, efficiency_values, cmap=cm.viridis)
    ax[0, 1].set_ylabel("HP turbine outlet pressure (Pa)")
    ax[0, 1].set_xlabel("LP turbine outlet Pressure (Pa)")
    ax[0, 1].set_title("Efficiency Vs. Secondary LP and HP Turbine Outlet Pressure", fontsize=13)
    cbar_2 = pyplot.colorbar(efficiency_plot, ax=ax[0, 1], cmap=cm.viridis)
    cbar_2.set_label("Efficiency (%)")

    solar_efficiency_plot = ax[1, 1].contourf(LP_pressure_values, HP_pressure_values, solar_efficiency_values, cmap=cm.viridis)
    ax[1, 1].set_ylabel("HP turbine outlet pressure (Pa)")
    ax[1, 1].set_xlabel("LP turbine outlet Pressure (Pa)")
    ax[1, 1].set_title("Solar Efficiency Vs. Secondary LP and HP Turbine Outlet Pressure", fontsize=13)
    cbar_3 = pyplot.colorbar(solar_efficiency_plot, ax=ax[1, 1], cmap=cm.viridis)
    cbar_3.set_label("Solar Efficiency (%)")

    exergy_plot = ax[1, 0].contourf(LP_pressure_values, HP_pressure_values, exergy_efficiency_values, cmap=cm.viridis)
    ax[1, 0].set_ylabel("HP turbine outlet pressure (Pa)")
    ax[1, 0].set_xlabel("LP turbine outlet Pressure (Pa)")
    ax[1, 0].set_title("Exergy Vs. Secondary LP and HP Turbine Outlet Pressure", fontsize=13)
    cbar_4 = pyplot.colorbar(exergy_plot, ax=ax[1, 0], cmap=cm.viridis)
    cbar_4.set_label("Exergy (%)")

    ax[0, 0].grid(True)
    ax[0, 1].grid(True)
    ax[1, 0].grid(True)
    ax[1, 1].grid(True, alpha=0.3)

    Title = "Effect of Secondary LP and HP Turbine Outlet Pressure on System Performance"
    fig.suptitle(Title, fontsize=16, fontweight="bold")

    pyplot.tight_layout()
    pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches='tight')  # save BEFORE show
    pyplot.show()

def plotting_ttd_u_2():
    pressure_values = np.linspace(7e3, 0.45e4, 50)
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
    ax[0, 0].plot([x / 1000 for x in pressure_values], power_values, linewidth=2)
    ax[0, 0].set_ylabel("Power (W)")
    ax[0, 0].set_xlabel("Terminal Temperature Difference (K)")
    ax[0, 0].set_title("Power Output Vs. Feedwater Heater Terminal Temperature Difference (K)", fontsize=13)

    # Efficiency Plot
    ax[0, 1].plot([x / 1000 for x in pressure_values], percentage(efficiency_values), linewidth=2)
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Terminal Temperature Difference (K)")
    ax[0, 1].set_title("Efficiency Vs. Feedwater Heater Terminal Temperature Difference (K)", fontsize=13)

    # Solar Efficiency Plot
    ax[1, 1].plot([x / 1000 for x in pressure_values], percentage(solar_efficiency_values), linewidth=2)
    ax[1, 1].set_ylabel("Efficiency (%)")
    ax[1, 1].set_xlabel("Terminal Temperature Difference (K)")
    ax[1, 1].set_title("Solar Efficiency Vs. Feedwater Heater Terminal Temperature Difference (K)", fontsize=13)

    # Exergy Efficiency Plot
    ax[1, 0].plot([x / 1000 for x in pressure_values], percentage(exergy_efficiency_values), linewidth=2)
    ax[1, 0].set_ylabel("Exergy (%)")
    ax[1, 0].set_xlabel("Terminal Temperature Difference (K)")
    ax[1, 0].set_title("Exergy Vs. Feedwater Heater Terminal Temperature Difference (K)", fontsize=13)

    ax[0, 0].grid(True)
    ax[0, 1].grid(True)
    ax[1, 0].grid(True)
    ax[1, 1].grid(True, alpha=0.3)

    Title = "Effect of Terminal Temperature Difference on System Performance"
    fig.suptitle(
        Title,
        fontsize=16,
        fontweight="bold"
    )

    pyplot.tight_layout()
    pyplot.show()
    pyplot.savefig(fr"ModelResults\{Title}", dpi=150, bbox_inches='tight')

def plotting_Q_design_thermal():
    pass


if __name__ == "__main__":
    #plotting_p_nuclear_condenser_2()
    plotting_HP_LP_Turbine_outlets_2()