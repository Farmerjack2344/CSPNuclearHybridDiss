from tespy.networks import Network
from tespy.components import (
    CycleCloser, Pump, Condenser, Turbine,
    SimpleHeatExchanger, Source, Sink,
    HeatExchanger, Merge, Splitter, Valve
)


from tespy.connections import Connection
# create a network object with R134a as fluid
my_plant = Network()
my_plant.units.set_defaults(
    temperature="K",
    pressure="Pa",
    pressure_difference="Pa",
    enthalpy="J/kg",
    heat="W",
    power="W",
    mass_flow="kg/s"
)

cooling_fluid = {'water': 1}
working_fluid = {'water': 1}

cwso = Source('cooling water source')
cwsi = Sink('cooling water sink')

cc = CycleCloser('cycle closer')
steam_generator= SimpleHeatExchanger('steam generator')
condenser = Condenser('main condenser')
condenser_merge = Merge('condenser merge')
HP_turbine = Turbine('HP turbine')
HP_splitter = Splitter('HP splitter', num_out=2)

LP_turbine = Turbine('LP turbine')

HP_FWH = HeatExchanger('HP FWH')

HP_FWH_valve = Valve('HP FWH drain valve')

pump = Pump('feed pump')



c1 = Connection(cc, 'out1', HP_turbine, 'in1')

c2 = Connection(HP_turbine, 'out1',
                HP_splitter, 'in1')

c3 = Connection(HP_splitter, 'out1',
                LP_turbine, 'in1')

c4 = Connection(
    HP_splitter, 'out2',
    HP_FWH, 'in1')

c5 = Connection(LP_turbine, 'out1',
                condenser, 'in1')

c6 = Connection(condenser, 'out1',
                condenser_merge, 'in1')

c7 = Connection(condenser_merge, 'out1',
                pump, 'in1')

c8 = Connection(pump, 'out1',
                HP_FWH, 'in2')

c9 = Connection(HP_FWH, 'out2',
                steam_generator, 'in1')

c10 = Connection(
    HP_FWH, 'out1',
    HP_FWH_valve, 'in1')

c11 = Connection(
    HP_FWH_valve, 'out1',
    condenser_merge, 'in2')

c0 = Connection(steam_generator,
                'out1', cc, 'in1')

#Condenser Cooling connections
c1_1 = Connection(cwso, 'out1', condenser, 'in2', label='11')
c1_2 = Connection(condenser, 'out2', cwsi, 'in1', label='12')

my_plant.add_conns(c1, c2, c3, c4, c5,c6,c7,c8,c9,c10, c11, c0, c1_1, c1_2)

condenser.set_attr(pr1=1, pr2=0.98)
steam_generator.set_attr(Q=1707e6)
HP_turbine.set_attr(eta_s=0.845)
LP_turbine.set_attr(eta_s=0.845)

HP_FWH.set_attr(
    Q=137.85e6,
    pr1=0.97,
    pr2=0.97

)

c4.set_attr(m=89.9)

pump.set_attr(eta_s=0.804)


#Condenser Cooling connections
c1_1.set_attr(T=288.15, p=1.2e5, fluid=cooling_fluid)
c1_2.set_attr(T=300.15)

c1.set_attr(T=600, p=150e5, m=1886.91, fluid=working_fluid)
c2.set_attr(p=113e4)# HP turbine outlet
c5.set_attr(p=40500)# LP turbine outlet
my_plant.solve(mode='design')
my_plant.print_results()