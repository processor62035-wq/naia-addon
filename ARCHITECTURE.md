# Runtime support design

## Findings

- Host: NAIA Portable Electron shell 2.0.48; embedded host Python is 3.12.
- Add-on contract: `extension.json` with `naia_ext_api: 1`, a `main.py` entry, and `register(ctx)`.
- Extension API v1 provides UI panels, subscriptions, hooks, generation queue operations, extension-scoped settings, logging, and notifications. It does not expose a supported setter for the managed engine manifest, process builder, GPU probe, or ComfyUI endpoint.
- Managed ANIMA runtime: `core/anima_engine/manifest.py` pins `r1-comfyui-0.22.0-nvidia` and a Windows NVIDIA ComfyUI archive. `install.py` probes NVML/`nvidia-smi`, validates NVIDIA-specific requirements, and records the selected GPU. `runtime.py` launches the embedded Python/ComfyUI entry and sets CUDA device visibility.
- Boost/Assist LLM: uses a separate `llama.cpp` Vulkan runtime with CPU fallback. It should remain a second, independent workstream.
- The app selects an external engine through its own backend setting. Selecting external by itself is not proof that the ANIMA-specific managed path works with an AMD engine.
- The installed extension under `user-data/extensions/naia_exten` demonstrates the v1 shape, but its source has no confirmed redistribution license. It is not copied or patched by this project.

## Options for ANIMA (priority 1)

### A. Supported host runtime selector

Preferred if the NAIA upstream exposes one. Add an optional ROCm 10 runtime manifest beside the existing NVIDIA manifest, then select either backend through a documented host API. Keep NVIDIA as the existing default and make switching explicit. Installation must pin the package URL, version, and checksum; validate OS/GPU support; and keep AMD Python/PyTorch dependencies isolated from NAIA's own Python and the NVIDIA environment.

### B. Reversible patch for a separate app copy

If Extension API v1 cannot select a managed backend, prepare a separately invoked patcher against an exact NAIA version. It must inspect version and checksums, back up every modified file, apply only to a user-selected copy, report each change, and support restore. It must not patch a running/original installation or silently fetch an unreviewed third-party patch. The original NVIDIA files and runtime selection remain available.

In either option, AMD detection and launch must not assume CUDA/NVML or reuse NVIDIA-only extensions. PyTorch's HIP compatibility layer can retain some `torch.cuda` calls, but CUDA-only custom kernels and wheels require separate validation. A safe baseline is a standard ROCm-supported ComfyUI/PyTorch path without optional CUDA extensions. Keep the host's Python 3.12 separate from the AMD ComfyUI's Python 3.13 runtime. The future AMD profile needs its own ID, install folder, receipt, and runtime command. Preflight should report `torch.version.hip` and run a small tensor smoke check; the mere presence of `torch.cuda` or a `cuda` device string is not sufficient to classify the backend.

## External ComfyUI boundary

NAIA can select an external ComfyUI engine, but that alone is not equivalent to replacing its managed ANIMA backend. ANIMA-specific formatting and managed lifecycle are coupled to the selected managed engine. An external-server health check or generic ComfyUI connection is a useful add-on capability, but it must not be described as AMD ANIMA support until an end-to-end ANIMA workflow is verified.

## Boost/Assist LLM (priority 2)

The existing Vulkan engine is already the separate cross-vendor path. First verify that NAIA's packaged `llama.cpp` build lists the target Radeon device and falls back to CPU correctly. ROCm may be explored as an optional backend later, but it must not replace or regress Vulkan/NVIDIA behavior.

## Validation gates

1. CPU/static: manifest and installer-plan checks, Python syntax, mocked GPU probes, runtime selection persistence, dry-run/staging, backup/restore, and NVIDIA default/regression tests.
2. Host integration: exact NAIA version in a disposable copy, isolated user-data, local/mock ComfyUI endpoint, no API credentials.
3. Hardware: exact AMD GPU, Windows version, and driver from the supported matrix; confirm HIP runtime, device enumeration, ANIMA smoke generation, memory use, and CPU fallback on failure.

Cloud checks cover only gate 1. No GPU success claim is valid before gate 3.

