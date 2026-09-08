from Configuration_1 import solve_configuration1
from Configuration_2 import solve_configuration2

solve_configuration1()





#Config 2 study
solve_configuration2()
#Plot :
#   Bar graphs of working fluids
#   p_nuclear condenser
#   p_evaporatpr_secondary
#   reheat fraction
#   T_field_out
#   p_condenser_secondary



# Recommended metric set per sweep point
# Net power output (P_net, already in your log)
# First-law (thermal) efficiency — your existing step["efficiency"] calculation, kept as the baseline/comparable metric against Andasol-1 and AP1000 standalone
# Second-law (exergy) efficiency — worth adding, since it directly supports the "waste heat is low-grade, CSP top-up upgrades it" narrative that's central to Configuration 2's novelty
# Solar-specific incremental efficiency — extra net power generated per unit of solar thermal input added (isolates whether the CSP contribution itself is being used well, independent of the fixed nuclear baseline)

def plotting_fluids():

    pass
