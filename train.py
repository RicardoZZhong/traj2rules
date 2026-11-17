"""按固定配置训练规则生成器适配器。基座权重不随这个包分发。"""

from __future__ import annotations

import json

from .config import TRAIN


def adapter_config() -> dict:
    return {
        "base_model": "Qwen3.5-9B",
        "task_type": "CAUSAL_LM",
        "r": TRAIN.lora_rank,
        "lora_alpha": TRAIN.lora_alpha,
        "lora_dropout": TRAIN.lora_dropout,
        "target_modules": [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        "quantization": "NF4",
        "quant_bits": TRAIN.quant_bits,
        "compute_dtype": TRAIN.compute_dtype,
        "learning_rate": TRAIN.learning_rate,
        "batch_size": TRAIN.batch_size,
        "max_epochs": TRAIN.max_epochs,
        "max_sequence_length": TRAIN.max_sequence_length,
        "max_rule_tokens": TRAIN.max_rule_tokens,
    }


def _read_examples(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        raise ValueError("监督样本为空")
    return rows


def train_adapter(dataset_path: str, output_dir: str) -> None:
    """用监督样本更新适配器。提示和证据位置不计入损失。"""
    try:
        import torch
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from torch.utils.data import Dataset
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            Trainer,
            TrainingArguments,
        )
    except ImportError as exc:
        raise SystemExit("训练适配器需要已安装 torch、transformers 和 peft。") from exc

    config = adapter_config()
    rows = _read_examples(dataset_path)
    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    tokenizer = AutoTokenizer.from_pretrained(config["base_model"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(config["base_model"], quantization_config=quant)
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(
        model,
        LoraConfig(
            r=config["r"],
            lora_alpha=config["lora_alpha"],
            lora_dropout=config["lora_dropout"],
            target_modules=config["target_modules"],
            bias="none",
            task_type="CAUSAL_LM",
        ),
    )

    class RuleDataset(Dataset):
        def __len__(self):
            return len(rows)

        def __getitem__(self, index):
            row = rows[index]
            prompt = row["prompt_text"] + "\n"
            text = prompt + row["target"]
            encoded = tokenizer(
                text,
                truncation=True,
                max_length=config["max_sequence_length"],
                padding="max_length",
            )
            prompt_length = len(tokenizer(prompt, add_special_tokens=False)["input_ids"])
            labels = list(encoded["input_ids"])
            for position in range(min(prompt_length, len(labels))):
                labels[position] = -100
            encoded["labels"] = labels
            return {key: torch.tensor(value) for key, value in encoded.items()}

    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=output_dir,
            learning_rate=config["learning_rate"],
            per_device_train_batch_size=1,
            gradient_accumulation_steps=config["batch_size"],
            num_train_epochs=config["max_epochs"],
            bf16=True,
            report_to=[],
        ),
        train_dataset=RuleDataset(),
    )
    trainer.train()
    model.save_pretrained(output_dir)
