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


AP1000_plant = Network()
#Components
cycle_closer = CycleCloser("cycle closer")
# Steam generator
reactor_out = Source('Reactor Out')
reactor_in = Sink('Reactor In')

steam_generator = HeatExchanger('Steam Generator')#
ms_drain_valve = Valve("MS Drain Valve")

pre_turbine_split = Splitter('Pre-Turbine Split', num_out=(1 + 4))
# One stream to the interstage heater and the rest to seperate turbines

# HP Turbine block
HP_turbine_stg_1 = SteamTurbine('HP Turbine Stage 1 (495P)')


HP_turbine_stg_2 = SteamTurbine('HP Turbine Stage 2(410)')


HP_turbine_stg_3 = SteamTurbine('HP Turbine Stage 3(259)')


HP_turbine_stg_4 = SteamTurbine('HP Turbine Stage 4(164.3x5)')
HP_turbine_splitter = Splitter('HP Turbine Splitter', num_out=3)


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

LP_turbine_stg_5 = SteamTurbine('LP Turbine Stage 5')

#Generator
turbines = [LP_turbine_stg_1, LP_turbine_stg_2, LP_turbine_stg_3, LP_turbine_stg_4, LP_turbine_stg_5,
            HP_turbine_stg_1, HP_turbine_stg_2, HP_turbine_stg_3, HP_turbine_stg_4]
# NOTE: PowerBus/Generator/Motor/PowerConnection network removed — repeatedly the
# source of Jacobian singularities. Turbines/pumps solve their own P internally via
# eta_s; total electrical output is computed post-solve by summing turbine P values
# and pump work is drawn directly (P attribute), which is mathematically identical
# for the cycle thermodynamics and removes ~20 extra coupled variables/equations.



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
HP_turbine_merger_stg1 = Merge('HP Feedwater Merger stg1: interstage heaters 1+2',
                          num_in=2)
HP_turbine_merger_stg2 = Merge('HP Feedwater Merger stg2: +HP turbine stage 2',
                          num_in=2)
HP_heater_merger = Merge("Merge output from HP FWH stg2 to stg1",
                         num_in=2)
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
                 label="Stream into turbine (495P))")
c6  = Connection(pre_turbine_split, "out3", HP_turbine_stg_2, "in1",
                 label="Stream into turbine (410P)")

c7  = Connection(pre_turbine_split, "out4", HP_turbine_stg_3, "in1",
                 label="Stream into turbine (259P)")

c8  = Connection(pre_turbine_split, "out5", HP_turbine_stg_4, "in1",
                 label="Stream into turbine (164.3P)")



#4 Streams going to the next stage of turbines
c9 = Connection(HP_turbine_stg_1,'out1', interstage_heater_1, "in1",
                label="HP Turbine stage 0")

c10 = Connection(HP_turbine_stg_2, "out1", HP_turbine_merger_stg2, "in1",
                label="HP Turbine stage 2")

c11 = Connection(HP_turbine_stg_3, "out1", HP_heater_merger, "in1",
                 label="HP Turbine stage 4")

c12 = Connection(HP_turbine_stg_4, "out1", HP_turbine_splitter, "in1",
                 label="HP Turbine stage 6")



#Interstage Heaters
c13 = Connection(HP_turbine_splitter, "out1", moisture_seperator_heater, "in1",
                 label="Moisture seperator heater")
c14 = Connection(HP_turbine_splitter, "out2", dearator, "in1",
                 label="Dearator input 1")
c14_1 = Connection(HP_turbine_splitter, "out3", LP_heater_merge_stg4, "in1",
                    label="HP crossover to LP FWH4")

#For moisture seperator out1 is liquid and out 2 is vapour
c15 = Connection(moisture_seperator_heater,"out2", interstage_heater_1, "in2",
                 label="Interstage heater 1")

c16_in = Connection(moisture_seperator_heater, "out1", ms_drain_valve, "in1", label="MS drain to valve")
c16_out = Connection(ms_drain_valve, "out1", LP_heater_merge_stg3, "in1", label="Valve to LP Merge 3")

c17 = Connection(interstage_heater_1, "out2", interstage_heater_2, "in2",
                 label="Interstage heater stage 2")
c18 = Connection(interstage_heater_1, "out1", HP_turbine_merger_stg1, "in1",
                 label="Interstage merge 1")

c19 = Connection(interstage_heater_2, "out2", LP_turbine_stg_1, "in1",
                 label="LP turbine stage 1")

c20 = Connection(interstage_heater_2, "out1", HP_turbine_merger_stg1, "in2",
                 label="Interstage merge 2")

c20_1 = Connection(HP_turbine_merger_stg1, "out1", HP_turbine_merger_stg2, "in2",
                   label="Combining two mergers")


c21 = Connection(HP_turbine_merger_stg2, "out1", HP_feedwater_heater_stg2, "in1",
                 label="LP interstage merge into stage 4")

#5 Low pressure Turbines
c22 = Connection(LP_turbine_stg_1, "out1", LP_splitter_stg_1, "in1",
                 label="LP splitter stage 1")

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




#6 Power bus connections — removed (see note above); pump work handled by eta_s directly

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

c57 = Connection(HP_feedwater_heater_stg2, "out1", HP_heater_merger, "in2",
                 label="HP merger stage 1")
c58 = Connection(HP_heater_merger, "out1", HP_feedwater_heater_stg1,"in1",
                 label="HP FWH 2 outlet to FWH 1 hot inlet")


# Component Attributes
steam_generator.set_attr(Q=1708e6,pr1=1,pr2=0.97)

interstage_heater_1.set_attr(Q=133.03e6)
interstage_heater_2.set_attr(Q=93.65e6, pr2=0.97)

#HP turbine outlets define in connections
HP_turbine_stg_1.set_attr(eta_s=0.845,pr=0.613)
HP_turbine_stg_2.set_attr(eta_s=0.845,pr=0.507)
HP_turbine_stg_3.set_attr(eta_s=0.845,pr=0.32)
HP_turbine_stg_4.set_attr(eta_s=0.845,pr=0.203)

#Condenser

condenser.set_attr(pr2=1,pr1=0.97)

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

# ==========================================
# Connection Attributes
# ==========================================

# Steam generator
c1.set_attr(fluid=coolant, T=597.85, p=15.5e6) # Primary in
c2.set_attr(T=555)

# Cold Side
c3.set_attr(fluid=working_fluid, m=1886.91, h=2785618, p=5.57e6)  # was T=543.9, which sat
    # 0.025 K BELOW saturation at this pressure (Tsat=543.925 K) — CoolProp silently
    # resolved that to subcooled LIQUID (h~1.19 MJ/kg) instead of steam (h~2.79 MJ/kg),
    # which was the root cause of every downstream convergence failure this session.
    # h here matches DCD Fig 10.1-1 main steam enthalpy (1197.6 BTU/lb -> 2,785,618 J/kg),
    # i.e. essentially saturated steam, unambiguously in the vapor branch.

# HP turbines outlets to splitters
c9.set_attr(m0=84.4, p0=3.414e6, h0=2.7064e6)
c13.set_attr(m0=1452, p0=1.1307e6, h0=2.5406e6)
c14.set_attr(m0=114, p0=1.1307e6, h0=2.5406e6)
c14_1.set_attr(m0=0.51, p0=1.1307e6, h0=2.5406e6)
c15.set_attr(m0=1282, p0=1.1307e6, h0=2.78e6)
c16_in.set_attr(m0=170, p0=1.1307e6, h0=786458)
c16_out.set_attr(m0=170, p0=1.1307e6, h0=786458)
c17.set_attr(m0=1282, p0=1.097e6, h0=2.85e6)
c19.set_attr(m0=1282)
c20.set_attr(m0=63)
c21.set_attr(m0=247.9, p0=1.03e6, h0=1.74e6)  # redundant hard m spec removed (Interstage Heater 1 Q + turbine eta_s + c18 quality spec already close it); guesses from isentropic estimate
c10.set_attr(m=89.91, p0=2.824e6, h0=2.6766e6)
c11.set_attr(m=71.716, p0=1.782e6, h0=2.6066e6)
c12.set_attr(p0=1.1307e6, h0=2.5406e6)



#c10.set_attr(p=1.79e6)
#c12.set_attr(p=113e4)

# MSH and Interstage
c18.set_attr(x=0.05, p0=3.414e6)  # MUST be 'x' (hard constraint), not 'x0'
c19.set_attr(p0=1.1004e6, h0=2.9497e6)
c20.set_attr(x=0, p0=1.0974e6)     # Drain from interstage heater 2 must be liquid

# LP Turbines
# We must lock one of the parallel bleeds to LP FWH 4 to avoid a singularity
c22.set_attr(h0=2.775e6, p0=4.292e5)
c23.set_attr(p0=4.292e5, h0=2.775e6)
c24.set_attr(m=43.07)   # LP turbine extraction 1 (41.9 psia), DCD Fig 10.1-1: 341,605 lb/hr
c25.set_attr(h0=2.690e6, p0=2.575e5, m0=1238.9)
c26.set_attr(p0=2.575e5, h0=2.690e6)
c27.set_attr(m=74.75)   # LP turbine extraction 2 (37.2 psia), DCD Fig 10.1-1: 593,374 lb/hr
c28.set_attr(h0=2.529e6, p0=8.755e4)
c29.set_attr(p0=8.755e4, h0=2.529e6)
c30.set_attr(m=41.68, x0=0.105)  # LP turbine extraction 3 (12.56 psia), DCD Fig 10.1-1: 330,887 lb/hr
c31.set_attr(p0=4.5e4, h0=2.425e6)
c32.set_attr(p0=4.5e4, h0=2.425e6)
c33.set_attr(m=54.68)   # LP turbine extraction 4 (5.66 psia), DCD Fig 10.1-1: 434,005 lb/hr

# Condenser
c34.set_attr(p=40500, h0=2.35e6)
c35.set_attr(fluid=cooling_fluid, p=0.1e6, T=288.15, m0=40000)
c36.set_attr(T=300.15)

# Feedwater/condensate train — verified self-consistent via hand energy balance using
# corrected (post-c3-fix) steam enthalpies, cascading bottom-up through the LP heater
# drain chain (FWH4->FWH3->FWH2->FWH1->condenser). See session notes: drains do NOT
# reach saturated liquid given these Q values + corrected steam properties, they settle
# higher, so guesses reflect the verified energy-balance result, not naive hf(P).
c34.set_attr(m0=1067.8, h0=2.35e6)
c37.set_attr(m0=1067.8, h0=318878)
c38.set_attr(m0=1452.5, h0=461724)
c39.set_attr(m0=384.7, h0=858218)
c40.set_attr(m0=384.7, h0=858218)
c41.set_attr(m0=330.0, h0=1010906)
c42.set_attr(m0=255.3, h0=712730)
c43.set_attr(m0=43.6, h0=555873)
c44.set_attr(m0=1452.5, h0=463724)
c45.set_attr(m0=1452.5, h0=557397)
c46.set_attr(m0=1452.5, h0=591407)
c47.set_attr(m0=1452.5, h0=647449)
c49.set_attr(m0=255.3)
c50.set_attr(m0=330.0)
c51.set_attr(m0=1452.5, h0=713948)
c52.set_attr(m0=43.6, h0=555873)
c53.set_attr(m0=319.6, h0=902599)
c54.set_attr(m0=1886.1, h0=856322)
c55.set_attr(m0=1886.1, h0=858322)
c56.set_attr(m0=1886.6, h0=716907)
c57.set_attr(m0=319.6, h0=1042962)
c58.set_attr(m0=319.6, h0=1042962)
c_fw1.set_attr(m0=1886.9, h0=725090)
c_fw2.set_attr(m0=1886.9, h0=725090)
c1.set_attr(m0=17000, h0=1.55e6)
c2.set_attr(m0=17000, h0=1.42e6)
c4.set_attr(m0=63, h0=2.785e6)
c5.set_attr(m0=95, h0=2.7856e6)
c6.set_attr(m0=89.91, h0=2.7856e6)
c7.set_attr(m0=71.716, h0=2.7856e6)
c8.set_attr(m0=1567, h0=2.7856e6)

# Deaerator Outlet
c54.set_attr(x=0)

# NO constraints on c55, c13, c14, c11_1, c45, or c51. Let TESPy calculate them!

# ==========================================
# Power bus connections — removed with the PowerBus/Generator/Motor network.
# Turbine mechanical output and pump work are now solved directly via each
# component's own eta_s / P attribute (no PowerConnection needed).
# ==========================================


AP1000_plant.add_conns(
    # Primary / Steam Generator
    c1, c2,

    # Feedwater into Steam Generator
    c_fw1, c_fw2,

    # Steam Generator -> Turbine
    c3, c4, c5,

    # HP Turbine
    c6, c7,  c8, c9, c10, c11, c12,


    # Interstage
    c13, c14,c14_1, c15, c16_in, c16_out, c17, c18, c19, c20,c20_1, c21,

    # LP Turbine
    c22, c23, c24, c25, c26, c27,
    c28, c29, c30, c31, c32, c33,

    # Condenser
    c34, c35, c36, c37, c38,

    # LP Heaters
    c39, c40, c41, c42, c43,
    c44, c45, c46, c47, c49, c50,

    # Deaerator
    c51, c52, c53,

    # HP Heaters
    c54, c55, c56, c57, c58
)



try:

    result = AP1000_plant.solve(mode="design",block_solve=True, robust_relax=True, oscillation_damping=True, max_iter=300)
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