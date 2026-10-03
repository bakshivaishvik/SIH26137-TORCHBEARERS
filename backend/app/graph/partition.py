"""
Hierarchical graph clustering for scalability (Section 2.4): Louvain
community detection decomposes the full city graph into sub-regions so
swarm optimization operates on manageable partitions for large N, with
a cross-partition stitching step (shortest inter-partition boundary edge)
for routes that must cross a cluster boundary.
"""
from __future__ import annotations
import networkx as nx
import networkx.algorithms.community as nx_comm


def louvain_partition(graph: nx.Graph, resolution: float = 1.0, seed: int = 0) -> dict:
    undirected = graph.to_undirected() if graph.is_directed() else graph
    communities = nx_comm.louvain_communities(undirected, weight="weight", resolution=resolution, seed=seed)
    node_to_partition = {}
    for pid, community in enumerate(communities):
        for node in community:
            node_to_partition[node] = pid
    return {"node_to_partition": node_to_partition, "n_partitions": len(communities),
            "partitions": [list(c) for c in communities]}


def stitch_cross_partition_route(graph: nx.Graph, partition_info: dict, source, target,
                                  intra_partition_path_fn) -> list:
    """If source/target fall in different partitions, route each leg inside
    its own partition to the nearest boundary node, then hop across the
    boundary edge, minimizing total stitched cost across candidate boundary
    edges between the two partitions."""
    n2p = partition_info["node_to_partition"]
    if n2p.get(source) == n2p.get(target):
        return intra_partition_path_fn(graph, source, target)

    p_source, p_target = n2p.get(source), n2p.get(target)
    boundary_edges = [
        (u, v) for u, v in graph.edges()
        if n2p.get(u) == p_source and n2p.get(v) == p_target
    ]
    if not boundary_edges:
        # no direct boundary edge -> fall back to full-graph shortest path
        return intra_partition_path_fn(graph, source, target)

    best_path, best_cost = None, float("inf")
    for u, v in boundary_edges:
        try:
            path1 = intra_partition_path_fn(graph, source, u)
            path2 = intra_partition_path_fn(graph, v, target)
        except Exception:
            continue
        if path1 is None or path2 is None:
            continue
        cost = len(path1) + len(path2)
        if cost < best_cost:
            best_cost = cost
            best_path = path1 + path2
    return best_path
