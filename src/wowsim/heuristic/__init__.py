"""Heuristic pruning: a cheap ranking that decides *what* SimulationCraft measures.

This package is deliberately free of any DPS logic. It only ranks candidates by
their weighted secondary stats so the search can simulate a small top-K per slot
and let SimulationCraft (the sole source of numbers) confirm the finalists.
"""
