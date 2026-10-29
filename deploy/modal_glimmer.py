"""Serve Muse Glimmer 30B on Modal with vLLM, as an OpenAI-compatible endpoint.

Deploy:   modal deploy deploy/modal_glimmer.py
Endpoint: https://<your-workspace>--netproof-glimmer-serve.modal.run/v1
Stop:     modal app stop netproof-glimmer      (stop it when not evaluating; you pay per GPU second)

Needs a Modal secret named "netproof-glimmer" with:
  GLIMMER_API_KEY  any long random string; the same value goes in your local .env
  HF_TOKEN         a Hugging Face read token (the weights may require accepting a license)
"""
import os
import subprocess

import modal

MODEL = "meta-models/Muse-Glimmer-30B"
VLLM_VERSION = "0.28.0"  # version NVIDIA's model card reports testing Muse Glimmer with
MINUTES = 60

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(f"vllm=={VLLM_VERSION}", "huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)
hf_cache = modal.Volume.from_name("netproof-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("netproof-vllm-cache", create_if_missing=True)

app = modal.App("netproof-glimmer")


@app.function(
    image=image,
    gpu="H100",
    timeout=60 * MINUTES,
    scaledown_window=10 * MINUTES,
    volumes={"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache},
    secrets=[modal.Secret.from_name("netproof-glimmer")],
)
@modal.concurrent(max_inputs=8)
@modal.web_server(port=8000, startup_timeout=30 * MINUTES)
def serve():
    cmd = [
        "vllm", "serve", MODEL,
        "--served-model-name", "muse-glimmer",
        "--host", "0.0.0.0", "--port", "8000",
        "--api-key", os.environ["GLIMMER_API_KEY"],
        "--max-model-len", "65536",
        "--quantization", "fp8",
        "--enable-auto-tool-choice", "--tool-call-parser", "muse_glimmer",
        "--reasoning-parser", "muse_glimmer",
        "--generation-config", "auto",
    ]
    subprocess.Popen(cmd)
