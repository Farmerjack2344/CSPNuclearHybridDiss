from tespy.networks import Network
from tespy.components import (
    CycleCloser, Pump, Condenser, Turbine,
    SimpleHeatExchanger, Source, Sink,
    HeatExchanger, Merge, Splitter, Valve
)
from MultistageTurbine import MultiStageExtractionTurbine

from tespy.connections import Connection
# create a network object with R134a as fluid
AP1000_plant = Network()
AP1000_plant.units.set_defaults(
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
HP_turbine = MultiStageExtractionTurbine('HP turbine',num_stages=3)


LP_turbine = Turbine('LP turbine')

HP_FWH_2 = HeatExchanger('HP FWH 2')
HP_FWH_1 = HeatExchanger('HP FWH 1')
HP_FWH_M = Merge('HP FWH merge')

HP_FWH_valve_1 = Valve('HP FWH drain valve 1')
HP_FWH_valve_2 = Valve('HP FWH drain valve 2')

pump = Pump('feed pump')



c1 = Connection(cc, 'out1', HP_turbine, 'in1')

c2 = Connection(HP_turbine, 'out1',
                LP_turbine, 'in1')

c3 = Connection(HP_turbine, 'out2',
                HP_FWH_2, 'in1')


c5 = Connection(LP_turbine, 'out1',
                condenser, 'in1')

c6 = Connection(condenser, 'out1',
                condenser_merge, 'in1')

c7 = Connection(condenser_merge, 'out1',
                pump, 'in1')

c8 = Connection(pump, "out1", HP_FWH_1, "in2")

c9 = Connection(HP_FWH_1, "out2", HP_FWH_2, "in2")

c10 = Connection(HP_FWH_valve_2, "out1", HP_FWH_M, "in1")
c11 = Connection(HP_turbine, "out3", HP_FWH_M, "in2")

c12 = Connection(HP_FWH_M,"out1", HP_FWH_1,"in1")
c13 = Connection(HP_FWH_1, "out1", HP_FWH_valve_1, "in1")




c14 = Connection(HP_FWH_2, 'out2',
                 steam_generator, 'in1')

c15 = Connection(
    HP_FWH_2, 'out1',
    HP_FWH_valve_2, 'in1')


c16 = Connection(HP_FWH_valve_1, "out1", condenser_merge, "in2")

c0 = Connection(steam_generator,
                'out1', cc, 'in1')

#Condenser Cooling connections
c1_1 = Connection(cwso, 'out1', condenser, 'in2', label='11')
c1_2 = Connection(condenser, 'out2', cwsi, 'in1', label='12')

AP1000_plant.add_conns(c1, c2, c3, c5,
                   c6, c7, c8, c9,c10,c11,c12,c13,
                    c14, c15, c16, c0, c1_1, c1_2)

condenser.set_attr(pr1=1, pr2=0.98)
steam_generator.set_attr(
    Q=1707e6,
    pr=0.97)

HP_turbine.set_attr(eta_s1=0.845,eta_s2=0.845,eta_s3=0.845)
LP_turbine.set_attr(eta_s=0.845)

HP_FWH_2.set_attr(
    Q=-137.85e6,
    pr1=0.97,
    pr2=0.97

)

HP_FWH_1.set_attr(
    #Q=-147.91e6,
    pr1=0.97,
    pr2=0.97
)



pump.set_attr(eta_s=0.804)


#Condenser Cooling connections
c1_1.set_attr(T=288.15, p=1.2e5, fluid=cooling_fluid)
c1_2.set_attr(T=300.15)

c1.set_attr(T=600, p=150e5, m=1886.91, fluid=working_fluid)

# HP Turbine Outlets
c2.set_attr(p=113e4)# HP turbine outlet
c3.set_attr(m=89.9,p=2.83e6)# HP turbine outlet 2
c11.set_attr(m=71.72,p=1.79e6)# HP turbine outlet 3

# Pump outlet -> HP FWH 1 cold in
c8.set_attr(m0=1886.91, h0=7.9e5)

# HP FWH 1 cold out -> HP FWH 2 cold in
c9.set_attr(m0=1725.29 , h0=1.05e6)

# HP FWH merge out -> HP FWH 1 hot in
c12.set_attr(m0=161.6, h0=8.1e5)   # 89.9 + 71.72 ≈ combined drain mass

c5.set_attr(p=40500)# LP turbine outlet
c13.set_attr(m0=161.6, h0=5.7e5, x0=0)
c15.set_attr(m0=89.9, h0=8.1e5, x0=0)
c16.set_attr(m0=161.6, h0=5.7e5)

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