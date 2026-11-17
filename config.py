"""主配置：搜索预算、训练超参和三个领域的数据规模。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchConfig:
    max_conditions: int = 3
    max_program_length: int = 2
    min_conditions: int = 1
    initial_candidates: int = 8
    revision_rounds: int = 2
    outputs_per_round: int = 8
    max_outputs_per_group: int = 24
    n_min: int = 3
    library_capacity: int = 64
    proposal_cap: int = 3


@dataclass(frozen=True)
class TrainConfig:
    lora_rank: int = 32
    lora_alpha: int = 64
    lora_dropout: float = 0.05
    learning_rate: float = 1e-4
    batch_size: int = 64
    max_epochs: int = 3
    max_sequence_length: int = 4096
    max_rule_tokens: int = 768
    generation_ratio: float = 0.7
    revision_ratio: float = 0.3
    trajectory_ratio_9b: float = 0.75
    trajectory_ratio_27b: float = 0.25
    online_input_tokens: int = 8192
    online_output_tokens: int = 512
    quant_bits: int = 4
    compute_dtype: str = "bf16"


@dataclass(frozen=True)
class DomainSpec:
    name: str
    training_groups: int
    library_groups: int
    development_groups: int
    calibration_groups: int
    probe_groups: int
    supervised_examples: int
    test_tasks: int
    step_limit: int
    rule_budget: int
    success_criterion: str

    def partition_counts(self) -> dict[str, int]:
        return {
            "training": self.training_groups,
            "library": self.library_groups,
            "development": self.development_groups,
            "calibration": self.calibration_groups,
            "probe": self.probe_groups,
        }


SEARCH = SearchConfig()
TRAIN = TrainConfig()

# 训练种子与执行种子成对使用：17/101、43/103、89/107。
TRAIN_SEEDS = (17, 43, 89)
EXEC_SEEDS = (101, 103, 107)

# 监督样本数。三个领域合计 11972，其中生成 8374、修订 3598。
GENERATION_EXAMPLES = 8374
REVISION_EXAMPLES = 3598
SUPERVISED_EXAMPLES = 11972

DOMAIN_SPECS = {
    "alfworld": DomainSpec(
        "alfworld", 800, 118, 100, 100, 112, 3814, 134, 40, 12, "official_completion"
    ),
    "scienceworld": DomainSpec(
        "scienceworld", 600, 147, 80, 80, 96, 3076, 90, 100, 20, "score_100"
    ),
    "webshop": DomainSpec(
        "webshop", 1200, 196, 150, 150, 128, 5082, 500, 40, 12, "reward_1"
    ),
}

INSUFFICIENT_EVIDENCE = "insufficient evidence"
PARTITION_ORDER = (
    "training",
    "library",
    "development",
    "calibration",
    "probe",
)
