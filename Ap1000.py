import components
from tespy.networks import Network
from tespy.components import (Compressor,Condenser, HeatExchanger,
                              SimpleHeatExchanger,Turbine,Splitter,
                              Merge)


#Components
# HP Turbine block


# Interstage heat block


# LP Turbine block


# Condenser

# LP heaters

# HP


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
