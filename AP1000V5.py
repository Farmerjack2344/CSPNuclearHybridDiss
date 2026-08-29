from tespy.networks import Network
from tespy.components import (
    CycleCloser, Pump, Condenser, Turbine, SimpleHeatExchanger, Source, Sink
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
turbine = Turbine('steam turbine')
pump = Pump('feed pump')



c1 = Connection(cc, 'out1', turbine, 'in1', label='1')
c2 = Connection(turbine, 'out1', condenser, 'in1', label='2')
c3 = Connection(condenser, 'out1', pump, 'in1', label='3')
c4 = Connection(pump, 'out1', steam_generator, 'in1', label='4')
c0 = Connection(steam_generator, 'out1', cc, 'in1', label='0')

#Condenser Cooling connections
c1_1 = Connection(cwso, 'out1', condenser, 'in2', label='11')
c1_2 = Connection(condenser, 'out2', cwsi, 'in1', label='12')

my_plant.add_conns(c1, c2, c3, c4, c0, c1_1, c1_2)

condenser.set_attr(pr1=1, pr2=0.98)
steam_generator.set_attr(Q=1707e6)
turbine.set_attr(eta_s=0.9)
pump.set_attr(eta_s=0.75)


#Condenser Cooling connections
c1_1.set_attr(T=300.15, p=1.2e5, fluid=cooling_fluid)
c1_2.set_attr(T=303.15)

c1.set_attr(T=600, p=150e5, m=1886.91, fluid=working_fluid)
c2.set_attr(p=0.1e5)

my_plant.solve(mode='design')
my_plant.print_results()