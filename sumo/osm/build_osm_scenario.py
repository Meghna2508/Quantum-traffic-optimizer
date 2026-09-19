#!/usr/bin/env python3
"""
Build a small OSM-derived SUMO scenario next to the synthetic 2x2 fixture.

Does not modify sumo/simulation.sumocfg or the synthetic network files.

Usage:
    python sumo/osm/build_osm_scenario.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import List, Optional, Sequence, Tuple

import sumolib


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OSM_FILE = os.path.join(HERE, "manhattan.osm")
NET_FILE = os.path.join(HERE, "manhattan.net.xml")
ROU_FILE = os.path.join(HERE, "manhattan.rou.xml")
CFG_FILE = os.path.join(HERE, "simulation_osm.sumocfg")
EMERGENCY_ROUTE_ID = "R_emergency"


def _tool_status() -> dict:
    sumo_tools = os.path.join(os.path.dirname(sumolib.__file__), "tools")
    # sumolib lives in site-packages/sumolib; SUMO tools are in site-packages/sumo/tools
    candidate_tools = [
        sumo_tools,
        os.path.join(os.path.dirname(os.path.dirname(sumolib.__file__)), "sumo", "tools"),
    ]
    tools_dir = next((p for p in candidate_tools if os.path.isdir(p)), "")

    def find_py(name: str) -> Optional[str]:
        for base in candidate_tools:
            path = os.path.join(base, name)
            if os.path.isfile(path):
                return path
        return None

    def find_bin(name: str) -> Optional[str]:
        which = shutil.which(name)
        if which:
            return which
        try:
            return sumolib.checkBinary(name)
        except Exception:
            return None

    return {
        "sumo": find_bin("sumo"),
        "netconvert": find_bin("netconvert"),
        "duarouter": find_bin("duarouter"),
        "osmGet.py": find_py("osmGet.py"),
        "osmBuild.py": find_py("osmBuild.py"),
        "osmWebWizard.py": find_py("osmWebWizard.py"),
        "randomTrips.py": find_py("randomTrips.py"),
        "tools_dir": tools_dir,
    }


def convert_osm(tools: dict) -> None:
    netconvert = tools["netconvert"]
    if not netconvert:
        raise RuntimeError("netconvert is not available")
    if not os.path.isfile(OSM_FILE):
        raise FileNotFoundError(f"Missing OSM extract: {OSM_FILE}")

    cmd = [
        netconvert,
        "--osm-files", OSM_FILE,
        "--output-file", NET_FILE,
        "--proj.utm", "true",
        "--geometry.remove", "true",
        "--tls.guess", "true",
        "--tls.join", "false",
        "--tls.discard-simple", "true",
        "--junctions.join", "true",
        "--no-warnings", "true",
    ]
    print("[osm] netconvert:", " ".join(cmd))
    subprocess.check_call(cmd)


def _usable_edges(net) -> List:
    edges = []
    for edge in net.getEdges():
        if edge.getFunction() != "":
            continue
        if edge.allows("passenger"):
            edges.append(edge)
    return edges


def _longest_path_through_tls(net) -> List[str]:
    """Pick a deterministic corridor that crosses at least two signalized junctions."""
    tls_nodes = {n.getID() for n in net.getNodes() if n.getType() == "traffic_light"}
    usable = _usable_edges(net)
    best: List[str] = []
    best_tls = 0

    for start in usable:
        for end in usable:
            if start.getID() == end.getID():
                continue
            if start.getToNode().getID() == end.getFromNode().getID() and start.getID() == end.getID():
                continue
            try:
                path = net.getShortestPath(start, end)
            except Exception:
                continue
            if not path or not path[0]:
                continue
            edges = path[0]
            node_ids = [edges[0].getFromNode().getID()] + [e.getToNode().getID() for e in edges]
            tls_hit = len([n for n in node_ids if n in tls_nodes])
            if tls_hit > best_tls or (tls_hit == best_tls and len(edges) > len(best)):
                if tls_hit >= 2:
                    best = [e.getID() for e in edges]
                    best_tls = tls_hit
        if best_tls >= 4:
            break
    if not best:
        # Fallback: first two connected passenger edges
        best = [usable[0].getID(), usable[min(1, len(usable) - 1)].getID()]
    return best


def _sample_flow_routes(net, n_routes: int = 8) -> List[Tuple[str, List[str]]]:
    usable = _usable_edges(net)
    if len(usable) < 2:
        raise RuntimeError("OSM network has too few passenger edges for routes")
    routes = []
    step = max(1, len(usable) // n_routes)
    idx = 0
    for i in range(n_routes):
        start = usable[(i * step) % len(usable)]
        end = usable[(-(i * step) - 1) % len(usable)]
        if start.getID() == end.getID():
            end = usable[(i * step + 3) % len(usable)]
        try:
            path = net.getShortestPath(start, end)
        except Exception:
            continue
        if not path or not path[0] or len(path[0]) < 2:
            continue
        edge_ids = [e.getID() for e in path[0]]
        routes.append((f"R{i + 1}", edge_ids))
        idx += 1
    if not routes:
        raise RuntimeError("Could not build OSM flow routes")
    return routes


def write_routes(net) -> dict:
    emergency_edges = _longest_path_through_tls(net)
    flows = _sample_flow_routes(net)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<routes>",
        '    <vType id="car" accel="2.8" decel="4.5" sigma="0.5" length="5.0"',
        '           minGap="2.5" maxSpeed="13.89" guiShape="passenger" color="0.2,0.6,1.0"/>',
        '    <vType id="truck" accel="2.0" decel="3.5" sigma="0.5" length="7.5"',
        '           minGap="3.0" maxSpeed="11.11" guiShape="truck" color="0.9,0.6,0.1"/>',
        '    <vType id="emergency" accel="3.5" decel="5.0" sigma="0.2" length="6.5"',
        '           minGap="2.0" maxSpeed="22.22" speedFactor="1.5" guiShape="emergency"',
        '           color="1.0,0.0,0.0" vClass="emergency"/>',
        "",
        f'    <route id="{EMERGENCY_ROUTE_ID}" edges="{" ".join(emergency_edges)}"/>',
    ]
    for rid, edges in flows:
        lines.append(f'    <route id="{rid}" edges="{" ".join(edges)}"/>')
    lines.append("")
    rates = [280, 240, 220, 200, 180, 160, 140, 120]
    for i, (rid, _) in enumerate(flows):
        vtype = "truck" if i % 4 == 3 else "car"
        lines.append(
            f'    <flow id="flow_{rid}" type="{vtype}" route="{rid}" '
            f'begin="0" end="2000" vehsPerHour="{rates[i % len(rates)]}"/>'
        )
    lines.append("")
    # Immediate presence so TraCI sees vehicles at step 0+
    for i, (rid, _) in enumerate(flows[:4]):
        lines.append(
            f'    <vehicle id="init_{i}" type="car" route="{rid}" '
            f'depart="0" departSpeed="8" departPos="10"/>'
        )
    lines.append("</routes>")
    with open(ROU_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return {
        "emergency_route_id": EMERGENCY_ROUTE_ID,
        "emergency_edges": emergency_edges,
        "flow_routes": {rid: edges for rid, edges in flows},
    }


def write_sumocfg() -> None:
    content = """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file value="manhattan.net.xml"/>
        <route-files value="manhattan.rou.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="2000"/>
    </time>
    <processing>
        <ignore-route-errors value="true"/>
    </processing>
</configuration>
"""
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        f.write(content)


def summarize(net, route_info: dict) -> dict:
    nodes = list(net.getNodes())
    tls_j = [n for n in nodes if n.getType() == "traffic_light"]
    edges = [e for e in net.getEdges() if e.getFunction() == ""]
    loc = net.getLocation() if hasattr(net, "getLocation") else None
    return {
        "net_file": os.path.relpath(NET_FILE, ROOT),
        "route_file": os.path.relpath(ROU_FILE, ROOT),
        "config_file": os.path.relpath(CFG_FILE, ROOT),
        "junctions": len(nodes),
        "signalized_junctions": len(tls_j),
        "signalized_ids": [n.getID() for n in tls_j],
        "edges": len(edges),
        "emergency_route_id": route_info["emergency_route_id"],
        "emergency_edges": route_info["emergency_edges"],
        "orig_boundary": getattr(net, "_origBoundary", None),
    }


def main() -> int:
    tools = _tool_status()
    print("[osm] tooling:")
    for k, v in tools.items():
        print(f"    {k}: {v or 'NOT FOUND'}")

    convert_osm(tools)
    net = sumolib.net.readNet(NET_FILE)
    route_info = write_routes(net)
    write_sumocfg()
    summary = summarize(net, route_info)
    print("[osm] scenario written:")
    for k, v in summary.items():
        print(f"    {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
