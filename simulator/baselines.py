"""Single-aircraft search baselines on the spatial grid: BFS, UCS, Greedy best-first, A*.

All four use the same 8-connected grid, the same step costs (1 orthogonal, sqrt(2) diagonal)
and the same blocked set, so they can be compared on path cost, nodes expanded, run time
and success rate. They plan in space only (no time, reservations or wind); the full
time-expanded planner in planner.py builds on the A* variant.

  BFS     fewest moves; ignores edge costs, so it can return a costlier route
  UCS     lowest accumulated cost g; optimal, but expands the most nodes
  Greedy  lowest heuristic h only; fast but can return a costlier route
  A*      g + h with the octile heuristic (admissible and consistent here): optimal
"""
import heapq
import math
import time
from collections import deque

from .grid import in_grid, octile

MOVES = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
ALGORITHMS = ("bfs", "ucs", "greedy", "astar")


def step_cost(a, b):
    return math.sqrt(2) if a[0] != b[0] and a[1] != b[1] else 1.0


def _neighbors(node, blocked):
    for dx, dy in MOVES:
        n = (node[0] + dx, node[1] + dy)
        if in_grid(n) and n not in blocked:
            yield n


def path_cost(path):
    return sum(step_cost(a, b) for a, b in zip(path, path[1:]))


def _rebuild(came, node):
    out = []
    while node is not None:
        out.append(node)
        node = came[node]
    return out[::-1]


def _bfs(start, goal, blocked):
    came, queue, expanded = {start: None}, deque([start]), 0
    while queue:
        node = queue.popleft()
        expanded += 1
        if node == goal:
            return _rebuild(came, node), expanded
        for n in _neighbors(node, blocked):
            if n not in came:
                came[n] = node
                queue.append(n)
    return None, expanded


def _best_first(start, goal, blocked, priority):
    """priority(g, h) -> key. ucs: g; greedy: h; astar: g + h."""
    counter = 0
    heap = [(priority(0.0, octile(start, goal)), counter, 0.0, start)]
    came, best_g, closed, expanded = {start: None}, {start: 0.0}, set(), 0
    while heap:
        _, _, g, node = heapq.heappop(heap)
        if node in closed:
            continue
        closed.add(node)
        expanded += 1
        if node == goal:
            return _rebuild(came, node), expanded
        for n in _neighbors(node, blocked):
            ng = g + step_cost(node, n)
            if n not in closed and ng < best_g.get(n, float("inf")):
                best_g[n] = ng
                came[n] = node
                counter += 1
                heapq.heappush(heap, (priority(ng, octile(n, goal)), counter, ng, n))
    return None, expanded


def search(algorithm, start, goal, blocked=frozenset()):
    """Run one algorithm. Returns dict(path, cost, expanded, ms, success)."""
    if algorithm not in ALGORITHMS:
        raise ValueError(f"algorithm must be one of {ALGORITHMS}")
    blocked = frozenset(blocked) - {start, goal}
    t0 = time.perf_counter()
    if algorithm == "bfs":
        path, expanded = _bfs(start, goal, blocked)
    elif algorithm == "ucs":
        path, expanded = _best_first(start, goal, blocked, lambda g, h: g)
    elif algorithm == "greedy":
        path, expanded = _best_first(start, goal, blocked, lambda g, h: h)
    else:
        path, expanded = _best_first(start, goal, blocked, lambda g, h: g + h)
    ms = (time.perf_counter() - t0) * 1000
    return {"algorithm": algorithm, "path": path, "success": path is not None,
            "cost": path_cost(path) if path else None, "moves": len(path) - 1 if path else None,
            "expanded": expanded, "ms": ms}
