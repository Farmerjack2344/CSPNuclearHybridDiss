class MoltenSaltTank:
    """
    Lumped two-tank molten salt storage.

    Parameters
    ----------
    cp_avg : float
        Salt specific heat capacity, J/(kg*K), evaluated at the mean of
        T_cold and T_hot. Pull this from MoltenSalt.cp() at (T_hot+T_cold)/2
        rather than hardcoding, so it stays consistent if design temps change.
    T_cold, T_hot : float
        Cold and hot tank design temperatures, K.
        for Solar Salt at Andasol-class plants) and cite the source you use.
    total_salt_mass : float
        Total salt inventory (hot + cold), kg.
    initial_hot_mass : float
        Salt mass already in the hot tank at t=0, kg. Default 0 (cold start).
    """

    def __init__(self, cp_avg, T_cold, T_hot, total_salt_mass, initial_hot_mass=0.0):
        self.cp_avg = cp_avg
        self.T_cold = T_cold
        self.T_hot = T_hot
        self.m_total = total_salt_mass
        self.m_hot = initial_hot_mass
        self.m_cold = total_salt_mass - initial_hot_mass

    @property
    def soc(self):
        """State of charge: 0 = hot tank empty, 1 = hot tank full."""
        return self.m_hot / self.m_total

    def capacity_thermal(self):
        """Total usable thermal energy capacity of the store, J."""
        return self.m_total * self.cp_avg * (self.T_hot - self.T_cold)

    def available_charge(self, dt):
        """Heat the cold tank could still absorb over dt, W."""
        dh = self.cp_avg * (self.T_hot - self.T_cold)
        return self.m_cold / dt * dh if dt > 0 else 0.0

    def available_discharge(self, dt):
        """Heat the hot tank could still supply over dt, W."""
        dh = self.cp_avg * (self.T_hot - self.T_cold)
        return self.m_hot / dt * dh if dt > 0 else 0.0

    def charge(self, Q_available, dt):
        """
        Move salt cold -> hot, absorbing up to Q_available (W) over dt (s).
        Clamped by however much cold-tank salt is actually available.

        Returns
        -------
        Q_used : float
            Heat actually absorbed into storage, W (<= Q_available).
        m_dot_salt : float
            Salt mass flow rate cold -> hot, kg/s.
        """
        dh = self.cp_avg * (self.T_hot - self.T_cold)
        m_dot_max = self.m_cold / dt if dt > 0 else 0.0
        m_dot_requested = Q_available / dh if dh > 0 else 0.0
        m_dot_salt = min(m_dot_requested, m_dot_max)

        m_moved = m_dot_salt * dt
        self.m_cold -= m_moved
        self.m_hot += m_moved

        return m_dot_salt * dh, m_dot_salt

    def discharge(self, Q_requested, dt):
        """
        Move salt hot -> cold, supplying up to Q_requested (W) over dt (s).
        Clamped by however much hot-tank salt is actually available.

        Returns
        -------
        Q_supplied : float
            Heat actually released from storage, W (<= Q_requested).
        m_dot_salt : float
            Salt mass flow rate hot -> cold, kg/s.
        """
        dh = self.cp_avg * (self.T_hot - self.T_cold)
        m_dot_max = self.m_hot / dt if dt > 0 else 0.0
        m_dot_requested = Q_requested / dh if dh > 0 else 0.0
        m_dot_salt = min(m_dot_requested, m_dot_max)

        m_moved = m_dot_salt * dt
        self.m_hot -= m_moved
        self.m_cold += m_moved

        return m_dot_salt * dh, m_dot_salt


def dispatch(Q_solar, Q_design, tank, dt, min_load_fraction=0.25):
    """
    Decide, for one timestep, how solar thermal input and power-block demand
    are met, and update the tank's SoC accordingly.

    Modes produced
    ---------------
    - "charging"             : Q_solar >= Q_design, power block gets full
                                Q_design, surplus routed to hot tank
    - "direct_plus_discharge": 0 < Q_solar < Q_design, storage tops up the
                                shortfall
    - "direct_partial"       : same as above but storage is empty, so the
                                power block runs below Q_design
    - "charging_only"        : there is sun but not enough of it, even with
                                storage, to hold the power block above its
                                minimum load, so the field only charges
    - "discharging"          : Q_solar == 0 (night), storage alone supplies
                                the power block
    - "shutdown"             : Q_solar == 0 and storage cannot carry minimum
                                load

    Parameters
    ----------
    Q_solar : float
        Usable thermal power delivered by the solar field this timestep, W

    Q_design : float
        Power block design thermal input, W.

    tank : MoltenSaltTank
    dt : float
        Timestep length, s
    min_load_fraction : float
        Lowest fraction of Q_design the steam turbine is allowed to run at.
        Asfand et al. validate Andasol-1 down to 25% MCR.

    Returns
    -------
    dict with mode, Q_to_pb, Q_to_storage, Q_from_storage, Q_defocus,
    m_dot_charge, m_dot_discharge, tank_soc — everything the TESPy-side code
    needs to set Q= specs on the steam generator and charge/discharge heat
    exchangers. The solar field must be driven with Q_solar - Q_defocus, not
    with Q_solar, or the heat the store could not take gets pushed onto the
    power block.
    """
    result = {"Q_solar": Q_solar, "Q_design": Q_design}
    Q_min_load = min_load_fraction * Q_design

    if Q_solar >= Q_design:
        Q_surplus = Q_solar - Q_design
        Q_charged, m_dot_charge = tank.charge(Q_surplus, dt)
        # Whatever the cold tank could not absorb has nowhere to go: the field
        # is defocused rather than dumped on the power block.
        result.update(
            mode="charging",
            Q_to_pb=Q_design,
            Q_to_storage=Q_charged,
            Q_from_storage=0.0,
            m_dot_charge=m_dot_charge,
            m_dot_discharge=0.0,
            Q_defocus=Q_surplus - Q_charged,
        )

    elif Q_solar > 0:
        Q_shortfall = Q_design - Q_solar
        # Look before withdrawing
        # If even a full top-up cannot lift the block
        # to minimum load, the salt is better left in the hot tank.
        Q_top_up = min(Q_shortfall, tank.available_discharge(dt))

        if Q_solar + Q_top_up >= Q_min_load:
            Q_discharged, m_dot_discharge = tank.discharge(Q_top_up, dt)
            mode = "direct_plus_discharge" if Q_discharged > 0 else "direct_partial"
            result.update(
                mode=mode,
                Q_to_pb=Q_solar + Q_discharged,
                Q_to_storage=0.0,
                Q_from_storage=Q_discharged,
                m_dot_charge=0.0,
                m_dot_discharge=m_dot_discharge,
                Q_defocus=0.0,
            )
        else:
            Q_charged, m_dot_charge = tank.charge(Q_solar, dt)
            result.update(
                mode="charging_only",
                Q_to_pb=0.0,
                Q_to_storage=Q_charged,
                Q_from_storage=0.0,
                m_dot_charge=m_dot_charge,
                m_dot_discharge=0.0,
                Q_defocus=Q_solar - Q_charged,
            )

    else:
        Q_target = min(Q_design, tank.available_discharge(dt))

        if Q_target >= Q_min_load:
            Q_discharged, m_dot_discharge = tank.discharge(Q_target, dt)
            result.update(
                mode="discharging",
                Q_to_pb=Q_discharged,
                Q_to_storage=0.0,
                Q_from_storage=Q_discharged,
                m_dot_charge=0.0,
                m_dot_discharge=m_dot_discharge,
                Q_defocus=0.0,
            )
        else:
            result.update(
                mode="shutdown",
                Q_to_pb=0.0,
                Q_to_storage=0.0,
                Q_from_storage=0.0,
                m_dot_charge=0.0,
                m_dot_discharge=0.0,
                Q_defocus=0.0,
            )

    result["tank_soc"] = tank.soc
    return result