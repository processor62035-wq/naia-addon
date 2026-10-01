# NAIA AMD Runtime Add-on

This public repository prepares an optional AMD path for NAIA Portable. The work is ordered by the requested priorities:

1. ANIMA image generation, whose managed runtime currently pins ComfyUI's Windows NVIDIA portable bundle.
2. Boost/Assist LLM, whose current `llama.cpp` path uses Vulkan and is already separate from the NVIDIA-only ANIMA runtime.

## Current integration boundary

The app is at NAIA Portable 2.0.48. Its managed ANIMA runtime is identified as `r1-comfyui-0.22.0-nvidia`, uses the ComfyUI Windows NVIDIA package, and applies NVIDIA-specific GPU probing and CUDA device selection. NAIA Extension API v1 can register extension UI and generation hooks, but does not expose a public method to replace the managed runtime or select its GPU backend. A plain add-on cannot safely swap the ANIMA runtime today.

The first implementation decision is therefore whether NAIA gains a supported runtime-selection hook or this project supplies a separately applied, reversible patch for a copy of the host app. The NVIDIA path must remain available. This repository currently contains development preparation and the compatibility design only; it does not claim to enable AMD acceleration yet.

The requested Windows installer flow is captured in [docs/installer-design.md](docs/installer-design.md). The installer and patch are not implemented in this scaffold commit.

As checked on 2026-10-01, the official ComfyUI Windows guide describes a ROCm 10.0 path using Windows 11, a current AMD graphics driver, 64-bit Python 3.13, and `device-gfx1201` for both RX 9070 and RX 9070 XT. This identifies a candidate upstream stack, not a tested NAIA runtime package. The guide does not identify Windows 11 26H2 separately, and it does not supply the signed, hash-pinned artifact set or exact NAIA integration patch needed by this repository. The installer must therefore refuse to offer that combination until those checks are complete. See [AMD/ComfyUI evidence and release gates](docs/amd-evidence.md).

The Codex cloud environment is for CPU-only static and mocked checks; it cannot prove GPU acceleration.

## Cloud development

Use Linux, Python 3.12, Git, and Bash. The devcontainer is a convenience for reproducible development; Codex cloud environment setup may be managed separately by the repository owner.

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```

The host app, ComfyUI, ROCm, models, GPU drivers, and NovelAI credentials are not needed for these scaffold checks. Do not copy the portable app or its `user-data` into this repository.

## References

- NAIA upstream: <https://github.com/DNT-LAB/NAIA2.0>
- NAIA Extension API reference format: <https://github.com/okawaritsuika/NAIA-EXten> (used as an interface reference; its local installed source and state are not copied here)
- ComfyUI Windows ROCm 10 guidance: <https://github.com/Comfy-Org/ComfyUI#amd-gpus-windows-rocm-100>
- AMD ROCm compatibility matrix: <https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html>
- AMD PyTorch Windows install guidance: <https://rocm.docs.amd.com/projects/ai-ecosystem/en/latest/frameworks/pytorch/install.html>

No repository license has been selected yet. No license is granted by this preparation commit.

