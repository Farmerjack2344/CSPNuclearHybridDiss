from envs.matlab_env.Lib.unittest import result
from matplotlib import pyplot

from Configuration_1 import solve_configuration1
from Configuration_2 import solve_configuration2



import numpy as np
import matplotlib.pyplot as plt
#solve_configuration1()
#TODO: find what I need to plot




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

def plotting_fluids():
    list_of_fluids = ["ISOPENTANE", "ISOBUTANE", "HEXAMETHYLDISILOXANE", "CYCLOPENTANE", "R1233ZDE", "R245fa"]
    fluids = [{x:1} for x in list_of_fluids]
    #TODO: Fill this in with fluids and then bar chart to find most efficient/power
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for fluid in fluids:
        results = solve_configuration2(secondary_fluid=fluid,hourly=False, print_results=False)
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


def plotting_p_nuclear_condenser():
    # The pressure coming out of the turbine
    pressure_values = np.linspace( 7e3,0.5e4, 50)
    power_values = []
    efficiency_values = []
    solar_efficiency_values = []
    exergy_efficiency_values = []
    for pressure in pressure_values:
        results = solve_configuration2(p_nuclear_condenser=pressure, hourly=False,print_results=False)
        power_values.append(results["P_net"])
        efficiency_values.append(results["efficiency"])
        solar_efficiency_values.append(results["solar_efficiency"])
        exergy_efficiency_values.append(results["efficiency_II"])

    fig, ax = pyplot.subplots(2, 2)
    # Power plot
    ax[0, 0].plot(pressure_values, power_values)
    ax[0, 0].set_ylabel("Power (W)")
    ax[0, 0].set_xlabel("Pressure (Pa)")
    ax[0,0].set_title("Power Output Vs. LP Turbine Outlet Pressure")

    # Efficiency Plot
    ax[0, 1].plot(pressure_values, efficiency_values)
    ax[0, 1].set_ylabel("Efficiency (%)")
    ax[0, 1].set_xlabel("Pressure (Pa)")
    ax[0, 1].set_title("Efficiency Vs. LP Turbine Outlet Pressure")

    # Solar Efficiency Plot
    ax[1, 1].plot(pressure_values, solar_efficiency_values)
    ax[1, 1].set_ylabel("Efficiency (%)")
    ax[1, 1].set_xlabel("Fluid")
    ax[1, 1].set_title("Solar Efficiency Vs. LP Turbine Outlet Pressure")

    # Exergy Efficiency Plot
    ax[1, 0].plot(pressure_values, exergy_efficiency_values)
    ax[1, 0].set_ylabel("Exergy (%)")
    ax[1, 0].set_xlabel("Fluid")
    ax[1, 0].set_title("Exergy Vs. LP Turbine Outlet Pressure")

    pyplot.tight_layout()
    pyplot.show()

def plotting_evaporator_secondary():
    pass

def plotting_reheat_fraction():
    #probably 50 to 95%
    pass

def plotting_T_field_out():
    pass

def plotting_condenser_secondary():
    pass


plotting_p_nuclear_condenser()