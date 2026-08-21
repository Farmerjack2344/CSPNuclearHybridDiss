import pandas as pd
import math
from tespy.networks import Network
from tespy.components import (Compressor, Condenser, HeatExchanger, Turbine, Splitter,
                              Merge, CycleCloser, Drum, Source, Sink, Pump, DropletSeparator,
                              PowerBus, PowerSink, Motor, SteamTurbine, ParabolicTrough
                              )
from tespy.components.power.generator import Generator
from tespy.connections import Connection, PowerConnection
from MoltenSalt import MoltenSalt

import numpy as np


def cos_theta(day_of_year, solar_hour):
    delta = np.radians(23.45 * np.sin(np.radians(360 * (284 + day_of_year) / 365)))
    omega = np.radians(15 * (solar_hour - 12))
    return np.sqrt(max(1 - np.cos(delta)**2 * np.sin(omega)**2, 0))


def iam(theta_deg):
    """
    Incidence Angle Modifier
    :param theta_deg:
    :return:
    """
    return np.cos(np.radians(theta_deg)) + 0.000884 * theta_deg - 0.00005369 * theta_deg ** 2

def end_loss(theta_deg, f=1.71, L=148.5):
    return 1 - (f * math.tan(math.radians(theta_deg))) / L

def q_thermal_loss(T_htf, T_amb, receiver_length_total=(148.5 * 624), a0=0, a1=0.687, a2=0.001):
    """

    :param T_htf:Heat transfer fluid temperature
    :param T_amb:Ambient Temperature
    :param receiver_length_total: e.g. reciever length * number of recievers
    The following are quadratic coefficients
    :param a0:
    :param a1:
    :param a2:
    :return:
    """
    dT = T_htf - T_amb
    q_per_metre = a0 + a1 * dT + a2 * dT**2   # W/m
    return q_per_metre * receiver_length_total  # W, total field

def meteorolgoicl_values():
    df = pd.read_csv("Timeseries_37.320.csv", skiprows=8)

    df["datetime"] = pd.to_datetime(df["time"], format="%Y%m%d:%H%M", errors="coerce")
    df = df.dropna(subset=["datetime"]).copy()

    for col in ["Gb(i)", "H_sun", "T2m"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["hour"] = df["datetime"].dt.hour

    sun_height_rad = np.radians(df["H_sun"])
    with np.errstate(divide="ignore", invalid="ignore"):
        df["DNI"] = np.where(df["H_sun"] > 0, df["Gb(i)"] / np.sin(sun_height_rad), 0.0)

    df["T_amb"] = df["T2m"]

    return list(df[["hour", "DNI", "T_amb"]].itertuples(index=False, name=None))

Andasol1 = Network()
Andasol1.units.set_defaults(
    temperature="K",
    pressure="Pa",
    pressure_difference="Pa",
    enthalpy="J/kg",
    heat="W",
    power="W",
    mass_flow="kg/s"
)

#Components
Cycle_closer =CycleCloser('Cycle Closer')
#Rankine Cycles Components
turbine = SteamTurbine('Power block Turbine')
condenser = Condenser('Condenser')
pump = Pump('Power block Pump')
steam_generator = HeatExchanger('Steam Generator')

#Condenser sink/Source
cooling_water_in = Source('Cooling water in')
cooling_water_out = Sink('Cooling water out')


#Thermal Storage Block
#Hot tank
hot_salt_exit = Source('Hot Salt Exit')
hot_salt_enter = Sink('Hot Salt Enter')


#Cold Tank



#Solar field Components
solar_field = ParabolicTrough('Solar Field')
solar_field_closer = CycleCloser('Solar Cycle Closer')





#Component attributes

#Connections

#Power block
df = pd.read_csv("july_dni_hourly.csv")
DNI_values = meteorolgoicl_values()
collector_area = 500000
optical_efficiency = 0.75
T_htf_in = 273.15 + 285
mdot_htf = 100
htf = MoltenSalt()

for hour_num, DNI, T_amb in DNI_values:
    T_amb += 273.15

    Q_ideal = collector_area * DNI * optical_efficiency
    Q_real = Q_ideal
    for i in range(2):
        delta_T = Q_real / (mdot_htf * htf.cp(T_htf_in))
        T_htf_out = T_htf_in + delta_T
        cos = cos_theta(202,hour_num)
        Q_thermal_loss = q_thermal_loss(T_htf=T_htf_out,T_amb=T_amb)
        Q_real = (Q_ideal * cos * iam(math.acos(cos)) * end_loss(cos)) - Q_thermal_loss

    c1 = Connection(steam_generator, "out2", turbine, "in1","Steam generator to Turbine")
    c2 = Connection(turbine, "out1", condenser, "in1","Turbine to Condenser")
    c3 = Connection(condenser, "out1", pump, "in1","Condenser to Pump")
    c4 = Connection(pump, "out1", Cycle_closer, "in1","Pump to Cycle Closer")
    c5 = Connection(Cycle_closer, "out1", steam_generator, "in2","Cycle Closer to Steam Generator")

    #Thermal Storage Block


    mode = "direct"
    if mode == "direct":
        c6 = Connection(solar_field, "out1", steam_generator, "in1", "Solar field direct heating")
        c7 = Connection(steam_generator, "out1", solar_field_closer, "in1", "Condenser to Steam Generator")
        c8 = Connection(solar_field_closer, "out1", solar_field, "in1", "Fluid into solar field")

        Andasol1.add_conns(c1,c2,c3,c4,c5,c6,c7,c8)
    elif mode == "charging":
        pass

    elif mode == "discharging":
        pass

    else:
        pass
