import components
from tespy.networks import Network
from tespy.components import (Compressor,Condenser, HeatExchanger,
                              SimpleHeatExchanger,Turbine,Splitter,
                              Merge)

AP1000_plant = Network()
#Components
# HP Turbine block
HP_turbine_stg_1 = Turbine('HP Turbine Stage 1')
Spliter_stg_1 = Splitter('Spliter Stage 1')
HP_turbine_stg_2 = Turbine('HP Turbine Stage 2')
Spliter_stg_2 = Splitter('Spliter Stage 2')
HP_turbine_stg_3 = Turbine('HP Turbine Stage 3')
Spliter_stg_3 = Splitter('Spliter Stage 3')
HP_turbine_stg_4 = Turbine('HP Turbine Stage 4')
Spliter_stg_4 = Splitter('Spliter Stage 4')
HP_turbine_stg_5 = Turbine('HP Turbine Stage 5')
Spliter_stg_5 = Splitter('Spliter Stage 5')

# Interstage heat block


# LP Turbine block
LP_turbine_stg_1 = Turbine('LP Turbine Stage 1')

LP_turbine_stg_2 = Turbine('LP Turbine Stage 2')
LP_spliter_stg_1 = Splitter('LP Spliter Stage 1')

LP_turbine_stg_3 = Turbine('LP Turbine Stage 3')
LP_spliter_stg_2 = Splitter('LP Spliter Stage 2')




# Condenser

# LP heaters

# HP


dearator = Merge('Dearator')

# Setup
AP1000_plant.units.set_defaults(
    temperature="K",
    pressure="bar",
    pressure_difference="bar",
    enthalpy="J/kg",
    heat="W",
    power="W",
)
#1 Primary Loop: Reactor and NaK loop



#2 Steam generator
#Take the heat input from the previous step and we kno the steam generator cold stream output
#The cold stream output can be a design parameter


#Seperate into 2 streams

#3.1 One stream going to the turbines
#Ouput will be the streams leaving the turbines

# Those stream objects will go to the interstage
# And stream objects will be used in the feed water heater

#Power should be calculated here


#3.2 Other stream going to the interstage heater(This is where one of the configuration will interface)

#4 Streams going to the next stage of turbines


#5 Generator no thermodynamics here: just calculate power
# Power should be calculated here too


#6 Condenser comes next (This is where one of the configuration will interface)

#7 Heater

#8 Deaerator

#9 Heater
# The output can come from step one
