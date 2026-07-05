
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import CoolProp.CoolProp as CP



class Stream:
    def __init__(self, fluid, m_dot, T=None, s=None, P=None, h=None, q=None):
        self.fluid = fluid
        self.T = T
        self.s = s
        self.P = P
        self.h = h
        self.q = q
        self.m_dot = m_dot

    def copy_with(self, **kwargs) -> "Stream":
        data = dict(fluid=self.fluid, m_dot=self.m_dot, p=self.p, h=self.h,
                    T=self.T, s=self.s)
        data.update(kwargs)
        return Stream(**data)


# Pump
class Pump:
    def __init__(self, stream, eta_isentropic=0.8, pressure_ratio=None, p_out=None):
        self.stream = stream
        self.eta_isentropic = eta_isentropic
        self.pressure_ratio = pressure_ratio
        self.p_out = p_out
        self.power = None

        self.h_out = None
        self.T_out = None
        self.s_out = None

    def solve(self):
        h_in = self.stream.h
        T_in = self.stream.T
        P_in = self.stream.p
        s_in = self.stream.s

        if s_in is None:
            s_in = CP.PropsSI('S', 'T', T_in,'P', P_in, self.stream.fl)

        if self.p_out == None:
            self.p_out = P_in * self.pressure_ratio

        h_outs = CP.PropsSI('H', 'S', s_in, 'P', self.p_out, self.stream.fluid)

        self.h_out = ((h_outs - h_in)/self.eta_isentropic) + h_in
        self.T_out = CP.PropsSI('T', 'H', self.h_out, 'P', self.p_out, self.stream.fluid)
        self.s_out = CP.PropsSI('S', 'T', self.T_out, 'P', self.p_out, self.stream.fluid)

        self.power = self.stream.m_dot * (self.h_out - h_in)

    def report(self):
        results = []
        return results





#Turbine

#Heater

#Condenser

#Deaerator
