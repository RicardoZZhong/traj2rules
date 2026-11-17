"""生成样本和修订样本。损失只落在规则输出上，不覆盖提示和证据。"""

from __future__ import annotations

import json
import random

from .config import INSUFFICIENT_EVIDENCE, TRAIN
from .evidence import ScoredRule
from .library import select_library


def render_prompt(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def generation_example(domain: str, effect: tuple, fragments: dict, target: str) -> dict:
    prompt = {
        "task": "generate",
        "domain": domain,
        "effect": effect,
        "positive": fragments.get("positive", []),
        "counterexample": fragments.get("counterexample", []),
        "unknown": fragments.get("unknown", []),
    }
    return {
        "kind": "generation",
        "prompt": prompt,
        "prompt_text": render_prompt(prompt),
        "target": target,
    }


def revision_example(domain: str, effect: tuple, rule_text: str, counterexamples, target: str) -> dict:
    prompt = {
        "task": "revise",
        "domain": domain,
        "effect": effect,
        "rule": rule_text,
        "counterexample": list(counterexamples),
    }
    return {
        "kind": "revision",
        "prompt": prompt,
        "prompt_text": render_prompt(prompt),
        "target": target,
    }


def loss_span(example: dict) -> tuple[int, int]:
    """训练文本是提示、换行、目标。损失从目标的第一个字符开始。"""
    start = len(example["prompt_text"]) + 1
    return start, start + len(example["target"])


def training_text(example: dict) -> str:
    return example["prompt_text"] + "\n" + example["target"]


def choose_target(scored: list[ScoredRule], n_min: int = 3) -> str:
    chosen, _decisions = select_library(scored, n_min=n_min, capacity=1)
    if not chosen:
        return INSUFFICIENT_EVIDENCE
    return chosen[0].canon


def mix_examples(generation, revision, count: int, ratio: float = TRAIN.generation_ratio, seed: int = 17):
    if not generation and not revision:
        return []
    rng = random.Random(seed)
    mixed = []
    for _ in range(count):
        use_generation = rng.random() < ratio
        pool = generation if use_generation and generation else revision
        if use_generation and not generation:
            pool = revision
        if not use_generation and not revision:
            pool = generation
        mixed.append(rng.choice(pool))
    return mixed
