"""T-s diagrams for the plant models in this project.

:func:`plot_ts_diagram` turns a solved TESPy network into a closed T-s diagram,
and running this file as a script writes the diagrams for configuration 1 and
configuration 2. ``AP1000V5.py`` uses the same function, so all three models
share one definition of what a cycle diagram looks like.

Closing the loop takes three things that are easy to get wrong.

TESPy publishes plotting data one entry per *stream* through a component, so a
two-stream heat exchanger has two entries and a multi-stage turbine one per
stage. Reading only the first entry - which is what the plotting code in
``AP1000V5.py`` originally did - throws away the cold side of every feedwater
heater, the reheat side of both interstage heaters, the separated vapour leaving
the moisture separator and every expansion stage past the first. The result is a
diagram with the compression and part of the expansion drawn and nothing joining
them up, which is why it did not look like a cycle. Collecting every stream
draws every state change in the loop.

Even then the isolines do not themselves form a closed shape. The condenser
merge mixes heater drains into the exhaust, so TESPy's condenser isoline
starts mid-dome instead of at the turbine exit. Walking the primary
mass-flow path and drawing the missing isotherm from that exhaust to the
condensate is what actually closes the figure.

The second thing is that the hybrid networks carry more than one fluid at a
time: configuration 2 has the nuclear steam and the organic working fluid in one
network because the nuclear condenser is also the ORC evaporator, and both
models have cooling water hanging off the condenser. A diagram is drawn for one
fluid, so the streams have to be filtered down to it, and the cooling water has
to be dropped even though it is water like the steam - it is an open branch
between a source and a sink, not part of any cycle.

The oil loop is deliberately not plotted. Therminol VP-1 is modelled through
CoolProp's incompressible backend, which has no vapour dome and therefore no
T-s diagram to draw it on.
"""

import math
import os

import matplotlib.pyplot as plt
import numpy as np
from fluprodia import FluidPropertyDiagram
from tespy.components import (
    Condenser, CycleCloser, DropletSeparator, HeatExchanger, Merge,
    Sink, Source, Splitter,
)

from MultistageTurbine import MultiStageExtractionTurbine


def _fluid_name(conn):
    """Name of the fluid a connection carries."""
    return max(conn.fluid.val, key=conn.fluid.val.get)


def _stream_ports(comp, stream):
    """Inlet and outlet behind one entry of a component's plotting data.

    Only the two-stream heat exchangers pair inlet i with outlet i. On a
    splitter, merge or separator the index counts branches that all carry the
    same fluid, and on a turbine or pump there is only ever one stream, so the
    first inlet answers the only question asked of this: which fluid the entry
    belongs to, and whether it comes from a source or goes to a sink.
    """
    if isinstance(comp, HeatExchanger):
        return comp.inl[stream - 1], comp.outl[stream - 1]
    if isinstance(comp, DropletSeparator):
        return comp.inl[0], comp.outl[stream - 1]
    if isinstance(comp, MultiStageExtractionTurbine):
        return comp._stage_inlet_conn(stream), comp._stage_outlet_conn(stream)
    return comp.inl[0], comp.outl[0]


def collect_processes(network, fluid):
    """Every process the given fluid undergoes in a solved network.

    Streams carrying another fluid are skipped, as are streams fed by a
    :class:`Source` or discharging into a :class:`Sink`: those are the cooling
    water branches, which are the right fluid but not part of the cycle.

    :return: plotting data keyed by a readable process name
    """
    processes = {}
    ports = {}
    for comp in network.comps["object"]:
        data = comp.get_plotting_data()
        if not data:
            continue
        for stream, path in data.items():
            inlet, outlet = _stream_ports(comp, stream)
            if _fluid_name(inlet) != fluid:
                continue
            if isinstance(inlet.source, Source) or isinstance(outlet.target, Sink):
                continue
            name = comp.label if len(data) == 1 else f"{comp.label} [{stream}]"
            processes[name] = path
            ports[name] = (inlet, outlet)
    return processes, ports


def _successor(conn):
    """The next connection on the primary working-fluid path after this one.

    Splitters keep the larger mass flow, so bleeds are dropped and the steam
    that is still expanding is followed. The moisture separator keeps the
    vapour: the liquid drain is a side stream. Two-stream heaters stay on the
    side they were entered from, which is what puts the feedwater climb and
    the reheat on the diagram and leaves the shell drains off it.
    """
    comp = conn.target
    if isinstance(comp, CycleCloser):
        return None
    if isinstance(comp, Splitter):
        return max(comp.outl, key=lambda outlet: abs(outlet.m.val_SI))
    if isinstance(comp, DropletSeparator):
        return comp.outl[1]
    if isinstance(comp, (HeatExchanger, Condenser)):
        for inlet, outlet in zip(comp.inl, comp.outl):
            if inlet is conn:
                return outlet
        return None
    if isinstance(comp, Merge):
        return comp.outl[0]
    if getattr(comp, "outl", None):
        return comp.outl[0]
    return None


def walk_main_cycle(network, fluid):
    """Connections around the primary loop of one fluid, in flow order.

    TESPy will not draw a CycleCloser or a splitter, and the inherited turbine
    plotting data only covered the first extraction, so a diagram built from
    component isolines alone stopped in mid-expansion and never came back up
    the feedwater train. Walking the largest-flow path from the cycle closer
    and recording every state on it - including the intermediate outlets of a
    :class:`MultiStageExtractionTurbine` - gives the polyline that actually
    closes.

    :return: connections from the closer outlet back to the closer inlet
    """
    start = None
    for comp in network.comps["object"]:
        if isinstance(comp, CycleCloser) and _fluid_name(comp.outl[0]) == fluid:
            start = comp.outl[0]
            break
    if start is None:
        return []

    ordered = [start]
    conn = start
    seen = {id(start)}
    for _ in range(len(network.conns)):
        comp = conn.target
        if isinstance(comp, CycleCloser):
            break
        if isinstance(comp, MultiStageExtractionTurbine):
            for outlet in comp.outl:
                if id(outlet) not in seen:
                    ordered.append(outlet)
                    seen.add(id(outlet))
            conn = comp.outl[-1]
            continue
        nxt = _successor(conn)
        if nxt is None or id(nxt) in seen:
            break
        # A merge changes the state by mixing in another stream. The main
        # steam does not actually jump to that mixed enthalpy: it goes on
        # condensing from the turbine exhaust, and putting the mixed state
        # on the polyline is what left a gap at the bottom of the AP1000
        # diagram. Keep the merge for topology, leave it off the figure.
        if not isinstance(comp, Merge):
            ordered.append(nxt)
        seen.add(id(nxt))
        conn = nxt
    return ordered


# Which property each value in a plotting data entry is measured in, so the
# entry can be re-expressed in another unit system.
_VALUE_PROPERTIES = {
    "isoline_value": "isoline_property",
    "isoline_value_end": "isoline_property",
    "starting_point_value": "starting_point_property",
    "ending_point_value": "ending_point_property",
}


def _convert(process, convert):
    """Re-express one process's plotting values using the given conversion."""
    return {
        key: convert(value, process[_VALUE_PROPERTIES[key]])
        if key in _VALUE_PROPERTIES else value
        for key, value in process.items()
    }


def _nice_isolines(low, high, mantissas=(1, 2, 5)):
    """Round 1-2-5 values spanning a range, so the isoline labels read well."""
    if not (0 < low <= high):
        return np.array([])
    values = [
        mantissa * 10.0 ** exponent
        for exponent in range(
            math.floor(math.log10(low)), math.floor(math.log10(high)) + 1
        )
        for mantissa in mantissas
    ]
    return np.array([v for v in values if low <= v <= high])


def plot_ts_diagram(network, fluid, path, title, colour="#c1121f", figsize=(16, 9),
                    display_units=None):
    """Draw the T-s diagram of one fluid's cycle in a solved network and save it.

    :param network: a solved :class:`tespy.networks.Network`
    :param fluid: CoolProp name of the fluid to draw the cycle for
    :param path: file to write; the extension picks the format
    :param title: figure title
    :param display_units: units to draw in, defaulting to bar and kJ/kgK
    :return: the collected process names, in case the caller wants to check them
    """
    if display_units is None:
        display_units = {"p": "bar", "s": "kJ/kgK", "T": "K"}

    processes, ports = collect_processes(network, fluid)
    cycle_path = walk_main_cycle(network, fluid)
    path_ids = {id(conn) for conn in cycle_path}
    if path_ids:
        processes = {
            name: process for name, process in processes.items()
            if id(ports[name][0]) in path_ids or id(ports[name][1]) in path_ids
        }
    if not processes:
        raise ValueError(f"the network has no {fluid} processes to plot")

    # The plotting data comes off the connections in whatever units the network
    # reports, and the diagram is drawn in units that give readable isoline
    # labels - pressures in Pa label the lines '1000000.0 Pa' - so every value
    # is taken through SI on the way from one to the other.
    diagram = FluidPropertyDiagram(fluid)
    diagram.set_unit_system(units=network.units)
    processes = {
        name: _convert(process, diagram.convert_to_SI)
        for name, process in processes.items()
    }
    diagram.set_unit_system(**display_units)

    curves = {
        name: diagram.calc_individual_isoline(
            **_convert(process, diagram.convert_from_SI)
        )
        for name, process in processes.items()
    }

    def limits(prop, pad=0.0):
        values = np.concatenate([curve[prop] for curve in curves.values()])
        values = values[np.isfinite(values)]
        low, high = values.min(), values.max()
        margin = pad * (high - low)
        return low - margin, high + margin

    s_min, s_max = limits("s", pad=0.06)
    T_min, T_max = limits("T", pad=0.08)
    p_min, p_max = limits("p")
    if cycle_path:
        s_pts = [diagram.convert_from_SI(conn.s.val_SI, "s") for conn in cycle_path]
        T_pts = [diagram.convert_from_SI(conn.T.val_SI, "T") for conn in cycle_path]
        s_pad = 0.06 * (max(s_pts) - min(s_pts) or 1.0)
        T_pad = 0.08 * (max(T_pts) - min(T_pts) or 1.0)
        s_min, s_max = min(s_min, min(s_pts) - s_pad), max(s_max, max(s_pts) + s_pad)
        T_min, T_max = min(T_min, min(T_pts) - T_pad), max(T_max, max(T_pts) + T_pad)

    # Only the vapour dome, the quality lines inside it and the pressure lines
    # are drawn. Enthalpy and specific volume isolines are left off: on a T-s
    # diagram of a wet cycle they cross everything else and hide the states.
    diagram.set_isolines(
        Q=np.linspace(0, 1, 11),
        p=_nice_isolines(p_min, p_max),
        T=np.array([]),
        h=np.array([]),
        vol=np.array([]),
    )
    diagram.calc_isolines()

    fig, ax = plt.subplots(1, figsize=figsize)
    diagram.draw_isolines(
        fig, ax, "Ts",
        x_min=s_min, x_max=s_max,
        y_min=max(T_min, diagram.convert_from_SI(diagram.T_trip, "T")), y_max=T_max,
    )
    for text in ax.texts:
        text.set_fontsize(10)

    for name, curve in curves.items():
        s_vals = np.asarray(curve["s"])
        T_vals = np.asarray(curve["T"])
        finite = np.isfinite(s_vals) & np.isfinite(T_vals)
        if finite.sum() < 2:
            continue
        ax.plot(s_vals[finite], T_vals[finite], color=colour, linewidth=1.6,
                alpha=0.85)

    # Isolines follow the real process (isobaric boiling, polytropic
    # expansion). A straight polyline through every walked state would cut
    # chords across those, which is why the ORC diagram filled with
    # diagonals. The one segment isolines will not draw is condensation
    # from the turbine exhaust to the condensate: the condenser merge
    # mixes drains into that stream, so TESPy's isoline starts mid-dome.
    # Joining the coldest high-s state to the coldest low-s state is what
    # closes the figure.
    if len(cycle_path) >= 4:
        s_path = np.array([
            diagram.convert_from_SI(conn.s.val_SI, "s") for conn in cycle_path
        ])
        T_path = np.array([
            diagram.convert_from_SI(conn.T.val_SI, "T") for conn in cycle_path
        ])
        i_exh = int(np.argmax(s_path))
        near_sink = np.where(T_path <= T_path.min() + 5.0)[0]
        i_liq = near_sink[int(np.argmin(s_path[near_sink]))]
        # Wet exhaust condenses on an isotherm, so a straight line in T-s is
        # the real process. A dry organic exhaust is hotter than the
        # condensate and the condenser isoline already draws the desuperheat;
        # a chord across that would reopen the ORC diagram.
        if (
            abs(T_path[i_exh] - T_path[i_liq]) < 8.0
            and s_path[i_exh] - s_path[i_liq] > 0.05 * (s_path.max() - s_path.min())
        ):
            ax.plot(
                [s_path[i_exh], s_path[i_liq]],
                [T_path[i_exh], T_path[i_liq]],
                color=colour, linewidth=2.8, zorder=5,
            )
        ax.scatter(s_path, T_path, color=colour, s=22, zorder=4)

    units = diagram.units.default
    ax.set_xlabel(f"Entropy, s in {units['s']}", fontsize=16)
    ax.set_ylabel(f"Temperature, T in {units['T']}", fontsize=16)
    ax.set_title(title, fontsize=18)
    ax.tick_params(axis="x", labelsize=12)
    ax.tick_params(axis="y", labelsize=12)
    plt.tight_layout()

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fig.savefig(path)
    root, ext = os.path.splitext(path)
    if ext.lower() != ".png":
        fig.savefig(root + ".png", dpi=150)
    plt.close(fig)
    return sorted(processes)


def main(output_dir="ModelResults"):
    """Solve both configurations at their design point and plot their cycles."""
    from Configuration_1 import solve_configuration1
    from Configuration_2 import solve_configuration2

    configuration_1 = {}
    solve_configuration1(
        verbose=False, hourly=False, results_csv=None,
        design_point_out=configuration_1,
    )
    plot_ts_diagram(
        configuration_1["steam"], "water",
        os.path.join(output_dir, "configuration_1_ts.svg"),
        "Configuration 1: nuclear steam cycle with solar superheat and reheat",
    )

    configuration_2 = {}
    solve_configuration2(
        verbose=False, hourly=False, results_csv=None,
        design_point_out=configuration_2,
    )
    # Configuration 2 is two cycles in one network, so it gets two diagrams: the
    # topping cycle on water and the bottoming cycle on the organic fluid.
    plot_ts_diagram(
        configuration_2["steam"], "water",
        os.path.join(output_dir, "configuration_2_nuclear_ts.svg"),
        "Configuration 2: nuclear topping cycle",
    )
    plot_ts_diagram(
        configuration_2["steam"], "R245fa",
        os.path.join(output_dir, "configuration_2_orc_ts.svg"),
        "Configuration 2: organic Rankine bottoming cycle",
        colour="#0353a4",
    )


if __name__ == "__main__":
    main()
