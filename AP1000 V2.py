import components
from tespy.networks import Network
from tespy.components import (Compressor, Condenser, HeatExchanger, Turbine, Splitter,
                              Merge, CycleCloser, Drum, Source, Sink, Pump, DropletSeparator,
                              PowerBus, PowerSink, Motor, SteamTurbine, Valve
                              )
from tespy.components.power.generator import Generator
from tespy.connections import Connection, PowerConnection

#Use TTD

coolant = {"water":1}
working_fluid = {"water":1}
cooling_fluid = {"water":1}

from components import Deareator

AP1000_plant = Network()
#Components
cycle_closer = CycleCloser("cycle closer")
# Steam generator
reactor_out = Source('Reactor Out')
reactor_in = Sink('Reactor In')

steam_generator = HeatExchanger('Steam Generator')#
ms_drain_valve = Valve("MS Drain Valve")

pre_turbine_split = Splitter('Pre-Turbine Split', num_out=2)

# HP Turbine block
HP_turbine_stg_1 = SteamTurbine('HP Turbine Stage 1')
Splitter_stg_1 = Splitter('Spliter Stage 1', num_out=2)

HP_turbine_stg_2 = SteamTurbine('HP Turbine Stage 2')
Splitter_stg_2 = Splitter('Spliter Stage 2', num_out=2)

HP_turbine_stg_3 = SteamTurbine('HP Turbine Stage 3')
Splitter_stg_3 = Splitter('Spliter Stage 3', num_out=2)

HP_turbine_stg_4 = SteamTurbine('HP Turbine Stage 4')
Splitter_stg_4 = Splitter('Spliter Stage 4', num_out=3)

# HP_turbine_stg_5 = Turbine('HP Turbine Stage 5')
# Spliter_stg_5 = Splitter('Spliter Stage 5', num_out=2)

# Interstage superheater block
#HeatExchanger - 2 IN and 2 OUT
#SimpleHeatExchanger - 1 IN and 1 OUT
moisture_seperator_heater = DropletSeparator("Moisture Seperator Heater")

interstage_heater_1 = HeatExchanger('Interstage Heater 1')
interstage_heater_2 = HeatExchanger('Interstage Heater 2')

interstage_merge = Merge('Interstage Merge',num_in=3)


# LP Turbine block
LP_turbine_stg_1 = SteamTurbine('LP Turbine Stage 1')
LP_splitter_stg_1 = Splitter('LP Spliter Stage 1', num_out=2)

LP_turbine_stg_2 = SteamTurbine('LP Turbine Stage 2')
LP_splitter_stg_2 = Splitter('LP Spliter Stage 2', num_out=2)

LP_turbine_stg_3 = SteamTurbine('LP Turbine Stage 3')
LP_splitter_stg_3 = Splitter('LP Spliter Stage 3', num_out=2)

LP_turbine_stg_4 = SteamTurbine('LP Turbine Stage 4')
LP_splitter_stg_4 = Splitter('LP Spliter Stage 4', num_out=2)

LP_turbine_stg_5 = Turbine('LP Turbine Stage 5')

#Generator
turbines = [LP_turbine_stg_1, LP_turbine_stg_2, LP_turbine_stg_3, LP_turbine_stg_4, LP_turbine_stg_5,
            HP_turbine_stg_1, HP_turbine_stg_2, HP_turbine_stg_3, HP_turbine_stg_4]

mechanical_bus = PowerBus("Mechanical Bus ", num_in=9,num_out=1)
generator = Generator('Generator')

turbine_power_conns = [
    PowerConnection(turb, "power", mechanical_bus, f"power_in{i+1}", label=f"turb_power_{i+1}")
    for i, turb in enumerate(turbines)
]

# Mechanical bus -> Generator
e_gen_in = PowerConnection(mechanical_bus, "power_out1", generator, "power_in", label="mech_to_gen")

# --- Electrical bus: generator feeds it, motors + grid draw from it ---
electrical_bus = PowerBus("Electrical Bus", num_in=1, num_out=3)


# Motors driving your three pumps
lp_fw_pump_motor = Motor("LP Feedwater Pump Motor")
hp_fw_pump_motor = Motor("HP Feedwater Pump Motor")

generator.set_attr(eta=0.985)
lp_fw_pump_motor.set_attr(eta=0.95)
hp_fw_pump_motor.set_attr(eta=0.95)

grid = PowerSink("Grid")



# Condenser
## Cooling water
cooling_water_in = Source('Cooling Water In')
cooling_water_out = Sink('Cooling Water Out')


condenser = Condenser('Condenser')


condenser_merger = Merge('Condenser Merger', num_in=2)

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
LP_heater_merge_stg3 = Merge('LP Heater Merge 3', num_in=3)
LP_heater_merge_stg4 = Merge('LP Heater Merge 4', num_in=2)

dearator = Merge('Deaerator', num_in=3)

# HP Heaters
HP_feedwater_pump = Pump('HP Feedwater Pump')
HP_feedwater_merger = Merge('HP Feedwater Merger', num_in=2)
HP_feedwater_heater_stg1 = HeatExchanger('HP Feedwater Heater 1')
HP_feedwater_heater_stg2 = HeatExchanger('HP Feedwater Heater 2')

#Valves
hp_crossover_valve = Valve("HP Crossover to LP FWH4 Valve")
is1_drain_valve = Valve("Interstage 1 Drain Valve")
is2_drain_valve = Valve("Interstage 2 Drain Valve")
fwh4_drain_valve = Valve("FWH4 Drain Valve")
fwh3_drain_valve = Valve("FWH3 Drain Valve")
fwh2_drain_valve = Valve("FWH2 Drain Valve")
fwh1_drain_valve = Valve("FWH1 Drain Valve")
hp_fwh2_drain_valve = Valve("HP FWH2 Drain Valve")
hp_fwh1_drain_valve = Valve("HP FWH1 Drain Valve")



# Setup
AP1000_plant.units.set_defaults(
    temperature="K",
    pressure="Pa",
    pressure_difference="Pa",
    enthalpy="J/kg",
    heat="W",
    power="W",
    mass_flow="kg/s"
)

#Connections
#c = Connection(Component A, "Component A's port", Component B, "Component B's port", label)
#1/2 Primary Loop: Reactor and NaK loop and Steam generator
## in1/out1 = hot side, in2/out2 = cold side

#Take the heat input from the previous step and we kno the steam generator cold stream output
#The cold stream output can be a design parameter

#Coolant into the SG
c1 =  Connection(reactor_out, "out1", steam_generator, "in1",
                 label = "primary_in")

#Coolant out of SG
c2 =  Connection(steam_generator, "out1", reactor_in, "in1",
                 label="primary out")

#Working fluid into SG
c_fw1 = Connection(HP_feedwater_heater_stg2, "out2", cycle_closer, "in1",
                    label="Feedwater to cycle closer")
c_fw2 = Connection(cycle_closer, "out1", steam_generator, "in2",
                    label="Cycle closer to feedwater_in")

#Seperate into 2 streams
c3 =  Connection(steam_generator, "out2", pre_turbine_split, "in1",
                 label="secondary out")


#3.1 One stream going to the stage 2 interstage heater

c4 = Connection(pre_turbine_split,"out1", interstage_heater_2, "in1",
                label="Initial bleed")


#3.2 On stream going to the turbine
c5  = Connection(pre_turbine_split, "out2", HP_turbine_stg_1, "in1",
                 label="Stream into the first turbine stage")

#4 Streams going to the next stage of turbines
c6 = Connection(HP_turbine_stg_1,'out1', Splitter_stg_1, "in1",
                label="HP Turbine stage 0")

c7 = Connection(Splitter_stg_1, "out1", HP_turbine_stg_2, "in1",
                label="HP Turbine stage 1")
c7_1 = Connection(Splitter_stg_1, "out2", interstage_heater_1, "in1",
                  label="Interstage heater stage 1")

c8 = Connection(HP_turbine_stg_2, "out1", Splitter_stg_2, "in1",
                label="HP Turbine stage 2")

c9 = Connection(Splitter_stg_2, "out1", HP_turbine_stg_3, "in1",
                label="HP Turbine stage 3")
c9_1 = Connection(Splitter_stg_2, "out2", interstage_merge, "in3",
                  label="HP feedwater heater stage 2")

c10 = Connection(HP_turbine_stg_3, "out1", Splitter_stg_3, "in1",
                 label="HP Turbine stage 4")

c11 = Connection(Splitter_stg_3, "out1", HP_turbine_stg_4, "in1",
                 label="HP Turbine stage 5")
c11_1 = Connection(Splitter_stg_3, "out2", HP_feedwater_merger, "in1",
                   label="HP feedwater heater stage 1")

c12 = Connection(HP_turbine_stg_4, "out1", Splitter_stg_4, "in1",
                 label="HP Turbine stage 6")



#Interstage Heaters
c13 = Connection(Splitter_stg_4, "out1", moisture_seperator_heater, "in1",
                 label="Moisture seperator heater")
c14_1_in = Connection(Splitter_stg_4, "out3", hp_crossover_valve, "in1", label="HP crossover to valve")
c14_1_out = Connection(hp_crossover_valve, "out1", LP_heater_merge_stg4, "in1", label="Valve to LP FWH4")
c14 = Connection(Splitter_stg_4, "out2", dearator, "in1",
                 label="Dearator input 1")
c14_1 = Connection(Splitter_stg_4, "out3", LP_heater_merge_stg4, "in1",
                    label="HP crossover to LP FWH4")

#For moisture seperator out1 is liquid and out 2 is vapour
c15 = Connection(moisture_seperator_heater,"out2", interstage_heater_1, "in2",
                 label="Interstage heater 1")

c16_in = Connection(moisture_seperator_heater, "out1", ms_drain_valve, "in1", label="MS drain to valve")
c16_out = Connection(ms_drain_valve, "out1", LP_heater_merge_stg3, "in1", label="Valve to LP Merge 3")

c17 = Connection(interstage_heater_1, "out2", interstage_heater_2, "in2",
                 label="Interstage heater stage 2")
c18 = Connection(interstage_heater_1, "out1", interstage_merge, "in1",
                 label="Interstage merge 1")

c19 = Connection(interstage_heater_2, "out2", LP_turbine_stg_1, "in1",
                 label="LP turbine stage 1")

c20 = Connection(interstage_heater_2, "out1", interstage_merge, "in2",
                 label="Interstage merge 2")


c21 = Connection(interstage_merge, "out1", HP_feedwater_heater_stg2, "in1",
                 label="LP interstage merge into stage 4")

#5 Low pressure Turbines
c22 = Connection(LP_turbine_stg_1, "out1", LP_splitter_stg_1, "in1",
                 label="LP spliter stage 1")

c23 = Connection(LP_splitter_stg_1, "out1", LP_turbine_stg_2, "in1",
                 label="LP turbine stage 2 En")
c24 = Connection(LP_splitter_stg_1, "out2", LP_heater_merge_stg4, "in2",
                 label="LP heater stage 4 En")


c25 = Connection(LP_turbine_stg_2, "out1", LP_splitter_stg_2, "in1",
                 label="LP turbine stage 2 Ex")

c26 = Connection(LP_splitter_stg_2, "out1", LP_turbine_stg_3, "in1",
                 label="LP turbine stage 3 En")
c27 = Connection(LP_splitter_stg_2, "out2", LP_heater_merge_stg3, "in2",
                 label="LP heater stage 3 En")


c28 = Connection(LP_turbine_stg_3, "out1", LP_splitter_stg_3, "in1",
                 label="LP turbine stage 3 Ex")

c29 = Connection(LP_splitter_stg_3, "out1", LP_turbine_stg_4, "in1",
                 label="LP turbine stage 4 En")
c30 = Connection(LP_splitter_stg_3, "out2", LP_heater_merge_stg2, "in2",
                 label="LP heater stage 4 Ex")


c31 = Connection(LP_turbine_stg_4, "out1", LP_splitter_stg_4, "in1",
                 label="LP turbine stage 4 Ex")

c32 = Connection(LP_splitter_stg_4, "out1", LP_turbine_stg_5, "in1",
                 label="LP turbine stage 5 En")
c33 = Connection(LP_splitter_stg_4, "out2", LP_heater_merge_stg1, "in2",
                 label="LP turbine stage 5 Ex")

# Interstage drains
c18_in = Connection(interstage_heater_1, "out1", is1_drain_valve, "in1",
                    label="IS1 Drain to Valve")
c18_out = Connection(is1_drain_valve, "out1", interstage_merge, "in1",
                     label="Valve to IS Merge 1")
c20_in = Connection(interstage_heater_2, "out1", is2_drain_valve, "in1",
                    label="IS2 Drain to Valve")
c20_out = Connection(is2_drain_valve, "out1", interstage_merge, "in2",
                     label="Valve to IS Merge 2")

# LP cascaded drains
c52_in = Connection(LP_feedwater_heater_stg4, "out1", fwh4_drain_valve, "in1",
                    label="FWH4 Drain to Valve")
c52_out = Connection(fwh4_drain_valve, "out1", LP_heater_merge_stg3, "in3",
                     label="Valve to FWH3 Merge")
c49_in = Connection(LP_feedwater_heater_stg3, "out1", fwh3_drain_valve, "in1",
                    label="FWH3 Drain to Valve")
c49_out = Connection(fwh3_drain_valve, "out1", LP_heater_merge_stg2, "in1",
                     label="Valve to FWH2 Merge")
c50_in = Connection(LP_feedwater_heater_stg2, "out1", fwh2_drain_valve, "in1",
                    label="FWH2 Drain to Valve")
c50_out = Connection(fwh2_drain_valve, "out1", LP_heater_merge_stg1, "in1",
                     label="Valve to FWH1 Merge")
c40_in = Connection(LP_feedwater_heater_stg1, "out1", fwh1_drain_valve, "in1",
                    label="FWH1 Drain to Valve")
c40_out = Connection(fwh1_drain_valve, "out1", condenser_merger, "in2",
                     label="Valve to Condenser Merger")

# HP cascaded drains
c57_in = Connection(HP_feedwater_heater_stg2, "out1", hp_fwh2_drain_valve, "in1",
                    label="HP FWH2 Drain to Valve")
c57_out = Connection(hp_fwh2_drain_valve, "out1", HP_feedwater_merger, "in2",
                     label="Valve to HP FWH1 Merge")
c53_in = Connection(HP_feedwater_heater_stg1, "out1", hp_fwh1_drain_valve, "in1",
                    label="HP FWH1 Drain to Valve")
c53_out = Connection(hp_fwh1_drain_valve, "out1", dearator, "in3",
                     label="Valve to Deaerator")


#6 Power bus connections

e_lpfw_in = PowerConnection(
    electrical_bus, "power_out1",
    lp_fw_pump_motor, "power_in",
    label="elec_to_lpfw_motor"
)

e_lpfw_out = PowerConnection(
    lp_fw_pump_motor, "power_out",
    LP_feedwater_pump, "power",
    label="lpfw_motor_to_pump"
)

e_hpfw_in = PowerConnection(
    electrical_bus, "power_out2",
    hp_fw_pump_motor, "power_in",
    label="elec_to_hpfw_motor"
)

e_hpfw_out = PowerConnection(
    hp_fw_pump_motor, "power_out",
    HP_feedwater_pump, "power",
    label="hpfw_motor_to_pump"
)

e_gen_out = PowerConnection(
    generator, "power_out",
    electrical_bus, "power_in1",
    label="gen_to_elec"
)

e_grid = PowerConnection(
    electrical_bus, "power_out3",
    grid, "power",
    label="elec_to_grid"
)

# Efficiencies


#7 Condenser comes next (This is where one of the configuration will interface)
c34 = Connection(LP_turbine_stg_5, "out1", condenser, "in1",
                 label="Condenser")#in1/out1 is hot side

c35 = Connection(cooling_water_in, "out1", condenser,"in2",
                 label="Cooling water in")

c36 = Connection(condenser, "out2", cooling_water_out, "in1",
                 label="Cooling water out")

c37 = Connection(condenser, "out1", condenser_merger, "in1",
                 label="Condenser merger")

c38 = Connection(condenser_merger, "out1", LP_feedwater_pump, "in1",
                 label="LP feedwater pump")

#8 Heater
## in1/out1 = hot side, in2/out2 = cold side
c39 = Connection(LP_heater_merge_stg1, "out1", LP_feedwater_heater_stg1, "in1", label="LP feedwater heater 1 in")

c40 = Connection(LP_feedwater_heater_stg1, "out1", condenser_merger, "in2",
                 label="Condenser merger Interstage stream")
c41 = Connection(LP_heater_merge_stg2, "out1", LP_feedwater_heater_stg2, "in1",
                 label="LP feedwater heater 2 Hot in")
c42 = Connection(LP_heater_merge_stg3, "out1", LP_feedwater_heater_stg3, "in1",
                 label="LP feedwater heater 3 Hot in")
c43 = Connection(LP_heater_merge_stg4, "out1", LP_feedwater_heater_stg4, "in1",
                 label="LP feedwater heater 4 Hot in")


c44 = Connection(LP_feedwater_pump, "out1", LP_feedwater_heater_stg1, "in2")


c45 = Connection(LP_feedwater_heater_stg1, "out2", LP_feedwater_heater_stg2, "in2",
                 label="LP feedwater heater 2 Cold in")

c46 = Connection(LP_feedwater_heater_stg2, "out2", LP_feedwater_heater_stg3, "in2",
                 label="LP feedwater heater 3 Cold in")

c47 = Connection(LP_feedwater_heater_stg3, "out2", LP_feedwater_heater_stg4, "in2",
                 label="LP feedwater heater 4 Cold in")


c49 = Connection(LP_feedwater_heater_stg3, "out1", LP_heater_merge_stg2, "in1",
                 label="LP FWH3 drain cascade to FWH2")
c50 = Connection(LP_feedwater_heater_stg2, "out1", LP_heater_merge_stg1, "in1",
                 label="LP FWH2 drain cascade to FWH1")

#9 Deaerator
c51 = Connection(LP_feedwater_heater_stg4, "out2", dearator, "in2", label="Dearator input 2")
c52 = Connection(LP_feedwater_heater_stg4, "out1", LP_heater_merge_stg3, "in3",
                    label="LP FWH4 drain cascade to FWH3")
c53 = Connection(HP_feedwater_heater_stg1, "out1", dearator, "in3", label="Dearator input 3")




#10 Heater
## in1/out1 = hot side, in2/out2 = cold side
c54 = Connection(dearator, "out1", HP_feedwater_pump,"in1",
                 label="Dearator output 1")

c55 = Connection(HP_feedwater_pump,"out1",  HP_feedwater_heater_stg1, "in2",
                 label="HP heater input")

c56 = Connection(HP_feedwater_heater_stg1, "out2", HP_feedwater_heater_stg2, "in2",
                 label="HP feedwater stage 1 into stage 2")

c57 = Connection(HP_feedwater_heater_stg2, "out1", HP_feedwater_merger, "in2",
                 label="HP merger stage 1")

c58 = Connection(HP_feedwater_merger, "out1", HP_feedwater_heater_stg1, "in1",
                 label="HP merger stage 2")
c14.set_attr(m0=50)
# Component Attributes
steam_generator.set_attr(pr1=1,pr2=0.97, Q=1708e6)

interstage_heater_1.set_attr(Q=133.03e6)
interstage_heater_2.set_attr(Q=93.65e6, pr2=0.97)

#HP turbine outlets define in connections
HP_turbine_stg_1.set_attr(eta_s=0.845)
HP_turbine_stg_2.set_attr(eta_s=0.845)
HP_turbine_stg_3.set_attr(eta_s=0.845)
HP_turbine_stg_4.set_attr(eta_s=0.845)

#Condenser

condenser.set_attr(pr2=1,pr1=0.97,subcooling=False)

#LP Turbines
LP_turbine_stg_1.set_attr(eta_s=0.882,pr=0.39)
LP_turbine_stg_2.set_attr(eta_s=0.906,pr=0.6)
LP_turbine_stg_3.set_attr(eta_s=0.894,pr=0.34)
LP_turbine_stg_4.set_attr(eta_s=0.894,pr=0.46)
LP_turbine_stg_5.set_attr(eta_s=0.894)



# LP feedwater heaters
LP_feedwater_pump.set_attr(eta_s=0.80)
LP_feedwater_heater_stg1.set_attr(Q=136.06e6, pr2=0.97)#Set Q, took out ttd_u
LP_feedwater_heater_stg2.set_attr(Q=49.4e6,pr2=0.98)
LP_feedwater_heater_stg3.set_attr(Q=81.4e6, pr2=0.98)
LP_feedwater_heater_stg4.set_attr(Q=96.59e6, pr2=0.97)# Set Q Took out ttd_u

#HP feedwater heaters
HP_feedwater_pump.set_attr(eta_s=0.8078 ,pr=6.90)

HP_feedwater_heater_stg1.set_attr(Q=147.91e6, pr2=0.97)
HP_feedwater_heater_stg2.set_attr(Q=15.44e6)




# Connection Attributes


# Connection Attributes
#Steam generator
#Hot side
#c1,c2
c1.set_attr(fluid=coolant,T=597.85,p=15.5e6)#Primary in
c2.set_attr(T=555)

#Cold Side
#c3 cold out
c3.set_attr(fluid=working_fluid,m=1886.91,T=543.9,p=5.57e6)

#Pre turbine split
c4.set_attr(m=61.32)

#HP turbines
#outlets to splitters
c6.set_attr(p=3.41e6)
c8.set_attr(p=2.83e6)
c10.set_attr(p=1.79e6)
c12.set_attr(p=113e4)


# 113e4 get output pressure from dearator to find pressure ratio to HP feedwater pump


#MSH and Interstage
c13.set_attr(m=1452)
c14.set_attr(m=170.3)
c18.set_attr(x0=0.05)


c11_1.set_attr(m=71.72)

#Mass flow out of splitters

#LP Turbines

c24.set_attr(p0=427000,m0=43.07)#Revived
c27.set_attr(p0=256000,m0=74.8)#Revived
c30.set_attr(p0=89600,x0=0.105,m0=42.82)#Revived
c31.set_attr(p0=1.133e6)



#Condenser
c34.set_attr(p=40500)
c35.set_attr(fluid=cooling_fluid,p=0.1e6,T=288.15, m=44854.196)
c36.set_attr(T=300.15)
c37.set_attr(x=0)
c40.set_attr(m=83.6278)

#LP feedwater heater
c45.set_attr(x=0)

c51.set_attr(m=1285.62)
c54.set_attr(x=0)
c55.set_attr(m=1886.91)#T=458.54)#

# LP feedwater heater DRAINS (Hot side outlets must be saturated liquid)

c50.set_attr(x=0)
c49.set_attr(x=0)
c52.set_attr(x=0)

# HP Feedwater heater DRAINS (Hot side outlets must be saturated liquid)
c53.set_attr(x=0)
c57.set_attr(x=0)

# Deaerator Outlet
c54.set_attr(x=0)
c18_in.set_attr(x=0.05)
c20_in.set_attr(x=0)
c40_in.set_attr(x=0)
c49_in.set_attr(x=0)
c50_in.set_attr(x=0)
c52_in.set_attr(x=0)
c53_in.set_attr(x=0)
c57_in.set_attr(x=0)


AP1000_plant.add_conns(
    # Primary / Steam Generator
    c1, c2, c_fw1, c_fw2, c3, c4, c5,

    # HP Turbine
    c6, c7, c7_1, c8, c9, c9_1, c10, c11, c11_1, c12,

    # Interstage
    c13, c14, c15, c16_in, c16_out, c17, c19, c21,
    c14_1_in, c14_1_out, c18_in, c18_out, c20_in, c20_out,

    # LP Turbine
    c22, c23, c24, c25, c26, c27, c28, c29, c30, c31, c32, c33,

    # Condenser
    c34, c35, c36, c37, c38,

    # LP Heaters
    c39, c41, c42, c43, c44, c45, c46, c47,
    c40_in, c40_out, c49_in, c49_out, c50_in, c50_out, c52_in, c52_out,

    # Deaerator & HP Heaters
    c51, c54, c55, c56, c58,
    c53_in, c53_out, c57_in, c57_out
)

AP1000_plant.add_conns(
    *turbine_power_conns,
    e_gen_in,
    e_gen_out,
    e_lpfw_in,
    e_lpfw_out,
    e_hpfw_in,
    e_hpfw_out,
    e_grid,
)




try:

    result = AP1000_plant.solve(mode="design",block_solve=False)
    print(f"Conerged: {"True" if AP1000_plant.status == 0 else "False"}")
    print("\n" * 5)
    AP1000_plant.print_structural_analysis()
    print("\n" * 5)
    AP1000_plant.print_variables()
    print("\n" * 5)
    AP1000_plant.print_incidence_matrix()
    print("\n" * 5)
    AP1000_plant.print_equations_with_dependents()




except Exception as e:
    print(f"Error: {e}")
    AP1000_plant.print_variables()
    AP1000_plant.print_structural_analysis()
    AP1000_plant.print_incidence_matrix()


