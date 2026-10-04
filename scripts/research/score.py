"""Shardable full-text inference against two fixed checkpoints; no paid APIs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research.recovery import RUN, DESK_REV, VANG_REV, read, save, sha, now, validate_score


def download(which):
    from huggingface_hub import snapshot_download
    if which == "desklib":
        from scripts.prepare_detector import prepare
        prepare(RUN / "models/desklib")
    else:
        snapshot_download("ShantanuT01/vanguard-ai-text-detector", revision=VANG_REV,
            local_dir=RUN / "models/vanguard", allow_patterns=["*.json", "*.model", "*.safetensors"], max_workers=2)
    print(which, "pinned model downloaded", flush=True)


def worker(which, shard, count, seconds, phase="A", reference_only=False, drain=False):
    model = tokenizer = torch = None
    started = time.monotonic()
    directory = RUN / "models" / which
    revision = DESK_REV if which == "desklib" else VANG_REV
    while time.monotonic() - started < seconds and not (RUN / "stop-scoring").exists():
        pending = False
        job_directory = RUN / "jobs" if phase == "A" else RUN / ("phase-b/jobs" if phase == "B" else "phase-c/jobs")
        original = RUN / "source-original.json"
        paths = [original] if reference_only else [RUN / "baseline.json", *([original] if original.exists() else []), *job_directory.glob("*.json")]
        jobs = [read(path) for path in paths]
        # Admission order only; inference, exact text and coverage are unchanged.
        # New-bank singles allow adaptive selection while older combinations drain.
        jobs.sort(key=lambda j: (len(j.get("patch_ids", [])) != 1, -j.get("round", 0), j["id"]))
        for j in jobs:
            if (RUN / "stop-scoring").exists():
                return
            digest = j["sha256"]
            if sha(j["text"]) != digest:
                raise ValueError("Text hash differs from job identity")
            if int(digest, 16) % count != shard:
                continue
            out = RUN / "scores" / which / (digest + ".json")
            if out.exists():
                existing = read(out)
                validate_score(existing, digest, which, revision)
                continue
            pending = True
            if which == "desklib":
                from app.local_detector import assess
                measurement = assess(j["text"], directory)
            else:
                if model is None:
                    import torch as torch_module
                    from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer
                    torch = torch_module
                    torch.set_num_threads(2)
                    tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True, trust_remote_code=False)
                    config = AutoConfig.from_pretrained(directory, local_files_only=True, trust_remote_code=False)
                    config.reference_compile = False
                    model = AutoModelForSequenceClassification.from_pretrained(directory, config=config,
                        local_files_only=True, trust_remote_code=False, attn_implementation="sdpa", torch_dtype=torch.float32)
                    model.eval()
                inputs = tokenizer(j["text"], return_tensors="pt", truncation=False)
                length = inputs["input_ids"].shape[1]
                if length > 8192:
                    raise ValueError("Vanguard full text exceeds context; truncation prohibited")
                with torch.inference_mode():
                    logits = model(**inputs).logits.float()
                    if logits.numel() != 1:
                        raise ValueError("Unexpected Vanguard output shape")
                    value = torch.sigmoid(logits).item()
                measurement = {"ai_score": value, "model": "ShantanuT01/vanguard-ai-text-detector",
                    "revision": VANG_REV, "tokens_assessed": length, "coverage": "full_document",
                    "dtype": "float32", "reference_compile": False, "attention": "sdpa"}
            record = {"sha256": digest, "revision": revision, "measured_at": now(), "measurement": measurement}
            validate_score(record, digest, which, revision)
            save(out, record)
            print(which, j["id"], round(measurement["ai_score"], 7), flush=True)
        if reference_only or drain:
            return
        if not pending:
            time.sleep(2)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["download", "worker", "reference", "drain"])
    p.add_argument("detector", choices=["desklib", "vanguard"])
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--seconds", type=int, default=7200)
    p.add_argument("--phase", choices=["A", "B", "C"], default="A")
    a = p.parse_args()
    if a.action == "download": download(a.detector)
    else: worker(a.detector, a.shard, a.count, a.seconds, a.phase, a.action == "reference", a.action == "drain")
