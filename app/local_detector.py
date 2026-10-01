"""Self-hosted Desklib inference. Text never leaves this process for detection.

Model: desklib/ai-text-detector-v1.01 (MIT). See THIRD_PARTY_NOTICES.md.
English only; scores are uncalibrated model estimates, not proof of authorship.
"""
import math
import threading
from pathlib import Path

MODEL_ID = "desklib/ai-text-detector-v1.01"
MODEL_REVISION = "5fdea974cd4287c61674951ec78803aa274e2fb7"
MAX_TOKENS = 512
OVERLAP = 64
_lock = threading.Lock()
_engine = None


def available(directory):
    return all((Path(directory) / f).is_file() for f in ("model.safetensors", "config.json", "tokenizer.json"))


def windows(ids, width=MAX_TOKENS - 2, overlap=OVERLAP):
    """Cover every content token once in the weights; overlap provides context."""
    start = 0
    while start < len(ids):
        end = min(start + width, len(ids))
        yield ids[start:end], end - start - (overlap if start else 0)
        if end == len(ids):
            break
        start = end - overlap


def _load(directory):
    import torch
    from transformers import AutoConfig, AutoModel, AutoTokenizer, PreTrainedModel
    from safetensors.torch import load_file

    class DesklibModel(PreTrainedModel):
        config_class = AutoConfig

        def __init__(self, config):
            super().__init__(config)
            self.model = AutoModel.from_config(config)
            self.classifier = torch.nn.Linear(config.hidden_size, 1)
            self.post_init()

        def forward(self, input_ids, attention_mask):
            hidden = self.model(input_ids=input_ids, attention_mask=attention_mask)[0]
            # Pool in float32 to avoid compounding reduced-precision rounding.
            mask = attention_mask.unsqueeze(-1).float()
            pooled = (hidden.float() * mask).sum(1) / mask.sum(1).clamp(min=1)
            return self.classifier(pooled.to(hidden.dtype))

    torch.set_num_threads(1)
    tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True, trust_remote_code=False)
    # Preserve checkpoint dtypes without allocating a second complete model.
    # Float32 layers avoid slow BF16 software emulation on older host CPUs.
    config = AutoConfig.from_pretrained(directory, local_files_only=True, trust_remote_code=False)
    with torch.device("meta"):
        model = DesklibModel(config)
    model.load_state_dict(load_file(str(Path(directory) / "model.safetensors")), assign=True, strict=True)
    class FloatLinear(torch.nn.Linear):
        def forward(self, value):
            return torch.nn.functional.linear(value.float(), self.weight.float(), self.bias.float() if self.bias is not None else None)
    for module in model.modules():
        if isinstance(module, torch.nn.Linear):
            module.__class__ = FloatLinear
        elif isinstance(module, torch.nn.Embedding):
            module.register_forward_hook(lambda module, args, output: output.float())
    model.eval()
    return torch, tokenizer, model


def assess(text, directory, on_progress=None):
    global _engine
    with _lock:  # Bound CPU and memory even when called from concurrent threads.
        if _engine is None:
            _engine = _load(directory)
        torch, tokenizer, model = _engine
        ids = tokenizer.encode(text, add_special_tokens=False, truncation=False)
        if not ids or len(ids) > 40000:
            raise ValueError("Text is outside detector token limits")
        pieces = list(windows(ids))
        results = []
        for index, (part, weight) in enumerate(pieces):
            if on_progress:
                on_progress(index, len(pieces))
            tokens = tokenizer.build_inputs_with_special_tokens(part)
            input_ids = torch.tensor([tokens], dtype=torch.long)
            with torch.inference_mode():
                logits = model(input_ids, torch.ones_like(input_ids))
                value = torch.sigmoid(logits.float()).item()
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Invalid detector score")
            results.append({"section": index + 1, "ai_score": value, "weight": weight})
        value = sum(r["ai_score"] * r["weight"] for r in results) / sum(r["weight"] for r in results)
        return {
            "status": "assessed", "provider": "txtzi detector", "provider_id": "local",
            "ai_score": value, "score_label": "AI-likelihood score", "score_kind": "window_weighted_model_estimate",
            "model": MODEL_ID, "version": MODEL_REVISION, "precision": "bfloat16 matrix storage; float32 compute",
            "sections": results, "tokens_assessed": len(ids), "coverage": "full_document",
            "confidence": "Not calibrated", "language": "English",
            "notice": "Self-hosted Desklib model. Token-weighted mean across overlapping sections; not a percentage of AI-written words or a validated probability of authorship. Results can differ from other checkers. English beta.",
        }
