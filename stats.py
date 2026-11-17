"""成功率、Holm 校正、符号检验和任务组 bootstrap。"""

from __future__ import annotations

import random
from math import comb


def success_rate(outcomes) -> float:
    """outcomes[task] 是各次运行的 0/1 结果。先对运行取均值，再对任务取均值。"""
    if not outcomes:
        return 0.0
    return sum(sum(runs) / len(runs) for runs in outcomes) / len(outcomes)


def paired_mean_difference(left, right) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("两组任务结果必须非空且等长")
    return sum(a - b for a, b in zip(left, right)) / len(left)


def holm(p_values: list[float]) -> list[float]:
    count = len(p_values)
    order = sorted(range(count), key=lambda index: (p_values[index], index))
    adjusted = [0.0] * count
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (count - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def two_sided_sign_test(n_positive: int, n_negative: int) -> float:
    """只统计结果发生变化的组。p = 0.5 的双侧精确二项检验。"""
    total = n_positive + n_negative
    if total == 0 or n_positive == n_negative:
        return 1.0
    smaller = min(n_positive, n_negative)
    tail = sum(comb(total, index) for index in range(smaller + 1))
    return min(1.0, 2.0 * tail / (2**total))


def bootstrap_difference_ci(left, right, iterations: int = 10000, seed: int = 0, alpha: float = 0.05):
    if len(left) != len(right) or not left:
        raise ValueError("两组任务结果必须非空且等长")
    rng = random.Random(seed)
    count = len(left)
    estimates = []
    for _ in range(iterations):
        indexes = [rng.randrange(count) for _ in range(count)]
        estimates.append(sum(left[index] - right[index] for index in indexes) / count)
    estimates.sort()
    low_index = int((alpha / 2) * iterations)
    high_index = min(iterations - 1, int((1 - alpha / 2) * iterations))
    return estimates[low_index], estimates[high_index]
