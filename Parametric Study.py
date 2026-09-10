from envs.matlab_env.Lib.unittest import result
from matplotlib import pyplot

from Configuration_1 import solve_configuration1
from Configuration_2 import solve_configuration2



import numpy as np
import matplotlib.pyplot as plt
solve_configuration1()
#TODO: find what I need to plot




#Config 2 study
solve_configuration2()
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
        results = solve_configuration2(secondary_fluid=fluid,hourly=False)
        power_values.append(results["P_net"])
        efficiency_values.append(results["efficiency"])
        solar_efficiency_values.append(results["solar_efficiency"])


    fig, ax = pyplot.subplots(2,2)
    power_plot = ax[0,0]


#TODO: Plot the above, maybe using mat plot lib plotting efficiency/power against variable
def plotting_p_nuclear_condenser():
    # The pressure coming out of the turbine
    p_array = np.linspace( 0.4e5,2.5e5, 300)
def plotting_evaporator_secondary():
    pass

def plotting_reheat_fraction():
    #probably 50 to 95%
    pass

def plotting_T_field_out():
    pass

def plotting_condenser_secondary():
    pass
