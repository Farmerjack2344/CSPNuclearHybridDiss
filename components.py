
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
        self.T_cold_out = CP.PropsSI('T', 'H', h_cold_out, 'P', self.P_cold_out, self.stream1.fluid)
        self.s_cold_out = CP.PropsSI('S', 'H', h_cold_out, 'P', self.P_cold_out, self.stream1.fluid)

        self.P_hot_out = self.stream2.P
        self.h_hot_out = h_hot_out
        self.T_hot_out = CP.PropsSI('T', 'H', h_hot_out, 'P', self.P_hot_out, self.stream2.fluid)
        self.s_hot_out = CP.PropsSI('S', 'H', h_hot_out, 'P', self.P_hot_out, self.stream2.fluid)

        self.Q = Q



    def report(self):
        results = {'Q':self.Q,'P_cold_out': self.P_cold_out, 'h_cold_out': self.h_cold_out,'h_hot_out': self.h_hot_out,
                   's_cold_out': self.s_cold_out, 'T_cold_out': self.T_cold_out, 'T_hot_out': self.T_hot_out,'s_hot_out': self.s_hot_out
                   }
        return results

# Boiler
class Boiler:
    def __init__(self, feedwater_stream, hot_stream, effectiveness,
                 T_hot_out=None, T_cold_out=None, pinch_min=5.0):
        self.feedwater_stream = feedwater_stream  # cold side: subcooled liquid in
        self.hot_stream = hot_stream               # hot side: single-phase (primary loop / NaK), sensible only
        self.effectiveness = effectiveness
        self.T_cold_out = T_cold_out                # target steam outlet T (superheated)
        self.pinch_min = pinch_min                  # K, minimum allowable approach at the boiling point

        self.P_boiler = feedwater_stream.P
        self.T_sat = None
        self.Q = None
        self.T_hot_out = T_hot_out

    def solve(self):
        fluid_cold = self.feedwater_stream.fluid
        fluid_hot = self.hot_stream.fluid

        # --- Cold side: fix the outlet state directly (superheated steam target) ---
        h_cold_in = self.feedwater_stream.h
        h_cold_out = CP.PropsSI('H', 'T', self.T_cold_out, 'P', self.P_boiler, fluid_cold)
        Q_cold_needed = self.feedwater_stream.m_dot * (h_cold_out - h_cold_in)

        # --- Hot side is sensible-only: this is where effectiveness-NTU is still valid ---
        cp_hot = CP.PropsSI('C', 'T', self.hot_stream.T, 'P', self.hot_stream.P, fluid_hot)
        C_hot = self.hot_stream.m_dot * cp_hot

        self.T_sat = CP.PropsSI('T', 'P', self.P_boiler, 'Q', 0, fluid_cold)

        # Qmax uses hot inlet down to the cold *inlet* T as the sensible bound
        Qmax = C_hot * (self.hot_stream.T - self.feedwater_stream.T)
        Q = self.effectiveness * Qmax


        if abs(Q - Q_cold_needed) / Q_cold_needed > 0.02:
            print(f"Warning: effectiveness-based Q ({Q:.0f} W) and required Q "
                  f"({Q_cold_needed:.0f} W) disagree by >2% — check m_dot_hot or T_cold_out target")

        self.Q = Q_cold_needed  # cold-side energy balance is the physical constraint

        h_hot_out = self.hot_stream.h - self.Q / self.hot_stream.m_dot
        self.T_hot_out = CP.PropsSI('T', 'H', h_hot_out, 'P', self.hot_stream.P, fluid_hot)

        # --- Pinch check at the boiling point, not just the terminals ---
        # Hot-side T at the point where cold side reaches T_sat (start of boiling):
        h_cold_at_sat = CP.PropsSI('H', 'P', self.P_boiler, 'Q', 0, fluid_cold)

        Q_up_to_boil = self.feedwater_stream.m_dot * (h_cold_at_sat - h_cold_in)

        h_hot_at_pinch = self.hot_stream.h - Q_up_to_boil / self.hot_stream.m_dot
        T_hot_at_pinch = CP.PropsSI('T', 'H', h_hot_at_pinch, 'P', self.hot_stream.P, fluid_hot)

        pinch_dT = T_hot_at_pinch - self.T_sat
        if pinch_dT < self.pinch_min:
            raise ValueError(
                f"Pinch violation: only {pinch_dT:.1f} K approach at boiling onset "
                f"(min {self.pinch_min} K) — hot and cold streams cross inside the exchanger"
            )

    def report(self):
        return {'Q': self.Q, 'T_sat': self.T_sat, 'T_hot_out': self.T_hot_out,
                'T_cold_out': self.T_cold_out}


#Condenser
class Condenser:
    def __init__(self, steam_stream, cw_stream, effectiveness, subcooling=0.0):
        self.steam_stream = steam_stream   # hot side: turbine exhaust, wet/saturated
        self.cw_stream = cw_stream         # cold side: cooling water, single-phase liquid
        self.effectiveness = effectiveness
        self.subcooling = subcooling       # K below T_sat, default 0 = saturated liquid out

        self.P_cond = steam_stream.P       # condenser operates at steam-side pressure
        self.T_sat = None
        self.h_hot_out = None
        self.T_cw_out = None
        self.Q = None

    def solve(self):
        fluid_hot = self.steam_stream.fluid
        fluid_cw = self.cw_stream.fluid

        # --- Hot side: fix the outlet state first ---
        self.T_sat = CP.PropsSI('T', 'P', self.P_cond, 'Q', 0, fluid_hot)
        if self.subcooling > 0:
            T_out = self.T_sat - self.subcooling
            self.h_hot_out = CP.PropsSI('H', 'T', T_out, 'P', self.P_cond, fluid_hot)
        else:
            self.h_hot_out = CP.PropsSI('H', 'P', self.P_cond, 'Q', 0, fluid_hot)  # sat. liquid

        h_hot_in = self.steam_stream.h  # should already be a valid two-phase/superheated h
        self.Q = self.steam_stream.m_dot * (h_hot_in - self.h_hot_out)

        # --- Cold side: C_min is always the cooling water (Cr -> 0 case) ---
        cp_cw = CP.PropsSI('C', 'T', self.cw_stream.T, 'P', self.cw_stream.P, fluid_cw)
        C_cw = self.cw_stream.m_dot * cp_cw

        Qmax = C_cw * (self.T_sat - self.cw_stream.T)
        Q_check = self.effectiveness * Qmax

        # Sanity check: the two Q's should be consistent if m_dot_cw was chosen correctly.
        # In practice you usually SOLVE for m_dot_cw given Q, rather than assume it — see note below.

        h_cw_out = self.cw_stream.h + self.Q / self.cw_stream.m_dot
        self.T_cw_out = CP.PropsSI('T', 'H', h_cw_out, 'P', self.cw_stream.P, fluid_cw)

        if self.T_cw_out >= self.T_sat:
            raise ValueError(
                f"T_cw_out ({self.T_cw_out:.1f} K) exceeds T_sat ({self.T_sat:.1f} K) — "
                f"non-physical, cooling water flow too low or effectiveness too high"
            )

    def report(self):
        return {
            'P_cond': self.P_cond, 'T_sat': self.T_sat, 'Q': self.Q,
            'h_hot_out': self.h_hot_out, 'T_cw_out': self.T_cw_out
        }

#Deaerator
class Deareator:
    def __init__(self, stream, P_operating):
        self.stream = stream
        self.P_operating = P_operating  # Pa

        self.extraction_fraction = None
        self.outlet_stream = None

    def solve(self, extraction_stream: Stream, feedwater_in_stream: Stream):
        """
        extraction_stream: turbine bleed state (P_operating, h_extract)
        feedwater_in_stream: incoming subcooled liquid (from condensate pump)
        Returns extraction fraction y and outlet Stream (sat. liquid).
        """
        h_out = CP.PropsSI('H', 'P', self.P_operating, 'Q', 0, self.stream.fluid)

        h_extract = extraction_stream.h
        h_fw_in = feedwater_in_stream.h

        y = (h_out - h_fw_in) / (h_extract - h_fw_in)

        if not 0 < y < 1:
            raise ValueError(f"Non-physical extraction fraction y={y:.3f} — "
                              f"check extraction pressure vs deaerator pressure")

        self.extraction_fraction = y
        self.outlet_stream = Stream(
            P=self.P_operating, h=h_out, fluid=self.fluid,
            mdot=extraction_stream.mdot + feedwater_in_stream.mdot  # total flow, if you're tracking absolute mdot rather than fractions
        )
        return y, self.outlet_stream
