# AMD Windows runtime evidence

Evidence checked on 2026-10-01. This page records candidate support information and the remaining gates. It is not an install recipe or a claim of NAIA acceleration.

## Confirmed upstream statements

- AMD's ROCm release history lists ROCm Core SDK 10.0.0 as released on August 26, 2026: <https://rocm.docs.amd.com/en/latest/release/versions.html>.
- The official ComfyUI Windows guidance describes AMD GPU use with Windows 11, a current AMD graphics driver, and 64-bit Python 3.13. It lists RX 9070 and RX 9070 XT under `device-gfx1201` and provides example ROCm 10.0.0 PyTorch 2.13 package versions: <https://github.com/Comfy-Org/ComfyUI#amd-gpus-windows-rocm-100>.
- AMD's PyTorch install guide is dynamically generated from selected GPU, OS, and framework inputs. The supplied RX 9070 XT / `gfx1201` / Windows / PyTorch 2.12 selection is a specific guide view, not evidence for an RX 9070 or for Windows 11 26H2: <https://rocm.docs.amd.com/projects/ai-ecosystem/en/latest/frameworks/pytorch/install.html?fam=radeon&gfx=gfx1201&gpu=rx-9070-xt&i=pip&os=windows&pytorch-ver=2.12.0&w=compute>.
- The AMD compatibility matrix is the authority for hardware, OS, and driver support: <https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html>. The matrix endpoint returned HTTP 429 during this review, so its exact rows could not be independently checked here.

## What this does not establish

- The general ComfyUI guidance does not call out the Windows 11 26H2 build. No 26H2 eligibility may be inferred from the phrase “Windows 11”.
- An architecture mapping of `gfx1201` does not make the RX 9070 and RX 9070 XT interchangeable for OS, driver, framework, or runtime support. Preserve exact model names in the catalog.
- A PyTorch package install guide does not identify a complete, NAIA-compatible ComfyUI bundle or provide a trusted set of artifact hashes for this patcher.
- Neither source verifies NAIA's ANIMA workflow, NAIA's external-engine behavior, runtime selection, custom nodes, or model execution on AMD.
- No Boost/Assist Vulkan GPU selection or inference run has been observed in this environment.

## Release gates

Before installation can be enabled, add a maintained compatibility entry with exact product model/device identity, Windows build, AMD driver, ROCm/PyTorch versions, ComfyUI version, official artifact URLs, independently anchored manifest signature or digest, and verified artifact hashes. Author the NAIA change only against exact clean target files and record their baseline hashes. Keep the NVIDIA route intact and provide a distinct, reversible AMD selection.

Before calling the package an acceleration release, validate on the exact Radeon model and Windows build. Record HIP version, device enumeration, a tensor smoke operation, an ANIMA generation, GPU utilization and VRAM, and logs demonstrating that generation did not fall back to CPU. Static tests in the cloud are not hardware evidence.
