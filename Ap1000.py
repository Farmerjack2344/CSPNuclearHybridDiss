import components
from tespy.networks import Network
from tespy.components import (Compressor, Condenser, HeatExchanger, Turbine, Splitter,
                              Merge, CycleCloser, Drum, Source, Sink, Pump, DropletSeparator)
from tespy.components.power.generator import Generator
from tespy.connections import Connection



AP1000_plant = Network()
#Components
cycle_closer = CycleCloser("cycle closer")
# Steam generator
reactor_out = Source('Reactor Out')
reactor_in = Sink('Reactor In')

steam_generator = HeatExchanger('Steam Generator')

pre_turbine_split = Splitter('Pre-Turbine Split', num_out=2)

# HP Turbine block
HP_turbine_stg_1 = Turbine('HP Turbine Stage 1')
Spliter_stg_1 = Splitter('Spliter Stage 1', num_out=2)

HP_turbine_stg_2 = Turbine('HP Turbine Stage 2')
Spliter_stg_2 = Splitter('Spliter Stage 2', num_out=2)

HP_turbine_stg_3 = Turbine('HP Turbine Stage 3')
Spliter_stg_3 = Splitter('Spliter Stage 3', num_out=2)

HP_turbine_stg_4 = Turbine('HP Turbine Stage 4')
Spliter_stg_4 = Splitter('Spliter Stage 4', num_out=2)

# HP_turbine_stg_5 = Turbine('HP Turbine Stage 5')
# Spliter_stg_5 = Splitter('Spliter Stage 5', num_out=2)

# Interstage superheater block
#HeatExchanger - 2 IN and 2 OUT
#SimpleHeatExchanger - 1 IN and 1 OUT
moisture_seperator_heater = DropletSeparator("Moisture Seperator Heater")

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
cooling_pump = Pump('Cooling Pump')

condenser = Condenser('Condenser')




# LP heaters
#Combine the steam(from the low pressure turbine) and some of the condensate from the condenser - This will go into the shell
#What comes out of the shell will be combined with another turbines exhaust

#HeatExchanger - 2 IN and 2 OUT
#SimpleHeatExchanger - 1 IN and 1 OUT
LP_feedwater_pump = Pump('LP Feedwater Pump')

LP_feedwater_heater_stg1 = HeatExchanger('LP Feedwater Heater 1')
LP_feedwater_heater_stg2 = HeatExchanger('LP Feedwater Heater 2')
LP_feedwater_heater_stg3 = HeatExchanger('LP Feedwater Heater 3')
LP_feedwater_heater_stg4 = HeatExchanger('LP Feedwater Heater 4')# Last stage is a normal 2 in and 2 out
# The extra line is just to a pump
LP_heater_merge_stg1 = Merge('LP Heater Merge 1', num_in=2)
LP_heater_merge_stg2 = Merge('LP Heater Merge 2', num_in=2)
LP_heater_merge_stg3 = Merge('LP Heater Merge 3', num_in=2)
LP_heater_merge_stg4 = Merge('LP Heater Merge 4', num_in=2)

dearator = Merge('Deaerator', num_in=3)

# HP Heaters
HP_feedwater_pump = Pump('HP Feedwater Pump')
HP_feedwater_heater_stg1 = HeatExchanger('HP Feedwater Heater 1')
HP_feedwater_heater_stg2 = HeatExchanger('HP Feedwater Heater 2')



# Setup
AP1000_plant.units.set_defaults(
    temperature="K",
    pressure="Pa",
    pressure_difference="Pa",
    enthalpy="J/kg",
    heat="W",
    power="W",
)

#Connections
#c = Connection(Component A, "Component A's port", Component B, "Component B's port", label)
#1/2 Primary Loop: Reactor and NaK loop and Steam generator
## in1/out1 = hot side, in2/out2 = cold side

#Take the heat input from the previous step and we kno the steam generator cold stream output
#The cold stream output can be a design parameter

#Coolant into the SG
c1 =  Connection(reactor_out, "out1", steam_generator, "in1",label = "primary_in")
#Coolant out of SG
c2 =  Connection(steam_generator, "out1", reactor_in, "in1",label="primary out")

#Working fluid into SG
c_fw = Connection(HP_feedwater_heater_stg2, "out1", steam_generator, "in2", label="feedwater_in")


#Seperate into 2 streams
#Working fluid out of SG
c3 =  Connection(steam_generator, "out2", pre_turbine_split, "in1",label="secondary out")


#3.1 One stream going to the stage 2 interstage heater

c4 = Connection(pre_turbine_split,"out1", interstage_heater_2, "in1", label="Initial bleed")


#3.2 On stream going to the turbine
c5  = Connection(pre_turbine_split, "out2", HP_turbine_stg_1, "in1",
                 label="Stream into the first turbine stage")

#4 Streams going to the next stage of turbines
c6 = Connection(HP_turbine_stg_1,'out1', Spliter_stg_1, "in1",
                 label="HP Turbine stage 0")

c7 = Connection(Spliter_stg_1, "out1", HP_turbine_stg_2, "in1", label="HP Turbine stage 1")
c7_1 = Connection(Spliter_stg_1, "out2", interstage_heater_1, "in1", label="Interstage heater stage 1")

c8 = Connection(HP_turbine_stg_2, "out2", Spliter_stg_2, "in1", label="HP Turbine stage 2")

c9 = Connection(Spliter_stg_2, "out1", HP_turbine_stg_3, "in1", label="HP Turbine stage 3")
c9_1 = Connection(Spliter_stg_2, "out2", HP_feedwater_heater_stg2, "in1", label="HP feedwater heater stage 2")

c10 = Connection(HP_turbine_stg_3, "out1", Spliter_stg_3, "in1",label="HP Turbine stage 4")

c11 = Connection(Spliter_stg_3, "out1", HP_turbine_stg_4, "in1", label="HP Turbine stage 5")
c11_1 = Connection(Spliter_stg_3, "out2", HP_feedwater_heater_stg1, "in1", label="HP feedwater heater stage 1")

c12 = Connection(HP_turbine_stg_4, "out1", Spliter_stg_4, "in1", label="HP Turbine stage 6")



#Interstage Heaters
c13 = Connection(Spliter_stg_4, "out1", moisture_seperator_heater, "in1", label="Moisture seperator heater")
c14 = Connection(Spliter_stg_4, "out2", dearator, "in1", label="Dearator")

#For moisture seperator out1 is liquid and out 2 is vapour
c15 = Connection(moisture_seperator_heater,"out2", interstage_heater_1, "in2", label="Interstage heater 1")
c16 = Connection(moisture_seperator_heater, "out1", LP_heater_merge_stg3, "in1",
                 label="LP feedwater heater stage 3")

c17 = Connection(interstage_heater_1, "out1", interstage_heater_2, "in2", label="Interstage heater stage 2")
c18 = Connection(interstage_heater_1, "out2", interstage_merge, "in1", label="Interstage merge 1")

c19 = Connection(interstage_heater_2, "out1", LP_turbine_stg_1, "in1", label="LP turbine stage 1")
c20 = Connection(interstage_heater_2, "out2", interstage_merge, "in2", label="Interstage merge 2")

c21 = Connection(interstage_merge, "out1", LP_heater_merge_stg4, "in1",
                 label="LP interstage merge into stage 4")

#5 Low pressure Turbines
c22 = Connection(LP_turbine_stg_1, "out1", LP_spliter_stg_1, "in1", label="LP spliter stage 1")

c23 = Connection(LP_spliter_stg_1, "out1", LP_turbine_stg_2, "in1", label="LP turbine stage 2 En")
c24 = Connection(LP_spliter_stg_1, "out2", LP_heater_merge_stg4, "in2", label="LP heater stage 4 En")


c25 = Connection(LP_turbine_stg_2, "out1", LP_spliter_stg_2, "in1", label="LP turbine stage 2 Ex")

c26 = Connection(LP_spliter_stg_2, "out1", LP_turbine_stg_3, "in1", label="LP turbine stage 3 En")
c27 = Connection(LP_spliter_stg_2, "out2", LP_heater_merge_stg3, "in2", label="LP turbine stage 3 En")



#6 Power bus connections

#7 Condenser comes next (This is where one of the configuration will interface)

#8 Heater

#9 Deaerator

#10 Heater
# The output can come from step one
