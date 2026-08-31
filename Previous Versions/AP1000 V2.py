from tespy.networks import Network
from tespy.components import (Condenser, HeatExchanger, Splitter,
                              Merge, CycleCloser, Source, Sink, Pump, DropletSeparator,
                              SteamTurbine, Valve
                              )
from tespy.connections import Connection

#Use TTD

coolant = {"water":1}
working_fluid = {"water":1}
cooling_fluid = {"water":1}

AP1000_plant = Network()
#Components
cycle_closer = CycleCloser("cycle closer")
# Steam generator
reactor_out = Source('Reactor Out')
reactor_in = Sink('Reactor In')

steam_generator = HeatExchanger('Steam Generator')#
ms_drain_valve = Valve("MS Drain Valve")
hp_crossover_valve = Valve("HP Crossover to LP FWH4 Valve")
fwh4_drain_valve = Valve("LP FWH4 Drain Valve")
fwh3_drain_valve = Valve("LP FWH3 Drain Valve")
fwh2_drain_valve = Valve("LP FWH2 Drain Valve")
ih1_drain_valve = Valve("Interstage Heater 1 Drain Valve")
ih2_drain_valve = Valve("Interstage Heater 2 Drain Valve")
hp_fwh2_drain_valve = Valve("HP FWH2 Drain Valve")
hp_fwh1_drain_valve = Valve("HP FWH1 Drain Valve")
fwh1_drain_valve = Valve("LP FWH1 Drain Valve")

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

LP_turbine_stg_5 = SteamTurbine('LP Turbine Stage 5')

# Generator / PowerBus network omitted: the extra PowerConnections couple into the
# Jacobian and were a recurring source of singularities. Turbine and pump work
# still come from eta_s; net output is summed after the thermodynamic solve.



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

c14 = Connection(Splitter_stg_4, "out2", dearator, "in1",
                 label="Dearator input 1")

c14_1_in = Connection(Splitter_stg_4, "out3", hp_crossover_valve, "in1",
                      label="HP crossover to valve")
c14_1 = Connection(hp_crossover_valve, "out1", LP_heater_merge_stg4, "in1",
                   label="HP crossover to LP FWH4")

#For moisture seperator out1 is liquid and out 2 is vapour
c15 = Connection(moisture_seperator_heater,"out2", interstage_heater_1, "in2",
                 label="Interstage heater 1")

c16_in = Connection(moisture_seperator_heater, "out1", ms_drain_valve, "in1", label="MS drain to valve")
c16_out = Connection(ms_drain_valve, "out1", LP_heater_merge_stg3, "in1", label="Valve to LP Merge 3")

c17 = Connection(interstage_heater_1, "out2", interstage_heater_2, "in2",
                 label="Interstage heater stage 2")
c18_in = Connection(interstage_heater_1, "out1", ih1_drain_valve, "in1",
                    label="Interstage heater 1 drain to valve")
c18 = Connection(ih1_drain_valve, "out1", interstage_merge, "in1",
                 label="Interstage merge 1")

c19 = Connection(interstage_heater_2, "out2", LP_turbine_stg_1, "in1",
                 label="LP turbine stage 1")

c20_in = Connection(interstage_heater_2, "out1", ih2_drain_valve, "in1",
                    label="Interstage heater 2 drain to valve")
c20 = Connection(ih2_drain_valve, "out1", interstage_merge, "in2",
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


c31 = Connection(LP_turbine_stg_4, "out1", LP_splitter_stg_4, "in1", label="LP turbine stage 4 Ex")

c32 = Connection(LP_splitter_stg_4, "out1", LP_turbine_stg_5, "in1", label="LP turbine stage 5 En")
c33 = Connection(LP_splitter_stg_4, "out2", LP_heater_merge_stg1, "in2", label="LP turbine stage 5 Ex")




#6 Power bus connections — removed; pumps use eta_s directly


#7 Condenser comes next (This is where one of the configuration will interface)
c34 = Connection(LP_turbine_stg_5, "out1", condenser_merger, "in1",
                 label="LP exhaust to condenser merge")

c35 = Connection(cooling_water_in, "out1", condenser,"in2",
                 label="Cooling water in")

c36 = Connection(condenser, "out2", cooling_water_out, "in1",
                 label="Cooling water out")

c37 = Connection(condenser_merger, "out1", condenser, "in1",
                 label="Merged exhaust and FWH1 drain to condenser")

c38 = Connection(condenser, "out1", LP_feedwater_pump, "in1",
                 label="LP feedwater pump")

#8 Heater
## in1/out1 = hot side, in2/out2 = cold side
c39 = Connection(LP_heater_merge_stg1, "out1", LP_feedwater_heater_stg1, "in1", label="LP feedwater heater 1 in")

c40_in = Connection(LP_feedwater_heater_stg1, "out1", fwh1_drain_valve, "in1",
                    label="LP FWH1 drain to valve")
c40 = Connection(fwh1_drain_valve, "out1", condenser_merger, "in2",
                 label="LP FWH1 drain to condenser merge")
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


c49_in = Connection(LP_feedwater_heater_stg3, "out1", fwh3_drain_valve, "in1",
                    label="LP FWH3 drain to valve")
c49 = Connection(fwh3_drain_valve, "out1", LP_heater_merge_stg2, "in1",
                 label="LP FWH3 drain cascade to FWH2")
c50_in = Connection(LP_feedwater_heater_stg2, "out1", fwh2_drain_valve, "in1",
                    label="LP FWH2 drain to valve")
c50 = Connection(fwh2_drain_valve, "out1", LP_heater_merge_stg1, "in1",
                 label="LP FWH2 drain cascade to FWH1")

#9 Deaerator
c51 = Connection(LP_feedwater_heater_stg4, "out2", dearator, "in2", label="Dearator input 2")
c52_in = Connection(LP_feedwater_heater_stg4, "out1", fwh4_drain_valve, "in1",
                    label="LP FWH4 drain to valve")
c52 = Connection(fwh4_drain_valve, "out1", LP_heater_merge_stg3, "in3",
                 label="LP FWH4 drain cascade to FWH3")

c53_in = Connection(HP_feedwater_heater_stg1, "out1", hp_fwh1_drain_valve, "in1",
                    label="HP FWH1 drain to valve")
c53 = Connection(hp_fwh1_drain_valve, "out1", dearator, "in3",
                 label="Dearator input 3")




#10 Heater
## in1/out1 = hot side, in2/out2 = cold side
c54 = Connection(dearator, "out1", HP_feedwater_pump,"in1",
                 label="Dearator output 1")

c55 = Connection(HP_feedwater_pump,"out1",  HP_feedwater_heater_stg1, "in2",
                 label="HP heater input")

c56 = Connection(HP_feedwater_heater_stg1, "out2", HP_feedwater_heater_stg2, "in2",
                 label="HP feedwater stage 1 into stage 2")

c57_in = Connection(HP_feedwater_heater_stg2, "out1", hp_fwh2_drain_valve, "in1",
                    label="HP FWH2 drain to valve")
c57 = Connection(hp_fwh2_drain_valve, "out1", HP_feedwater_merger, "in2",
                 label="HP merger stage 1")

c58 = Connection(HP_feedwater_merger, "out1", HP_feedwater_heater_stg1, "in1",
                 label="HP merger stage 2")

# Component Attributes
steam_generator.set_attr(Q=1708e6,pr1=1,pr2=0.97)

interstage_heater_1.set_attr(Q=133.03e6, pr1=0.97, pr2=0.97)
interstage_heater_2.set_attr(Q=93.65e6, pr1=0.97, pr2=0.97)
# Drain/crossover valves have no fixed pr: they throttle to the downstream merge pressure.

# Series HP stages: outlet pressures (not V4 parallel-turbine pr values).
HP_turbine_stg_1.set_attr(eta_s=0.845)
HP_turbine_stg_2.set_attr(eta_s=0.845)
HP_turbine_stg_3.set_attr(eta_s=0.845)
HP_turbine_stg_4.set_attr(eta_s=0.845)

#Condenser

condenser.set_attr(pr2=1,pr1=0.97)

#LP Turbines
LP_turbine_stg_1.set_attr(eta_s=0.882,pr=0.39)
LP_turbine_stg_2.set_attr(eta_s=0.906,pr=0.6)
LP_turbine_stg_3.set_attr(eta_s=0.894,pr=0.34)
LP_turbine_stg_4.set_attr(eta_s=0.894)
LP_turbine_stg_5.set_attr(eta_s=0.894)



# LP feedwater heaters
LP_feedwater_pump.set_attr(eta_s=0.80)
LP_feedwater_heater_stg1.set_attr(Q=136.06e6, pr1=0.97, pr2=0.97)
LP_feedwater_heater_stg2.set_attr(Q=49.4e6, pr1=0.98, pr2=0.98)
LP_feedwater_heater_stg3.set_attr(Q=81.4e6, pr1=0.98, pr2=0.98)
LP_feedwater_heater_stg4.set_attr(Q=96.59e6, pr1=0.97, pr2=0.97)

#HP feedwater heaters
HP_feedwater_pump.set_attr(eta_s=0.8078)

HP_feedwater_heater_stg1.set_attr(Q=147.91e6, pr1=0.97, pr2=0.97)
HP_feedwater_heater_stg2.set_attr(Q=15.44e6, pr1=0.97, pr2=0.97)

# ==========================================
# Connection Attributes
# ==========================================

# Steam generator
c1.set_attr(fluid=coolant, T=597.85, p=15.5e6, m0=17000, h0=1.55e6)
c2.set_attr(T=555, m0=17000, h0=1.42e6)

# Main steam: specify h, not T. T=543.9 K is 0.025 K below Tsat at 5.57 MPa,
# so CoolProp returns subcooled liquid (~1.19 MJ/kg) instead of steam (~2.79 MJ/kg).
c3.set_attr(fluid=working_fluid, m=1886.91, h=2785618, p=5.57e6)
c4.set_attr(m0=63, h0=2.785e6)
c5.set_attr(m0=1824, h0=2.7856e6)

# HP turbines outlets to splitters (series expansion)
c6.set_attr(p=3.41e6, m0=1824, h0=2.706e6)
c7.set_attr(m0=1739, h0=2.706e6)
c7_1.set_attr(m0=85, h0=2.706e6, p0=3.41e6)
c8.set_attr(p=2.83e6, m0=1739, h0=2.677e6)
c9.set_attr(m0=1649, h0=2.677e6, p0=2.83e6)
c9_1.set_attr(m0=90, h0=2.677e6)
c10.set_attr(p=1.79e6, m0=1649, h0=2.607e6)
c11.set_attr(m0=1577, h0=2.607e6, p0=1.79e6)
c11_1.set_attr(m0=72, h0=2.607e6)
c12.set_attr(p=1.1307e6, m0=1577, h0=2.541e6)
c13.set_attr(m0=1452, p0=1.1307e6, h0=2.541e6)
c14.set_attr(m0=114, p0=1.1307e6, h0=2.541e6)
c14_1_in.set_attr(m=0.51, p0=1.1307e6, h0=2.541e6)
c14_1.set_attr(m0=0.51, p0=4.292e5, h0=2.541e6)

# MSH and Interstage
c15.set_attr(m0=1282, p0=1.1307e6, h0=2.78e6)
c16_in.set_attr(m0=170, p0=1.1307e6, h0=786458)
c16_out.set_attr(m0=170, p0=1.13e6, h0=786458)
c17.set_attr(m0=1282, p0=1.097e6, h0=2.85e6)
c18_in.set_attr(x=0.05, p0=3.414e6, m0=85)
c18.set_attr(m0=85, h0=1.0e6)
c19.set_attr(m0=1282, p0=1.1004e6, h0=2.9497e6)
c20_in.set_attr(x=0, p0=5.4e6, m0=63)
c20.set_attr(m0=63, h0=1.0e6)
c21.set_attr(m0=248, p0=1.03e6, h0=1.74e6)

# LP Turbines — lock extraction mass flows; guesses must be LP pressures, not HP.
c22.set_attr(h0=2.775e6, p0=4.292e5)
c23.set_attr(p0=4.292e5, h0=2.775e6)
c24.set_attr(m0=43.07)
c25.set_attr(h0=2.690e6, p0=2.575e5, m0=1239)
c26.set_attr(p0=2.575e5, h0=2.690e6)
c27.set_attr(m0=74.75)
c28.set_attr(h0=2.529e6, p0=8.755e4)
c29.set_attr(p0=8.755e4, h0=2.529e6)
c30.set_attr(m0=41.68)
c31.set_attr(p0=4.5e4, h0=2.425e6)
c32.set_attr(p0=4.5e4, h0=2.425e6)
c33.set_attr(m0=54.68)

# Condenser
c34.set_attr(p=40500, m0=1068, h0=2.35e6)
c35.set_attr(fluid=cooling_fluid, p=0.1e6, T=288.15, m0=40000)
c36.set_attr(T=300.15)
c37.set_attr(m0=1453, h0=2.0e6)
c38.set_attr(m0=1453, h0=318878)
c39.set_attr(m0=385, h0=858218)
c40_in.set_attr(x=0, m0=385, h0=4.2e5)
c40.set_attr(m0=385, h0=4.2e5)
c41.set_attr(m0=330, h0=1.01e6)
c42.set_attr(m0=255, h0=7.13e5)
c43.set_attr(m0=44, h0=5.56e5)
c44.set_attr(m0=1453, h0=4.64e5)
c45.set_attr(m0=1453, h0=5.57e5)
c46.set_attr(m0=1453, h0=5.91e5)
c47.set_attr(m0=1453, h0=6.47e5)
c49_in.set_attr(x=0, m0=255)
c49.set_attr(m0=255, h0=5.5e5)
c50_in.set_attr(x=0, m0=330)
c50.set_attr(m0=330, h0=4.5e5)
c51.set_attr(m0=1453, h0=7.14e5)
c52_in.set_attr(x=0, m0=44, h0=5.56e5)
c52.set_attr(m0=44, h0=5.0e5)

# HP heaters / deaerator
c53_in.set_attr(x=0, m0=320, h0=9.03e5)
c53.set_attr(m0=320, h0=9.03e5)
c54.set_attr(x=0, m0=1887, h0=8.56e5)
c55.set_attr(m0=1887, h0=8.58e5)
c56.set_attr(m0=1887, h0=7.17e5)
c57_in.set_attr(x=0, m0=320, h0=1.04e6)
c57.set_attr(m0=320, h0=1.04e6)
c58.set_attr(m0=320, h0=1.04e6)
c_fw1.set_attr(m0=1887, h0=7.25e5)
c_fw2.set_attr(m0=1887, h0=7.25e5)

AP1000_plant.add_conns(
    # Primary / Steam Generator
    c1, c2,

    # Feedwater into Steam Generator
    c_fw1, c_fw2,

    # Steam Generator -> Turbine
    c3, c4, c5,

    # HP Turbine
    c6, c7, c7_1, c8, c9, c9_1,
    c10, c11, c11_1, c12,

    # Interstage
    c13, c14, c14_1_in, c14_1, c15, c16_in, c16_out, c17, c18_in, c18, c19, c20_in, c20, c21,

    # LP Turbine
    c22, c23, c24, c25, c26, c27,
    c28, c29, c30, c31, c32, c33,

    # Condenser
    c34, c35, c36, c37, c38,

    # LP Heaters
    c39, c40_in, c40, c41, c42, c43,
    c44, c45, c46, c47, c49_in, c49, c50_in, c50,

    # Deaerator
    c51, c52_in, c52, c53_in, c53,

    # HP Heaters
    c54, c55, c56, c57_in, c57, c58
)

try:

    result = AP1000_plant.solve(
        mode="design",
        block_solve=True,
        robust_relax=True,
        oscillation_damping=True,
        max_iter=300,
    )
    print(f"Converged: {'True' if AP1000_plant.status == 0 else 'False'}")
    turbines = [
        HP_turbine_stg_1, HP_turbine_stg_2, HP_turbine_stg_3, HP_turbine_stg_4,
        LP_turbine_stg_1, LP_turbine_stg_2, LP_turbine_stg_3, LP_turbine_stg_4,
        LP_turbine_stg_5,
    ]
    print(f"Gross turbine power: {sum(t.P.val for t in turbines)/1e6:.2f} MW")
    print(f"Pump work: {(LP_feedwater_pump.P.val + HP_feedwater_pump.P.val)/1e6:.2f} MW")




except Exception as e:
    print(f"Error: {e}")
    print(c14.p.val)
    AP1000_plant.print_variables()
    AP1000_plant.print_structural_analysis()
    AP1000_plant.print_incidence_matrix()


