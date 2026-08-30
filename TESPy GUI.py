"""
TESPy Drag-and-Drop Cycle Builder
==================================

A visual editor for building TESPy thermodynamic cycle models.

- Drag components onto the canvas from the palette
- Click "Connect", then click a source component then a target component
  to draw a connection (you'll be asked which ports to use)
- Double-click any component to edit its attributes (eta_s, Q, pr, ...)
- Double-click any connection to edit its state (fluid, m, p, T, h, x, ...)
- Press "Build & Solve" to construct a real TESPy Network from the diagram
  and solve it. Results appear in the Results tab.
- "Export to Python Script" writes a standalone .py file that reproduces
  the diagram in code, for examiner traceability / version control.

Requirements:
    pip install tespy CoolProp
    (tkinter ships with standard Python on Windows / most Linux distros;
     on some Linux distros you may need `sudo apt install python3-tk`)

Optional custom component:
    If multi_stage_turbine.py (defining MultiStageExtractionTurbine) is
    placed in the same folder as this file, a "MultiStageExtractionTurbine"
    entry appears in the palette - a single component with 1 inlet and N
    outlets (N-1 extraction bleeds + 1 final exhaust), with independent
    eta_s1..eta_sN isentropic efficiencies per stage. Without that file
    present, the GUI still runs fine - that palette entry just won't build.

Run:
    python tespy_gui.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import uuid
import io
import json
import contextlib
import traceback

# ---------------------------------------------------------------------------
# Component registry: name -> (default_num_in, default_num_out,
#                               variable_port_side or None, [attr names])
# variable_port_side: "in" (Merge) or "out" (Splitter) means the user is
# asked how many ports to create when placing the component.
# ---------------------------------------------------------------------------
COMPONENT_SPECS = {
    "Source":                     (0, 1, None,  []),
    "Sink":                        (1, 0, None,  []),
    "CycleCloser":                 (1, 1, None,  []),
    "Splitter":                    (1, 2, "out", []),
    "Merge":                       (2, 1, "in",  []),
    "Turbine":                     (1, 1, None,  ["eta_s", "pr"]),
    "SteamTurbine":                (1, 1, None,  ["eta_s", "pr"]),
    "Compressor":                  (1, 1, None,  ["eta_s", "pr"]),
    "Pump":                        (1, 1, None,  ["eta_s", "pr"]),
    "SimpleHeatExchanger":         (1, 1, None,  ["Q", "pr", "ttd_u", "ttd_l", "kA"]),
    "HeatExchanger":               (2, 2, None,  ["Q", "pr1", "pr2", "ttd_u", "ttd_l", "kA"]),
    "Condenser":                   (2, 2, None,  ["Q", "pr1", "pr2", "ttd_u"]),
    "Valve":                       (1, 1, None,  ["pr", "dp"]),
    "DropletSeparator":            (1, 2, None,  []),
    "Drum":                        (2, 2, None,  []),
    # attrs=[] here because NodeEditor generates eta_s1..eta_sN dynamically
    # based on how many stages this particular node was placed with.
    "MultiStageExtractionTurbine": (1, 2, "out", []),
}

# Constructor kwarg name used for each component's variable port count.
# (Splitter/Merge/MultiStageExtractionTurbine all take a different name.)
VARIABLE_PORT_KWARG = {
    "Splitter": "num_out",
    "Merge": "num_in",
    "MultiStageExtractionTurbine": "num_stages",
}

# Custom placement-dialog wording + minimum count per variable-port type.
# Falls back to a generic "in"/"out" prompt with minvalue=2 if not listed.
PORT_PROMPT = {
    "MultiStageExtractionTurbine": (
        "Number of stages",
        "How many expansion stages? (stages 1..N-1 are extraction bleeds,\n"
        "the last stage is the final exhaust)",
        1,
    ),
}

CONNECTION_ATTRS = ["fluid", "m", "p", "T", "h", "x",
                    "m0", "p0", "T0", "h0", "x0"]

UNIT_OPTIONS = {
    "temperature": ["K", "degC", "F", "R"],
    "pressure": ["Pa", "bar", "MPa", "psi"],
    "enthalpy": ["J/kg", "kJ/kg", "Btu/lb"],
    "power": ["W", "kW", "MW"],
    "mass_flow": ["kg/s", "t/h", "lb/s"],
}


def get_tespy_classes():
    """Import deferred so the GUI can open even without tespy installed."""
    from tespy.components import (
        Source, Sink, Splitter, Merge, Turbine, SteamTurbine, Compressor,
        Pump, HeatExchanger, Condenser, CycleCloser, Valve, SimpleHeatExchanger,
        DropletSeparator, Drum,
    )
    classes = dict(
        Source=Source, Sink=Sink, Splitter=Splitter, Merge=Merge,
        Turbine=Turbine, SteamTurbine=SteamTurbine, Compressor=Compressor,
        Pump=Pump, HeatExchanger=HeatExchanger, Condenser=Condenser,
        CycleCloser=CycleCloser, Valve=Valve,SimpleHeatExchanger=SimpleHeatExchanger,
        DropletSeparator=DropletSeparator, Drum=Drum,
    )

    # Optional custom component - only added if multi_stage_turbine.py is
    # sitting next to this script. Its absence must never break the rest
    # of the palette, so failures here are swallowed silently; the error
    # only surfaces if the user actually tries to build with that type
    # (see build_and_solve / export_script).
    try:
        from MultistageTurbine import MultiStageExtractionTurbine
        classes["MultiStageExtractionTurbine"] = MultiStageExtractionTurbine
    except Exception:
        pass

    return classes


# ---------------------------------------------------------------------------
# Node (component instance on the canvas)
# ---------------------------------------------------------------------------
class Node:
    def __init__(self, app, ctype, node_id, x, y, num_in, num_out, label):
        self.app = app
        self.ctype = ctype
        self.id = node_id
        self.x = x
        self.y = y
        self.num_in = num_in
        self.num_out = num_out
        self.label = label
        self.attrs = {}          # attr name -> string value
        self.custom_attrs = {}   # extra attr name -> string value
        self.w = 120
        self.h = max(50, 22 * max(num_in, num_out, 1))
        self.items = []
        self.draw()

    def bbox(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def draw(self):
        c = self.app.canvas
        for it in self.items:
            c.delete(it)
        self.items = []
        x0, y0, x1, y1 = self.bbox()
        rect = c.create_rectangle(
            x0, y0, x1, y1, fill="#dbeafe", outline="#1e3a8a", width=2,
            tags=("node", self.id))
        text = c.create_text(
            (x0 + x1) / 2, (y0 + y1) / 2,
            text=f"{self.label}\n[{self.ctype}]",
            tags=("node", self.id), font=("Segoe UI", 9, "bold"), width=self.w - 10)
        self.items = [rect, text]
        for i in range(self.num_in):
            px, py = self.port_pos("in", i)
            pid = c.create_oval(
                px - 4, py - 4, px + 4, py + 4, fill="#16a34a", outline="",
                tags=("port", self.id, f"in{i + 1}"))
            lbl = c.create_text(px + 10, py, text=f"in{i + 1}", anchor="w",
                                 font=("Segoe UI", 6), tags=("node", self.id))
            self.items += [pid, lbl]
        for i in range(self.num_out):
            px, py = self.port_pos("out", i)
            pid = c.create_oval(
                px - 4, py - 4, px + 4, py + 4, fill="#dc2626", outline="",
                tags=("port", self.id, f"out{i + 1}"))
            lbl = c.create_text(px - 10, py, text=f"out{i + 1}", anchor="e",
                                 font=("Segoe UI", 6), tags=("node", self.id))
            self.items += [pid, lbl]

    def port_pos(self, side, idx):
        x0, y0, x1, y1 = self.bbox()
        n = self.num_in if side == "in" else self.num_out
        frac = (idx + 1) / (n + 1)
        y = y0 + frac * (y1 - y0)
        x = x0 if side == "in" else x1
        return x, y

    def move_to(self, x, y):
        dx, dy = x - self.x, y - self.y
        self.x, self.y = x, y
        for it in self.items:
            self.app.canvas.move(it, dx, dy)
        self.app.refresh_edges_for_node(self)

    def to_dict(self):
        return dict(id=self.id, ctype=self.ctype, x=self.x, y=self.y,
                    num_in=self.num_in, num_out=self.num_out,
                    label=self.label, attrs=self.attrs,
                    custom_attrs=self.custom_attrs)


# ---------------------------------------------------------------------------
# Edge (connection instance on the canvas)
# ---------------------------------------------------------------------------
class Edge:
    def __init__(self, app, edge_id, src_node, src_port, dst_node, dst_port, label):
        self.app = app
        self.id = edge_id
        self.src_node = src_node
        self.src_port = src_port
        self.dst_node = dst_node
        self.dst_port = dst_port
        self.label = label
        self.attrs = {}
        self.line = None
        self.text = None
        self.draw()

    def endpoints(self):
        sidx = int(self.src_port.replace("out", "")) - 1
        didx = int(self.dst_port.replace("in", "")) - 1
        sx, sy = self.src_node.port_pos("out", sidx)
        dx, dy = self.dst_node.port_pos("in", didx)
        return sx, sy, dx, dy

    def draw(self):
        c = self.app.canvas
        if self.line:
            c.delete(self.line)
        if self.text:
            c.delete(self.text)
        sx, sy, dx, dy = self.endpoints()
        self.line = c.create_line(
            sx, sy, dx, dy, arrow=tk.LAST, width=2, fill="#334155",
            tags=("edge", self.id))
        mx, my = (sx + dx) / 2, (sy + dy) / 2
        self.text = c.create_text(
            mx, my - 8, text=self.label, fill="#334155",
            font=("Segoe UI", 7), tags=("edge", self.id))
        c.tag_lower(self.line)

    def to_dict(self):
        return dict(id=self.id, src=self.src_node.id, src_port=self.src_port,
                    dst=self.dst_node.id, dst_port=self.dst_port,
                    label=self.label, attrs=self.attrs)


# ---------------------------------------------------------------------------
# Attribute editor dialogs
# ---------------------------------------------------------------------------
class NodeEditor(tk.Toplevel):
    def __init__(self, master, node):
        super().__init__(master)
        self.node = node
        self.title(f"Edit {node.label}")
        self.resizable(False, False)
        self.entries = {}

        row = 0
        ttk.Label(self, text="Label:").grid(row=row, column=0, sticky="e", padx=4, pady=3)
        self.label_var = tk.StringVar(value=node.label)
        ttk.Entry(self, textvariable=self.label_var, width=22).grid(
            row=row, column=1, padx=4, pady=3)
        row += 1

        attr_names = self._attr_names_for(node)
        for name in attr_names:
            ttk.Label(self, text=f"{name}:").grid(row=row, column=0, sticky="e", padx=4, pady=3)
            var = tk.StringVar(value=node.attrs.get(name, ""))
            ttk.Entry(self, textvariable=var, width=22).grid(row=row, column=1, padx=4, pady=3)
            self.entries[name] = var
            row += 1

        ttk.Label(self, text="Custom attrs (one 'name=value' per line):").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 0))
        row += 1
        self.custom_text = tk.Text(self, width=32, height=4)
        self.custom_text.grid(row=row, column=0, columnspan=2, padx=4, pady=3)
        self.custom_text.insert(
            "1.0", "\n".join(f"{k}={v}" for k, v in node.custom_attrs.items()))
        row += 1

        btns = ttk.Frame(self)
        btns.grid(row=row, column=0, columnspan=2, pady=8)
        ttk.Button(btns, text="Save", command=self.save).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=4)

    @staticmethod
    def _attr_names_for(node):
        """Which attribute fields to show for this node.

        Static list for most component types (from COMPONENT_SPECS), but
        MultiStageExtractionTurbine gets one eta_s field per stage the
        node actually has (node.num_out), since that count is only known
        once the node is placed.
        """
        if node.ctype == "MultiStageExtractionTurbine":
            return [f"eta_s{i}" for i in range(1, node.num_out + 1)]
        _, _, _, attr_names = COMPONENT_SPECS.get(node.ctype, (1, 1, None, []))
        return attr_names

    def save(self):
        self.node.label = self.label_var.get().strip() or self.node.label
        for name, var in self.entries.items():
            v = var.get().strip()
            if v:
                self.node.attrs[name] = v
            elif name in self.node.attrs:
                del self.node.attrs[name]
        custom = {}
        for line in self.custom_text.get("1.0", "end").splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            custom[k.strip()] = v.strip()
        self.node.custom_attrs = custom
        self.node.draw()
        self.destroy()


class EdgeEditor(tk.Toplevel):
    def __init__(self, master, edge):
        super().__init__(master)
        self.edge = edge
        self.title(f"Edit {edge.label}")
        self.resizable(False, False)
        self.entries = {}

        row = 0
        ttk.Label(self, text="Label:").grid(row=row, column=0, sticky="e", padx=4, pady=3)
        self.label_var = tk.StringVar(value=edge.label)
        ttk.Entry(self, textvariable=self.label_var, width=22).grid(
            row=row, column=1, padx=4, pady=3)
        row += 1

        ttk.Label(self, text="fluid (e.g. water:1  or  water:0.9,air:0.1):").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(6, 0))
        row += 1
        var = tk.StringVar(value=edge.attrs.get("fluid", ""))
        ttk.Entry(self, textvariable=var, width=32).grid(
            row=row, column=0, columnspan=2, padx=4, pady=3)
        self.entries["fluid"] = var
        row += 1

        for name in ["m", "p", "T", "h", "x", "m0", "p0", "T0", "h0", "x0"]:
            ttk.Label(self, text=f"{name}:").grid(row=row, column=0, sticky="e", padx=4, pady=2)
            v = tk.StringVar(value=edge.attrs.get(name, ""))
            ttk.Entry(self, textvariable=v, width=22).grid(row=row, column=1, padx=4, pady=2)
            self.entries[name] = v
            row += 1

        btns = ttk.Frame(self)
        btns.grid(row=row, column=0, columnspan=2, pady=8)
        ttk.Button(btns, text="Save", command=self.save).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=4)

    def save(self):
        self.edge.label = self.label_var.get().strip() or self.edge.label
        for name, var in self.entries.items():
            v = var.get().strip()
            if v:
                self.edge.attrs[name] = v
            elif name in self.edge.attrs:
                del self.edge.attrs[name]
        self.edge.draw()
        self.destroy()


class NetworkSettingsDialog(tk.Toplevel):
    def __init__(self, master, settings):
        super().__init__(master)
        self.title("Network Settings (unit defaults)")
        self.resizable(False, False)
        self.settings = settings
        self.vars = {}
        row = 0
        for key, options in UNIT_OPTIONS.items():
            ttk.Label(self, text=f"{key}:").grid(row=row, column=0, sticky="e", padx=4, pady=4)
            var = tk.StringVar(value=settings.get(key, options[0]))
            ttk.Combobox(self, textvariable=var, values=options, width=10,
                         state="readonly").grid(row=row, column=1, padx=4, pady=4)
            self.vars[key] = var
            row += 1
        btns = ttk.Frame(self)
        btns.grid(row=row, column=0, columnspan=2, pady=8)
        ttk.Button(btns, text="Save", command=self.save).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=4)

    def save(self):
        for key, var in self.vars.items():
            self.settings[key] = var.get()
        self.destroy()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class TespyGuiApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TESPy Drag-and-Drop Cycle Builder")
        self.geometry("1200x750")

        self.nodes = {}   # id -> Node
        self.edges = {}   # id -> Edge
        self.pending_type = None
        self.pending_num = None
        self.mode = tk.StringVar(value="move")
        self.connect_src = None
        self.drag_node = None
        self.drag_offset = (0, 0)
        self.net_settings = dict(temperature="K", pressure="Pa", enthalpy="J/kg",
                                  power="W", mass_flow="kg/s")
        self._counters = {}

        self._build_ui()

    # -- UI construction -----------------------------------------------
    def _build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        editor_tab = ttk.Frame(self.notebook)
        results_tab = ttk.Frame(self.notebook)
        self.notebook.add(editor_tab, text="Editor")
        self.notebook.add(results_tab, text="Results")

        # --- Editor tab layout ---
        toolbar = ttk.Frame(editor_tab)
        toolbar.pack(side="top", fill="x", padx=4, pady=4)

        ttk.Radiobutton(toolbar, text="Move", variable=self.mode, value="move").pack(side="left")
        ttk.Radiobutton(toolbar, text="Connect", variable=self.mode, value="connect").pack(side="left")
        ttk.Radiobutton(toolbar, text="Delete", variable=self.mode, value="delete").pack(side="left")
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(toolbar, text="Network Settings", command=self.open_settings).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Build & Solve", command=self.build_and_solve).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Export to Python Script", command=self.export_script).pack(side="left", padx=2)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(toolbar, text="Save Diagram", command=self.save_diagram).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Load Diagram", command=self.load_diagram).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Clear", command=self.clear_diagram).pack(side="left", padx=2)

        body = ttk.Frame(editor_tab)
        body.pack(fill="both", expand=True)

        # Palette
        palette = ttk.Frame(body, width=160)
        palette.pack(side="left", fill="y", padx=4, pady=4)
        ttk.Label(palette, text="Components", font=("Segoe UI", 10, "bold")).pack(pady=(0, 6))
        for ctype in COMPONENT_SPECS:
            ttk.Button(palette, text=ctype, width=18,
                       command=lambda t=ctype: self.select_palette(t)).pack(pady=2)
        self.pending_label = ttk.Label(palette, text="", foreground="#1e3a8a",
                                        wraplength=150, font=("Segoe UI", 8, "italic"))
        self.pending_label.pack(pady=8)

        # Canvas with scrollbars
        canvas_frame = ttk.Frame(body)
        canvas_frame.pack(side="left", fill="both", expand=True)
        xscroll = ttk.Scrollbar(canvas_frame, orient="horizontal")
        yscroll = ttk.Scrollbar(canvas_frame, orient="vertical")
        self.canvas = tk.Canvas(canvas_frame, bg="white",
                                 scrollregion=(0, 0, 2500, 2000),
                                 xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        xscroll.config(command=self.canvas.xview)
        yscroll.config(command=self.canvas.yview)
        xscroll.pack(side="bottom", fill="x")
        yscroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        # --- Results tab layout ---
        self.results_tree = ttk.Treeview(
            results_tab,
            columns=("conn", "source", "target", "fluid", "m", "p", "T", "h", "x"),
            show="headings", height=15)
        for col, width in [("conn", 140), ("source", 160), ("target", 160), ("fluid", 120),
                            ("m", 90), ("p", 100), ("T", 90), ("h", 100), ("x", 60)]:
            self.results_tree.heading(col, text=col)
            self.results_tree.column(col, width=width, anchor="center")
        self.results_tree.pack(fill="x", padx=6, pady=6)

        ttk.Label(results_tab, text="Solver Log:", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=6)
        self.log_text = tk.Text(results_tab, height=18, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    # -- Palette / placement --------------------------------------------
    def select_palette(self, ctype):
        self.pending_type = ctype
        self.pending_label.config(text=f"Click on the canvas to place a {ctype}")

    def next_label(self, ctype):
        n = self._counters.get(ctype, 0) + 1
        self._counters[ctype] = n
        return f"{ctype}_{n}"

    def place_node(self, ctype, x, y):
        d_in, d_out, var_side, _ = COMPONENT_SPECS[ctype]
        num_in, num_out = d_in, d_out
        if var_side == "out":
            title, text, minval = PORT_PROMPT.get(
                ctype, ("Number of outputs", f"How many outputs for this {ctype}?", 2))
            n = simpledialog.askinteger(
                title, text, initialvalue=max(minval, d_out),
                minvalue=minval, maxvalue=12, parent=self)
            if n:
                num_out = n
        elif var_side == "in":
            title, text, minval = PORT_PROMPT.get(
                ctype, ("Number of inputs", f"How many inputs for this {ctype}?", 2))
            n = simpledialog.askinteger(
                title, text, initialvalue=max(minval, d_in),
                minvalue=minval, maxvalue=12, parent=self)
            if n:
                num_in = n
        node_id = str(uuid.uuid4())
        node = Node(self, ctype, node_id, x, y, num_in, num_out, self.next_label(ctype))
        self.nodes[node_id] = node

    # -- Canvas interaction -----------------------------------------------
    def _item_under_cursor(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(x - 3, y - 3, x + 3, y + 3)
        for it in reversed(items):
            tags = self.canvas.gettags(it)
            if "node" in tags or "port" in tags:
                return "node", tags[1]
            if "edge" in tags:
                return "edge", tags[1]
        return None, None

    def on_canvas_click(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        if self.pending_type:
            self.place_node(self.pending_type, x, y)
            self.pending_type = None
            self.pending_label.config(text="")
            return

        kind, obj_id = self._item_under_cursor(event)

        if self.mode.get() == "connect":
            if kind == "node":
                node = self.nodes[obj_id]
                if self.connect_src is None:
                    if node.num_out == 0:
                        messagebox.showinfo("Connect", f"{node.label} has no outputs.")
                        return
                    self.connect_src = node
                    self.canvas.itemconfig(node.items[0], outline="#f59e0b", width=3)
                else:
                    if node is self.connect_src:
                        return
                    if node.num_in == 0:
                        messagebox.showinfo("Connect", f"{node.label} has no inputs.")
                        return
                    self._make_edge(self.connect_src, node)
                    self.canvas.itemconfig(self.connect_src.items[0], outline="#1e3a8a", width=2)
                    self.connect_src = None
            return

        if self.mode.get() == "delete":
            if kind == "node":
                self.delete_node(obj_id)
            elif kind == "edge":
                self.delete_edge(obj_id)
            return

        # move mode
        if kind == "node":
            node = self.nodes[obj_id]
            self.drag_node = node
            self.drag_offset = (x - node.x, y - node.y)

    def _make_edge(self, src_node, dst_node):
        src_port = "out1" if src_node.num_out == 1 else simpledialog.askstring(
            "Source port", f"Which output port on {src_node.label}? "
            f"(out1..out{src_node.num_out})", initialvalue="out1", parent=self)
        dst_port = "in1" if dst_node.num_in == 1 else simpledialog.askstring(
            "Target port", f"Which input port on {dst_node.label}? "
            f"(in1..in{dst_node.num_in})", initialvalue="in1", parent=self)
        if not src_port or not dst_port:
            return
        edge_id = str(uuid.uuid4())
        label = f"c_{src_node.label}_{dst_node.label}"
        edge = Edge(self, edge_id, src_node, src_port, dst_node, dst_port, label)
        self.edges[edge_id] = edge

    def on_canvas_double_click(self, event):
        kind, obj_id = self._item_under_cursor(event)
        if kind == "node":
            NodeEditor(self, self.nodes[obj_id])
        elif kind == "edge":
            EdgeEditor(self, self.edges[obj_id])

    def on_canvas_drag(self, event):
        if self.mode.get() != "move" or self.drag_node is None:
            return
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        nx, ny = x - self.drag_offset[0], y - self.drag_offset[1]
        self.drag_node.move_to(nx, ny)

    def on_canvas_release(self, event):
        self.drag_node = None

    def refresh_edges_for_node(self, node):
        for edge in self.edges.values():
            if edge.src_node is node or edge.dst_node is node:
                edge.draw()

    def delete_node(self, node_id):
        node = self.nodes.pop(node_id, None)
        if not node:
            return
        for it in node.items:
            self.canvas.delete(it)
        for eid in [eid for eid, e in self.edges.items()
                    if e.src_node.id == node_id or e.dst_node.id == node_id]:
            self.delete_edge(eid)

    def delete_edge(self, edge_id):
        edge = self.edges.pop(edge_id, None)
        if not edge:
            return
        self.canvas.delete(edge.line)
        self.canvas.delete(edge.text)

    def clear_diagram(self):
        if not messagebox.askyesno("Clear", "Remove all components and connections?"):
            return
        self.canvas.delete("all")
        self.nodes.clear()
        self.edges.clear()
        self._counters.clear()

    def open_settings(self):
        NetworkSettingsDialog(self, self.net_settings)

    # -- fluid parsing ----------------------------------------------------
    @staticmethod
    def _parse_fluid(text):
        d = {}
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                name, frac = part.split(":", 1)
                d[name.strip()] = float(frac)
            else:
                d[part] = 1.0
        return d

    @staticmethod
    def _coerce(val):
        try:
            return float(val)
        except ValueError:
            return val

    # -- Build & Solve ------------------------------------------------------
    def build_and_solve(self):
        try:
            classes = get_tespy_classes()
        except Exception as e:
            messagebox.showerror(
                "TESPy not available",
                f"Could not import tespy. Install it with:\n\n    pip install tespy CoolProp\n\n{e}")
            return

        try:
            from tespy.networks import Network
            from tespy.connections import Connection

            net = Network()
            net.units.set_defaults(
                temperature=self.net_settings["temperature"],
                pressure=self.net_settings["pressure"],
                pressure_difference=self.net_settings["pressure"],
                enthalpy=self.net_settings["enthalpy"],
                heat=self.net_settings["power"],
                power=self.net_settings["power"],
                mass_flow=self.net_settings["mass_flow"],
            )

            comp_objs = {}
            for node in self.nodes.values():
                if node.ctype not in classes:
                    messagebox.showerror(
                        "Component not available",
                        f"'{node.ctype}' could not be imported. If this is "
                        "MultiStageExtractionTurbine, make sure "
                        "multi_stage_turbine.py is saved in the same folder "
                        "as this script.")
                    return
                cls = classes[node.ctype]
                kwargs = {}
                port_kwarg = VARIABLE_PORT_KWARG.get(node.ctype)
                if port_kwarg == "num_in":
                    kwargs[port_kwarg] = node.num_in
                elif port_kwarg is not None:
                    # num_out and num_stages both track the node's out-port count
                    kwargs[port_kwarg] = node.num_out
                comp = cls(node.label, **kwargs)

                set_kwargs = {}
                for k, v in {**node.attrs, **node.custom_attrs}.items():
                    set_kwargs[k] = self._coerce(v)
                if set_kwargs:
                    comp.set_attr(**set_kwargs)
                comp_objs[node.id] = comp

            if not self.edges:
                messagebox.showwarning("Build & Solve", "No connections have been drawn yet.")
                return

            conns = []
            for edge in self.edges.values():
                src = comp_objs[edge.src_node.id]
                dst = comp_objs[edge.dst_node.id]
                c = Connection(src, edge.src_port, dst, edge.dst_port, label=edge.label)
                set_kwargs = {}
                for k, v in edge.attrs.items():
                    if k == "fluid":
                        set_kwargs["fluid"] = self._parse_fluid(v)
                    else:
                        set_kwargs[k] = self._coerce(v)
                if set_kwargs:
                    c.set_attr(**set_kwargs)
                conns.append(c)

            net.add_conns(*conns)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                net.solve(mode="design")
            status = getattr(net, "status", None)

            self.show_results(conns, buf.getvalue(), status)
            self.notebook.select(1)

        except Exception:
            messagebox.showerror("Build/Solve Error", traceback.format_exc())

    def show_results(self, conns, log_output, status):
        for row in self.results_tree.get_children():
            self.results_tree.delete(row)

        def prop(conn, name):
            try:
                obj = getattr(conn, name)
                return round(obj.val, 4)
            except Exception:
                return ""

        for c in conns:
            fluid_str = ""
            try:
                fluid_str = ", ".join(
                    f"{k}:{v:.3f}" for k, v in c.fluid.val.items() if v > 1e-4)
            except Exception:
                pass
            self.results_tree.insert("", "end", values=(
                c.label, c.source.label, c.target.label, fluid_str,
                prop(c, "m"), prop(c, "p"), prop(c, "T"), prop(c, "h"), prop(c, "x")))

        self.log_text.delete("1.0", "end")
        converged = "CONVERGED" if status == 0 else f"NOT CONVERGED (status={status})"
        self.log_text.insert("end", f"Status: {converged}\n\n")
        self.log_text.insert("end", log_output)

    # -- Export to script -----------------------------------------------
    def export_script(self):
        if not self.nodes:
            messagebox.showinfo("Export", "Nothing to export yet.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".py", filetypes=[("Python file", "*.py")],
            initialfile="generated_tespy_model.py")
        if not path:
            return

        used_types = {node.ctype for node in self.nodes.values()}

        lines = []
        lines.append("# Auto-generated by TESPy Drag-and-Drop Cycle Builder")
        lines.append("from tespy.networks import Network")
        lines.append("from tespy.components import (")
        lines.append("    Source, Sink, Splitter, Merge, Turbine, SteamTurbine,")
        lines.append("    Compressor, Pump, HeatExchanger, Condenser, CycleCloser,")
        lines.append("    Valve, DropletSeparator, Drum")
        lines.append(")")
        if "MultiStageExtractionTurbine" in used_types:
            lines.append("from multi_stage_turbine import MultiStageExtractionTurbine")
        lines.append("from tespy.connections import Connection")
        lines.append("")
        lines.append("net = Network()")
        lines.append("net.units.set_defaults(")
        lines.append(f"    temperature='{self.net_settings['temperature']}',")
        lines.append(f"    pressure='{self.net_settings['pressure']}',")
        lines.append(f"    pressure_difference='{self.net_settings['pressure']}',")
        lines.append(f"    enthalpy='{self.net_settings['enthalpy']}',")
        lines.append(f"    heat='{self.net_settings['power']}',")
        lines.append(f"    power='{self.net_settings['power']}',")
        lines.append(f"    mass_flow='{self.net_settings['mass_flow']}',")
        lines.append(")")
        lines.append("")

        var_names = {}
        for node in self.nodes.values():
            var = "c_" + "".join(ch if ch.isalnum() else "_" for ch in node.label)
            var_names[node.id] = var
            kwargs = ""
            port_kwarg = VARIABLE_PORT_KWARG.get(node.ctype)
            if port_kwarg == "num_in":
                kwargs = f", num_in={node.num_in}"
            elif port_kwarg is not None:
                kwargs = f", {port_kwarg}={node.num_out}"
            lines.append(f"{var} = {node.ctype}('{node.label}'{kwargs})")
            attrs = {**node.attrs, **node.custom_attrs}
            if attrs:
                attr_str = ", ".join(f"{k}={v}" for k, v in attrs.items())
                lines.append(f"{var}.set_attr({attr_str})")
        lines.append("")

        conn_vars = []
        for edge in self.edges.values():
            src_var = var_names[edge.src_node.id]
            dst_var = var_names[edge.dst_node.id]
            evar = "conn_" + "".join(ch if ch.isalnum() else "_" for ch in edge.label)
            conn_vars.append(evar)
            lines.append(
                f"{evar} = Connection({src_var}, '{edge.src_port}', "
                f"{dst_var}, '{edge.dst_port}', label='{edge.label}')")
            kw_parts = []
            for k, v in edge.attrs.items():
                if k == "fluid":
                    fluid_dict = self._parse_fluid(v)
                    kw_parts.append(f"fluid={fluid_dict}")
                else:
                    kw_parts.append(f"{k}={self._coerce(v)!r}")
            if kw_parts:
                lines.append(f"{evar}.set_attr({', '.join(kw_parts)})")
        lines.append("")
        lines.append(f"net.add_conns({', '.join(conn_vars)})")
        lines.append("")
        lines.append("net.solve(mode='design')")
        lines.append("print('Converged:', net.status == 0)")
        lines.append("net.print_results()")

        with open(path, "w") as f:
            f.write("\n".join(lines))
        messagebox.showinfo("Export", f"Script written to:\n{path}")

    # -- Save / load diagram (JSON) --------------------------------------
    def save_diagram(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON diagram", "*.json")])
        if not path:
            return
        data = dict(
            settings=self.net_settings,
            nodes=[n.to_dict() for n in self.nodes.values()],
            edges=[e.to_dict() for e in self.edges.values()],
        )
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load_diagram(self):
        path = filedialog.askopenfilename(filetypes=[("JSON diagram", "*.json")])
        if not path:
            return
        with open(path) as f:
            data = json.load(f)

        self.canvas.delete("all")
        self.nodes.clear()
        self.edges.clear()
        self._counters.clear()

        self.net_settings.update(data.get("settings", {}))

        for nd in data["nodes"]:
            node = Node(self, nd["ctype"], nd["id"], nd["x"], nd["y"],
                        nd["num_in"], nd["num_out"], nd["label"])
            node.attrs = nd.get("attrs", {})
            node.custom_attrs = nd.get("custom_attrs", {})
            node.draw()
            self.nodes[node.id] = node

        for ed in data["edges"]:
            edge = Edge(self, ed["id"], self.nodes[ed["src"]], ed["src_port"],
                        self.nodes[ed["dst"]], ed["dst_port"], ed["label"])
            edge.attrs = ed.get("attrs", {})
            edge.draw()
            self.edges[edge.id] = edge


if __name__ == "__main__":
    app = TespyGuiApp()
    app.mainloop()