
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
    def __init__(self, stream, eta_isentropic=0.8, pressure_ratio=None, p_out=None, bleed=None):
        self.stream = stream
        self.eta_isentropic = eta_isentropic
        self.pressure_ratio = pressure_ratio
        self.P_out = p_out
        self.bleed = bleed
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

        if self.P_out == None:
            self.P_out = P_in * self.pressure_ratio

        h_outs = CP.PropsSI('H', 'S', s_in, 'P', self.P_out, self.stream.fluid)

        self.h_out = ((h_outs - h_in)/self.eta_isentropic) + h_in
        self.T_out = CP.PropsSI('T', 'H', self.h_out, 'P', self.P_out, self.stream.fluid)
        self.s_out = CP.PropsSI('S', 'T', self.T_out, 'P', self.P_out, self.stream.fluid)

        self.power = self.stream.m_dot * (self.h_out - h_in)

        return self.power

    def report(self):
        results = {'T_in': self.stream.T_in,'T_out': self.stream.T_out,'P_in':self.stream.p,'P_out':self.P_out, 'h_in': self.stream.h,'h_out': self.h_out, 's_in': self.stream.s,'s_out': self.s_out}
        return results


#Turbine
class Turbine:
    def __init__(self, stream, eta_isentropic=0.8, pressure_ratio=None, p_out=None, bleed=None):
        self.stream = stream
        self.eta_isentropic = eta_isentropic
        self.pressure_ratio = pressure_ratio
        self.P_out = p_out
        self.bleed = bleed
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
            s_in = CP.PropsSI('S', 'T', T_in, 'P', P_in, self.stream.fluid)

        if self.P_out == None:
            self.P_out = P_in * self.pressure_ratio

        h_outs = CP.PropsSI('H', 'S', s_in, 'P', self.P_out, self.stream.fluid)

        self.h_out = h_in - self.stream.h - self.eta_isentropic * (self.stream.h_out - h_outs)

        self.T_out = CP.PropsSI('T', 'H', self.h_out, 'P', self.P_out, self.stream.fluid)
        self.s_out = CP.PropsSI('S', 'T', self.T_out, 'P', self.P_out, self.stream.fluid)

        self.power = self.stream.m_dot * (self.h_out - h_in)

        return self.power

    def report(self):
        results = {'T_in': self.stream.T_in, 'T_out': self.stream.T_out, 'P_in': self.stream.p, 'P_out': self.P_out,
                   'h_in': self.stream.h, 'h_out': self.h_out, 's_in': self.stream.s, 's_out': self.s_out}
        return results


#Heater
class Heater:
    def __init__(self, stream1, stream2, effectivness, T_hot_out=None, T_cold_out=None, P_hot_out=None, P_cold_out=None):
        self.stream1 = stream1 # Has T_cold in
        self.stream2 = stream2 # Has T_hot in
        self.effectivness = effectivness

        self.T_hot_out = T_hot_out
        self.P_hot_out = P_hot_out
        self.h_hot_out = None
        self.s_hot_out = None

        self.T_cold_out = T_cold_out
        self.P_cold_out = P_cold_out
        self.h_cold_out = None
        self.s_cold_out = None

        self.Q = None

    def solve(self):
        C_stream1 = self.stream1.m_dot * (CP.PropsSI('C','T',self.stream1.T,'P',self.stream1.P, self.stream1.fluid))
        C_stream2 = self.stream2.m_dot * (CP.PropsSI('C','T',self.stream2.T,'P',self.stream2.P, self.stream2.fluid))

        if C_stream1 < C_stream2:
            C_min = C_stream1
        else:
            C_min = C_stream2

        Qmax = C_min * (self.stream2.T - self.stream1.T)

        Q = self.effectivness * Qmax

        # Energy balance, cold side: Q = m_dot_cold * (h_cold_out - h_cold_in)
        h_cold_in = self.stream1.h
        h_cold_out = h_cold_in + Q / self.stream1.m_dot

        # Energy balance, hot side: Q = m_dot_hot * (h_hot_in - h_hot_out)
        h_hot_in = self.stream2.h
        h_hot_out = h_hot_in - Q / self.stream2.m_dot

        # Back out T (and s, if you want it) from h and P
        self.P_cold_out = self.stream1.P
        self.h_cold_out = h_cold_out
        self.T_cold_out = CP.PropsSI('T', 'H', h_cold_out, 'P', self.P_cold_out, self.stream.fluid)
        self.s_cold_out = CP.PropsSI('S', 'H', h_cold_out, 'P', self.P_cold_out, self.stream.fluid)

        self.P_hot_out = self.stream2.P
        self.h_hot_out = h_hot_out
        self.T_hot_out = CP.PropsSI('T', 'H', h_hot_out, 'P', self.P_hot_out, self.stream.fluid)
        self.s_hot_out = CP.PropsSI('S', 'H', h_hot_out, 'P', self.P_hot_out, self.stream.fluid)

        self.Q = Q



    def report(self):
        pass


#Condenser

#Deaerator
