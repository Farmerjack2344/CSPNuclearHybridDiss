import components
from tespy.networks import Network
from tespy.components import (Compressor, Condenser, HeatExchanger, Turbine, Splitter,
                              Merge, CycleCloser, Drum, Source, Sink)
from tespy.components.power.generator import Generator

AP1000_plant = Network()
#Components
cycle_closer = CycleCloser("cycle closer")
# Steam generator
reactor_in = Source('Reactor In')
reactor_out = Sink('Reactor Out')

steam_generator = HeatExchanger('Steam Generator')

# HP Turbine block
HP_turbine_stg_1 = Turbine('HP Turbine Stage 1')
Spliter_stg_1 = Splitter('Spliter Stage 1', num_out=2)
HP_turbine_stg_2 = Turbine('HP Turbine Stage 2')
Spliter_stg_2 = Splitter('Spliter Stage 2', num_out=2)
HP_turbine_stg_3 = Turbine('HP Turbine Stage 3')
Spliter_stg_3 = Splitter('Spliter Stage 3', num_out=2)
HP_turbine_stg_4 = Turbine('HP Turbine Stage 4')
Spliter_stg_4 = Splitter('Spliter Stage 4', num_out=2)
HP_turbine_stg_5 = Turbine('HP Turbine Stage 5')
Spliter_stg_5 = Splitter('Spliter Stage 5', num_out=2)

# Interstage superheater block
#HeatExchanger - 2 IN and 2 OUT
#SimpleHeatExchanger - 1 IN and 1 OUT
moisture_seperator_heater = Drum("Moisture Seperator Heater")

interstage_heater_1 = HeatExchanger('Interstage Heater 1')
interstage_heater_2 = HeatExchanger('Interstage Heater 2')

interstage_merge = Merge('Interstage Merge',num_in=2)


# LP Turbine block
LP_turbine_stg_1 = Turbine('LP Turbine Stage 1')
LP_spliter_stg_1 = Splitter('LP Spliter Stage 1', num_out=2)

LP_turbine_stg_2 = Turbine('LP Turbine Stage 2')
LP_spliter_stg_2 = Splitter('LP Spliter Stage 2', num_out=2)

LP_turbine_stg_3 = Turbine('LP Turbine Stage 3')
LP_spliter_stg_3 = Splitter('LP Spliter Stage 3', num_out=2)

LP_turbine_stg_4 = Turbine('LP Turbine Stage 4')
LP_spliter_stg_4 = Splitter('LP Spliter Stage 4', num_out=2)

LP_turbine_stg_5 = Turbine('LP Turbine Stage 5')

#Generator
generator = Generator('Generator')


# Condenser


## Cooling water
cooling_water_in = Source('Cooling Water In')
cooling_water_out = Sink('Cooling Water Out')


# LP heaters
#Combine the steam(from the low pressure turbine) and some of the condensate from the condenser - This will go into the shell
#What comes out of the shell will be combined with another turbines exhaust

#HeatExchanger - 2 IN and 2 OUT
#SimpleHeatExchanger - 1 IN and 1 OUT

LP_feedwater_heater_stg1 = HeatExchanger('LP Feedwater Heater 1')
LP_feedwater_heater_stg2 = HeatExchanger('LP Feedwater Heater 2')
LP_feedwater_heater_stg3 = HeatExchanger('LP Feedwater Heater 3')

LP_feedwater_heater_stg4 = HeatExchanger('LP Feedwater Heater 4')# Last stage is a normal 2 in and 2 out
# The extra line is just to a pump


# HP Heaters
HP_feedwater_heater_stg1 = HeatExchanger('HP Feedwater Heater 1')
HP_feedwater_heater_stg2 = HeatExchanger('HP Feedwater Heater 2')
HP_feedwater_heater_stg3 = HeatExchanger('HP Feedwater Heater 3')
HP_feedwater_heater_stg4 = HeatExchanger('HP Feedwater Heater 4')


dearator = Merge('Dearator', num_in=3)

# Setup
AP1000_plant.units.set_defaults(
    temperature="K",
    pressure="bar",
    pressure_difference="bar",
    enthalpy="J/kg",
    heat="W",
    power="W",
)

#Connections
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
