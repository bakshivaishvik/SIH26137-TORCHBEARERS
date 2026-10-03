"""
Classical exact shortest-path algorithms (Dijkstra / A*) for the Algorithm
Arena's point-to-point baseline (Section 5.2). These operate directly on
the road graph (NetworkX), unlike the population metaheuristics which solve
the multi-stop VRP layer -- this is the "what a non-VRP-aware classical
router would do" baseline the jury can compare QPSO against on the same
disruption event (single ambulance, depot -> incident).
"""
from __future__ import annotations
import heapq
import math
import networkx as nx


def dijkstra_shortest_path(graph: nx.Graph, source, target, weight="weight"):
    dist = {source: 0.0}
    prev = {}
    visited = set()
    pq = [(0.0, source)]
    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == target:
            break
        for v, data in graph[u].items():
            w = data.get(weight, 1.0)
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if target not in dist:
        return None, math.inf
    path = [target]
    while path[-1] != source:
        path.append(prev[path[-1]])
    path.reverse()
    return path, dist[target]


def _euclidean_heuristic(graph: nx.Graph, u, v):
    ux, uy = graph.nodes[u].get("x", 0.0), graph.nodes[u].get("y", 0.0)
    vx, vy = graph.nodes[v].get("x", 0.0), graph.nodes[v].get("y", 0.0)
    return math.hypot(ux - vx, uy - vy)


def astar_shortest_path(graph: nx.Graph, source, target, weight="weight"):
    dist = {source: 0.0}
    prev = {}
    visited = set()
    pq = [(0.0, source)]
    while pq:
        _, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == target:
            break
        for v, data in graph[u].items():
            w = data.get(weight, 1.0)
            nd = dist[u] + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd + _euclidean_heuristic(graph, v, target), v))
    if target not in dist:
        return None, math.inf
    path = [target]
    while path[-1] != source:
        path.append(prev[path[-1]])
    path.reverse()
    return path, dist[target]
