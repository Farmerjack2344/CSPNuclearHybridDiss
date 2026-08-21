import pandas as pd
import numpy as np
from CoolProp.CoolProp import PropsSI

# print(PropsSI("P","T",321.039, "H",180.73e3, "WATER"))
# H = 180.73e3
# df = pd.read_csv("Timeseries_37.320.csv", skiprows=8)
#
# df["datetime"] = pd.to_datetime(df["time"], format="%Y%m%d:%H%M", errors="coerce")
# df = df.dropna(subset=["datetime"]).copy()
#
# for col in ["Gb(i)", "H_sun", "T2m"]:
#     df[col] = pd.to_numeric(df[col], errors="coerce")
#
# df["hour"] = df["datetime"].dt.hour
#
# sun_height_rad = np.radians(df["H_sun"])
# with np.errstate(divide="ignore", invalid="ignore"):
#     df["DNI"] = np.where(df["H_sun"] > 0, df["Gb(i)"] / np.sin(sun_height_rad), 0.0)
#
# df["T_amb"] = df["T2m"]
#
# data = list(df[["hour", "DNI", "T_amb"]].itertuples(index=False, name=None))
#
# print(data)