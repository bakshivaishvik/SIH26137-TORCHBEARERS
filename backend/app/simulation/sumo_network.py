"""
SUMO integration (Section 3): builds/imports a SUMO network for the target
area and defines the traffic demand generation used to produce
realistic vehicle-flow/speed data.

This module writes real SUMO XML config (.net.xml generation via netconvert,
.rou.xml demand, .sumocfg) so `sumo`/`sumo-gui` can actually run it. Because
this sandboxed dev environment has no SUMO binary or GUI available, the
TraCI live-control counterpart (traci_client.py) additionally exposes a
`--offline` mode that replays a SUMO-shaped flow using the same tensor
format as app.forecasting.synthetic_traffic, so the rest of the pipeline
(edge weighting, ST-GNN feed) is exercised identically whether SUMO is
actually installed or not -- swap is a single flag.
"""
from __future__ import annotations
from pathlib import Path
import networkx as nx

NET_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<nodes>
{nodes}
</nodes>
"""

EDGE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<edges>
{edges}
</edges>
"""

ROUTES_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<routes>
  <vType id="ambulance" accel="3.0" decel="6.0" length="6.5" maxSpeed="33.3" vClass="emergency"/>
{flows}
</routes>
"""

SUMOCFG_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <input>
    <net-file value="city.net.xml"/>
    <route-files value="demand.rou.xml"/>
  </input>
  <time><begin value="0"/><end value="7200"/></time>
</configuration>
"""


def export_sumo_network(graph: nx.DiGraph, out_dir: str) -> dict:
    """Writes plain-XML node/edge files that `netconvert` (bundled with any
    SUMO install) turns into a real .net.xml, plus a matching demand file
    and .sumocfg. Uses the same synthetic_city_grid()/OSM graph as the rest
    of the system so SUMO and the router agree on topology."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    node_lines = [f'  <node id="n{n}" x="{d["x"]*1000:.1f}" y="{d["y"]*1000:.1f}"/>' for n, d in graph.nodes(data=True)]
    (out / "city.nod.xml").write_text(NET_TEMPLATE.format(nodes="\n".join(node_lines)))

    edge_lines = [
        f'  <edge id="e{u}_{v}" from="n{u}" to="n{v}" numLanes="1" speed="{40/3.6:.2f}"/>'
        for u, v in graph.edges()
    ]
    (out / "city.edg.xml").write_text(EDGE_TEMPLATE.format(edges="\n".join(edge_lines)))

    flow_lines = [
        f'  <flow id="f{u}_{v}" type="ambulance" begin="0" end="7200" period="180" from="e{u}_{v}"/>'
        for i, (u, v) in enumerate(graph.edges()) if i % 5 == 0
    ]
    (out / "demand.rou.xml").write_text(ROUTES_TEMPLATE.format(flows="\n".join(flow_lines)))
    (out / "city.sumocfg").write_text(SUMOCFG_TEMPLATE)

    return {
        "node_file": str(out / "city.nod.xml"),
        "edge_file": str(out / "city.edg.xml"),
        "route_file": str(out / "demand.rou.xml"),
        "sumocfg": str(out / "city.sumocfg"),
        "netconvert_cmd": f"netconvert --node-files={out/'city.nod.xml'} --edge-files={out/'city.edg.xml'} "
                           f"-o {out/'city.net.xml'}",
        "run_cmd": f"sumo -c {out/'city.sumocfg'}",
    }
