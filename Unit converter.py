"""
US/Imperial <-> SI Unit Converter
----------------------------------
A standalone desktop GUI (built with Tkinter, no external dependencies)
for converting between American/Imperial units and SI units.

Run with:
    python unit_converter.py
"""

import tkinter as tk
from tkinter import ttk

# ---------------------------------------------------------------------------
# Conversion data
# ---------------------------------------------------------------------------
# Each category maps unit name -> factor to convert TO the base SI unit.
# Temperature is handled separately (non-linear/offset conversions).

CATEGORIES = {
    "Length": {
        "base": "metre (m)",
        "units": {
            "inch (in)": 0.0254,
            "foot (ft)": 0.3048,
            "yard (yd)": 0.9144,
            "mile (mi)": 1609.344,
            "metre (m)": 1.0,
            "centimetre (cm)": 0.01,
            "millimetre (mm)": 0.001,
            "kilometre (km)": 1000.0,
        },
    },
    "Mass": {
        "base": "kilogram (kg)",
        "units": {
            "pound (lb)": 0.45359237,
            "ounce (oz)": 0.028349523125,
            "US ton (short ton)": 907.18474,
            "slug": 14.5939029,
            "kilogram (kg)": 1.0,
            "gram (g)": 0.001,
            "tonne (t)": 1000.0,
        },
    },
    "Pressure": {
        "base": "pascal (Pa)",
        "units": {
            "psi (lbf/in^2)": 6894.757293168,
            "inHg (inch mercury)": 3386.389,
            "atm": 101325.0,
            "bar": 100000.0,
            "pascal (Pa)": 1.0,
            "kilopascal (kPa)": 1000.0,
            "megapascal (MPa)": 1_000_000.0,
        },
    },
    "Energy": {
        "base": "joule (J)",
        "units": {
            "BTU": 1055.05585262,
            "foot-pound (ft-lb)": 1.3558179483,
            "calorie (cal)": 4.184,
            "kilowatt-hour (kWh)": 3_600_000.0,
            "joule (J)": 1.0,
            "kilojoule (kJ)": 1000.0,
            "megajoule (MJ)": 1_000_000.0,
        },
    },
    "Power": {
        "base": "watt (W)",
        "units": {
            "horsepower (hp, mechanical)": 745.6998715823,
            "BTU/hour": 0.29307107,
            "watt (W)": 1.0,
            "kilowatt (kW)": 1000.0,
            "megawatt (MW)": 1_000_000.0,
        },
    },
    "Force": {
        "base": "newton (N)",
        "units": {
            "pound-force (lbf)": 4.4482216153,
            "kip (1000 lbf)": 4448.2216153,
            "poundal": 0.138254954376,
            "newton (N)": 1.0,
            "kilonewton (kN)": 1000.0,
        },
    },
    "Velocity": {
        "base": "metre/second (m/s)",
        "units": {
            "mph": 0.44704,
            "foot/second (ft/s)": 0.3048,
            "knot": 0.514444,
            "metre/second (m/s)": 1.0,
            "kilometre/hour (km/h)": 0.277778,
        },
    },
    "Area": {
        "base": "square metre (m^2)",
        "units": {
            "square inch (in^2)": 0.00064516,
            "square foot (ft^2)": 0.09290304,
            "acre": 4046.8564224,
            "square metre (m^2)": 1.0,
            "square centimetre (cm^2)": 0.0001,
            "hectare": 10000.0,
        },
    },
    "Volume": {
        "base": "cubic metre (m^3)",
        "units": {
            "US gallon (gal)": 0.003785411784,
            "US quart (qt)": 0.000946352946,
            "cubic foot (ft^3)": 0.028316846592,
            "cubic inch (in^3)": 0.000016387064,
            "cubic metre (m^3)": 1.0,
            "litre (L)": 0.001,
            "millilitre (mL)": 0.000001,
        },
    },
    "Density": {
        "base": "kilogram/cubic metre (kg/m^3)",
        "units": {
            "pound/cubic foot (lb/ft^3)": 16.01846337,
            "slug/cubic foot (slug/ft^3)": 515.378818,
            "kilogram/cubic metre (kg/m^3)": 1.0,
            "gram/cubic centimetre (g/cm^3)": 1000.0,
        },
    },
    "Dynamic Viscosity": {
        "base": "pascal-second (Pa.s)",
        "units": {
            "lb/(ft.s)": 1.48816394,
            "centipoise (cP)": 0.001,
            "pascal-second (Pa.s)": 1.0,
        },
    },
    "Heat Flux": {
        "base": "watt/square metre (W/m^2)",
        "units": {
            "BTU/(hr.ft^2)": 3.15459075,
            "watt/square metre (W/m^2)": 1.0,
        },
    },
    "Specific Energy": {
        "base": "joule/kilogram (J/kg)",
        "units": {
            "BTU/lb": 2326.0,
            "BTU/lbm": 2326.0,
            "kcal/kg": 4184.0,
            "joule/kilogram (J/kg)": 1.0,
            "kilojoule/kilogram (kJ/kg)": 1000.0,
        },
    },
    "Mass Flow Rate": {
        "base": "kilogram/second (kg/s)",
        "units": {
            "pound/hour (lb/hr)": 0.00012599788,
            "pound/second (lb/s)": 0.45359237,
            "kilogram/second (kg/s)": 1.0,
            "kilogram/hour (kg/hr)": 0.000277778,
            "tonne/hour (t/hr)": 0.277778,
        },
    },
}

TEMPERATURE_UNITS = ["Fahrenheit (°F)", "Rankine (°R)", "Celsius (°C)", "Kelvin (K)"]


def temperature_to_kelvin(value: float, unit: str) -> float:
    if unit == "Fahrenheit (°F)":
        return (value - 32.0) * 5.0 / 9.0 + 273.15
    if unit == "Rankine (°R)":
        return value * 5.0 / 9.0
    if unit == "Celsius (°C)":
        return value + 273.15
    if unit == "Kelvin (K)":
        return value
    raise ValueError(f"Unknown temperature unit: {unit}")


def kelvin_to_temperature(value_k: float, unit: str) -> float:
    if unit == "Fahrenheit (°F)":
        return (value_k - 273.15) * 9.0 / 5.0 + 32.0
    if unit == "Rankine (°R)":
        return value_k * 9.0 / 5.0
    if unit == "Celsius (°C)":
        return value_k - 273.15
    if unit == "Kelvin (K)":
        return value_k
    raise ValueError(f"Unknown temperature unit: {unit}")


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class UnitConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("US <-> SI Unit Converter")
        self.geometry("460x300")
        self.resizable(False, False)

        self.all_categories = ["Temperature"] + list(CATEGORIES.keys())

        self._build_widgets()
        self._on_category_change()

    def _build_widgets(self):
        pad = {"padx": 10, "pady": 6}

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Category
        ttk.Label(main, text="Category:").grid(row=0, column=0, sticky="w", **pad)
        self.category_var = tk.StringVar(value=self.all_categories[0])
        category_box = ttk.Combobox(
            main, textvariable=self.category_var, values=self.all_categories,
            state="readonly", width=30
        )
        category_box.grid(row=0, column=1, columnspan=2, sticky="w", **pad)
        category_box.bind("<<ComboboxSelected>>", lambda e: self._on_category_change())

        # Input value
        ttk.Label(main, text="Value:").grid(row=1, column=0, sticky="w", **pad)
        self.value_var = tk.StringVar(value="1")
        value_entry = ttk.Entry(main, textvariable=self.value_var, width=15)
        value_entry.grid(row=1, column=1, sticky="w", **pad)
        value_entry.bind("<KeyRelease>", lambda e: self._convert())

        # From unit
        ttk.Label(main, text="From:").grid(row=2, column=0, sticky="w", **pad)
        self.from_var = tk.StringVar()
        self.from_box = ttk.Combobox(main, textvariable=self.from_var, state="readonly", width=30)
        self.from_box.grid(row=2, column=1, columnspan=2, sticky="w", **pad)
        self.from_box.bind("<<ComboboxSelected>>", lambda e: self._convert())

        # To unit
        ttk.Label(main, text="To:").grid(row=3, column=0, sticky="w", **pad)
        self.to_var = tk.StringVar()
        self.to_box = ttk.Combobox(main, textvariable=self.to_var, state="readonly", width=30)
        self.to_box.grid(row=3, column=1, columnspan=2, sticky="w", **pad)
        self.to_box.bind("<<ComboboxSelected>>", lambda e: self._convert())

        # Swap button
        swap_btn = ttk.Button(main, text="⇅ Swap", command=self._swap_units)
        swap_btn.grid(row=2, column=3, rowspan=2, padx=10)

        # Convert button (also lets Enter key trigger it)
        convert_btn = ttk.Button(main, text="Convert", command=self._convert)
        convert_btn.grid(row=4, column=1, sticky="w", pady=(12, 6))
        self.bind("<Return>", lambda e: self._convert())

        # Result
        ttk.Label(main, text="Result:").grid(row=5, column=0, sticky="w", **pad)
        self.result_var = tk.StringVar(value="")
        result_label = ttk.Label(
            main, textvariable=self.result_var, font=("Segoe UI", 12, "bold")
        )
        result_label.grid(row=5, column=1, columnspan=3, sticky="w", **pad)

    def _current_units(self):
        cat = self.category_var.get()
        if cat == "Temperature":
            return TEMPERATURE_UNITS
        return list(CATEGORIES[cat]["units"].keys())

    def _on_category_change(self):
        units = self._current_units()
        self.from_box["values"] = units
        self.to_box["values"] = units
        # sensible defaults: first US-style unit -> first SI-style unit
        self.from_var.set(units[0])
        self.to_var.set(units[-1])
        self._convert()

    def _swap_units(self):
        f, t = self.from_var.get(), self.to_var.get()
        self.from_var.set(t)
        self.to_var.set(f)
        self._convert()

    def _convert(self):
        cat = self.category_var.get()
        try:
            value = float(self.value_var.get())
        except ValueError:
            self.result_var.set("Enter a valid number")
            return

        from_unit = self.from_var.get()
        to_unit = self.to_var.get()
        if not from_unit or not to_unit:
            return

        try:
            if cat == "Temperature":
                kelvin = temperature_to_kelvin(value, from_unit)
                result = kelvin_to_temperature(kelvin, to_unit)
            else:
                units = CATEGORIES[cat]["units"]
                base_value = value * units[from_unit]
                result = base_value / units[to_unit]
        except (ValueError, ZeroDivisionError):
            self.result_var.set("Conversion error")
            return

        self.result_var.set(f"{result:,.6g} {to_unit}")


if __name__ == "__main__":
    app = UnitConverterApp()
    app.mainloop()