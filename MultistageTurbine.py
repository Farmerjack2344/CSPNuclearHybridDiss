# -*- coding: utf-8 -*-
"""
MultiStageExtractionTurbine
============================

A custom TESPy component representing a turbine with an arbitrary number of
expansion stages, each of which can have its own isentropic efficiency and
(optionally) its own extraction / bleed outlet.

This collapses a chain of `SteamTurbine` + `Splitter` pairs (the pattern used
for HP/LP turbine trains with extraction bleeds, e.g. an AP1000 HP turbine
with interstage extractions) into a single component with 1 inlet and N
outlets - outlet N is the final exhaust, outlets 1..N-1 are the stage
extractions.

Ports
-----
- Inlet:  in1
- Outlets: out1 ... outN  (N = num_stages; the LAST outlet is the stage-N /
  final exhaust, all earlier outlets are extraction bleeds taken after their
  respective stage)

Mandatory equations
--------------------
- Overall mass balance: m_in1 = sum(m_out_i)
- Fluid composition equality: fluid_in1 = fluid_out_i for every outlet
  (no separation takes place - every outlet carries the same composition)

Optional per-stage equations
-----------------------------
- eta_s1 ... eta_sN : isentropic efficiency of stage i. Setting eta_s{i}
  adds the equation
      0 = -(h_out_i - h_in_i) + eta_s_i * (h_out_i,s - h_in_i)
  exactly like the standard tespy Turbine, where:
    * h_in_i / p_in_i are the properties of the connection feeding stage i
      (the component inlet for stage 1, or the extraction connection of the
      previous stage for stage i > 1)
    * h_out_i / p_out_i are the properties of stage i's own outlet
      connection (out{i})

You are NOT required to set eta_s for every stage - if you leave a stage's
eta_s unset, you must fully determine that stage's outlet state some other
way (e.g. hard p= and h= on the connection), exactly as you would for a
standalone tespy Turbine.

Pressures are NOT constrained by this component - specify p (or p0 as an
initial guess) directly on each outlet connection, same as you already do
for extraction connections in your AP1000 model.

Notes on implementation
------------------------
This targets tespy's newer function/dependents equation API (0.11.x). No
Jacobian derivatives are hand-coded: every equation supplies a `dependents`
list and lets tespy's automatic central-difference differentiation build the
Jacobian, exactly the mechanism the built-in `Turbine.eta_s_func` relies on
when a component doesn't need a hand-optimised analytic derivative.
"""

from tespy.components.component import Component
from tespy.components.component import component_registry
from tespy.components.turbomachinery.base import Turbomachine
from tespy.tools.data_containers import ComponentMandatoryConstraints as dc_cmc
from tespy.tools.data_containers import ComponentProperties as dc_cp
from tespy.tools.data_containers import SimpleDataContainer as dc_simple
from tespy.tools.fluid_properties import isentropic

# Number of eta_s{i} parameters pre-declared. num_stages can be set to
# anything from 1 up to this value. Raise it if you need a turbine with
# more than 12 stages.
MAX_STAGES = 12


@component_registry
class MultiStageExtractionTurbine(Turbomachine):
    r"""
    Turbine with an arbitrary number of expansion stages and extraction
    outlets.

    Example
    -------
    A 3-stage turbine: two extraction bleeds after stages 1 and 2, plus the
    final exhaust after stage 3.

    >>> from tespy.components import Source, Sink
    >>> from tespy.connections import Connection
    >>> from tespy.networks import Network
    >>> nw = Network(iterinfo=False)
    >>> nw.units.set_defaults(
    ...     temperature='K', pressure='Pa', pressure_difference='Pa',
    ...     enthalpy='J/kg', mass_flow='kg/s'
    ... )
    >>> so = Source('inlet steam')
    >>> bleed1 = Sink('extraction 1')
    >>> bleed2 = Sink('extraction 2')
    >>> exhaust = Sink('exhaust')
    >>> t = MultiStageExtractionTurbine('HP turbine', num_stages=3)
    >>> c_in = Connection(so, 'out1', t, 'in1', label='c_in')
    >>> c_b1 = Connection(t, 'out1', bleed1, 'in1', label='c_b1')
    >>> c_b2 = Connection(t, 'out2', bleed2, 'in1', label='c_b2')
    >>> c_ex = Connection(t, 'out3', exhaust, 'in1', label='c_ex')
    >>> nw.add_conns(c_in, c_b1, c_b2, c_ex)
    >>> t.set_attr(eta_s1=0.9, eta_s2=0.9, eta_s3=0.9)
    >>> c_in.set_attr(fluid={'water': 1}, m=100, p=15e6, T=850)
    >>> c_b1.set_attr(p=8e6, m=20)
    >>> c_b2.set_attr(p=4e6, m=20)
    >>> c_ex.set_attr(p=1e6)
    >>> nw.solve('design')
    """

    # ------------------------------------------------------------------
    # Ports
    # ------------------------------------------------------------------
    @staticmethod
    def inlets():
        return ["in1"]

    def outlets(self):
        if self.num_stages.is_set:
            return [f"out{i + 1}" for i in range(self.num_stages.val)]
        else:
            self.set_attr(num_stages=2)
            return self.outlets()

    @classmethod
    def port_schema(cls):
        return {
            "inlets": {"type": "fixed", "ports": ["in1"]},
            "outlets": {
                "type": "variable", "parameter": "num_stages",
                "pattern": "out{n}", "min": 1,
            },
            "powerinlets": {"type": "fixed", "ports": []},
            "poweroutlets": {"type": "fixed", "ports": []},
            "heatinlets": {"type": "fixed", "ports": []},
            "heatoutlets": {"type": "fixed", "ports": []},
        }

    # ------------------------------------------------------------------
    # Parameters (num_stages + up to MAX_STAGES optional eta_s{i})
    # ------------------------------------------------------------------
    def get_parameters(self):
        parameters = super().get_parameters()

        parameters["P"].func = self.energy_balance_func
        parameters["P"].dependents = self.energy_balance_dependents
        parameters["P"].calc = self.calc_P
        parameters["P"].max_val = 0

        parameters["num_stages"] = dc_simple(
            dtype="int",
            description="number of expansion stages"
        )

        for i in range(1, MAX_STAGES + 1):
            parameters[f"eta_s{i}"] = dc_cp(
                min_val=0,
                max_val=1,
                num_eq_sets=1,
                func=self._stage_eta_s_func,
                func_params={"stage": i},
                dependents=self._stage_eta_s_dependents,
                quantity="efficiency",
                description=f"isentropic efficiency of stage {i}",
            )

        return parameters

    # ------------------------------------------------------------------
    # Mandatory constraints: overall mass balance + fluid equality
    # ------------------------------------------------------------------
    def get_mandatory_constraints(self):
        return {
            "mass_flow_constraints": dc_cmc(**{
                "func": self._mass_flow_func,
                "dependents": self._mass_flow_dependents,
                "num_eq_sets": 1,
                "description": (
                    "overall mass balance: inlet = sum of all stage outlets"
                ),
            }),
            "fluid_constraints": dc_cmc(**{
                "structure_matrix": self._fluid_structure_matrix,
                "num_eq_sets": self.num_o,
                "description": (
                    "fluid composition equality: inlet composition "
                    "preserved at every outlet"
                ),
            }),
        }

    def _mass_flow_func(self):
        res = self.inl[0].m.val_SI
        for o in self.outl:
            res -= o.m.val_SI
        return res

    def _mass_flow_dependents(self):
        return [self.inl[0].m] + [o.m for o in self.outl]

    def _fluid_structure_matrix(self, k):
        for eq, conn in enumerate(self.outl):
            self._structure_matrix[k + eq, self.inl[0].fluid.sm_col] = 1
            self._structure_matrix[k + eq, conn.fluid.sm_col] = -1

    # ------------------------------------------------------------------
    # Stage bookkeeping
    # ------------------------------------------------------------------
    def _num_active_stages(self):
        return len(self.outl)

    def _stage_inlet_conn(self, stage):
        n = self._num_active_stages()
        if stage < 1 or stage > n:
            msg = (
                f"eta_s{stage} was set on component {self.label}, but "
                f"num_stages is only {n}. Either raise num_stages or "
                f"remove the eta_s{stage} specification."
            )
            raise ValueError(msg)
        return self.inl[0] if stage == 1 else self.outl[stage - 2]

    def _stage_outlet_conn(self, stage):
        return self.outl[stage - 1]

    # ------------------------------------------------------------------
    # Fluid-wrapper propagation: a single inlet must propagate to every
    # outlet (default Component behaviour assumes 1:1 inlet/outlet
    # pairing, which only reaches out1). Same fix as tespy's own Splitter.
    # ------------------------------------------------------------------
    def propagate_wrapper_to_target(self, branch):
        branch["components"] += [self]
        for outconn in self.outl:
            branch["connections"] += [outconn]
            outconn.target.propagate_wrapper_to_target(branch)

    # ------------------------------------------------------------------
    # Per-stage isentropic efficiency equation
    # ------------------------------------------------------------------
    def _stage_eta_s_func(self, stage):
        i = self._stage_inlet_conn(stage)
        o = self._stage_outlet_conn(stage)
        eta = getattr(self, f"eta_s{stage}")
        h_s = isentropic(
            i.p.val_SI, i.h.val_SI, o.p.val_SI,
            i.fluid_data, i.mixing_rule,
            T0=i.T.val_SI, T0_out=o.T.val_SI,
        )
        return (
            -(o.h.val_SI - i.h.val_SI)
            + (h_s - i.h.val_SI) * eta.val_SI
        )

    def _stage_eta_s_dependents(self, stage):
        i = self._stage_inlet_conn(stage)
        o = self._stage_outlet_conn(stage)
        return [i.p, i.h, o.p, o.h]

    def energy_balance_func(self):
        """
        Energy balance for a turbine with multiple extraction outlets.

        TESPy turbine sign convention:
        P < 0 means power is produced by the turbine.
        """

        power_fluid = -self.inl[0].m.val_SI * self.inl[0].h.val_SI

        for o in self.outl:
            power_fluid += o.m.val_SI * o.h.val_SI

        return self.P.val_SI - power_fluid

    def energy_balance_dependents(self):
        return (
                [self.P, self.inl[0].m, self.inl[0].h]
                + [
                    variable
                    for o in self.outl
                    for variable in [o.m, o.h]
                ]
        )

    def calc_P(self):
        """
        Calculate turbine power from the overall steady-flow
        energy balance.
        """

        P = -self.inl[0].m.val_SI * self.inl[0].h.val_SI

        for o in self.outl:
            P += o.m.val_SI * o.h.val_SI

        return P