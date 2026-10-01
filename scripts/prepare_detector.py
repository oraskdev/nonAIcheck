"""Download a pinned, MIT-licensed model and prepare CPU weights at image build."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import torch
from huggingface_hub import snapshot_download
from safetensors import safe_open
from safetensors.torch import save_file

MODEL = "desklib/ai-text-detector-v1.01"
REVISION = "5fdea974cd4287c61674951ec78803aa274e2fb7"


def prepare(destination):
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="txtzi-model-") as temporary:
        source = Path(snapshot_download(MODEL, revision=REVISION, local_dir=temporary,
                                       allow_patterns=["*.json", "*.model", "model.safetensors"], max_workers=2))
        tensors = {}
        with safe_open(source / "model.safetensors", framework="pt", device="cpu") as weights:
            for name in weights.keys():
                value = weights.get_tensor(name)
                tensors[name] = value.to(torch.bfloat16) if value.is_floating_point() else value
        save_file(tensors, str(destination / "model.safetensors"), metadata={"format": "pt"})
        for file in source.iterdir():
            if file.suffix in (".json", ".model"):
                shutil.copyfile(file, destination / file.name)
        config = json.loads((destination / "config.json").read_text())
        config["torch_dtype"] = "bfloat16"
        (destination / "config.json").write_text(json.dumps(config))
        (destination / "provenance.json").write_text(json.dumps({"model": MODEL, "revision": REVISION, "license": "MIT", "precision": "bfloat16"}))
    print("Pinned txtzi detector prepared", flush=True)


if __name__ == "__main__":
    prepare(Path(sys.argv[1]))
