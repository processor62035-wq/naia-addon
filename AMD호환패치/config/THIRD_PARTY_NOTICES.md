# Third-party notices

The source transformer in scripts/amd_transform.py is derived for the ANIMA integration points in **NAIA Portable 2.0.48**. The inspected upstream tag v2.0.48 resolves to commit 6e97c7f4f37e495ad21657ed29d28dd9993a808e in DNT-LAB/NAIA2.0: https://github.com/DNT-LAB/NAIA2.0/tree/6e97c7f4f37e495ad21657ed29d28dd9993a808e. The target source LICENSE at that commit is GNU GPL version 3; its full text is retained in THIRD_PARTY_LICENSES/GPL-3.0.txt.

amd_transform.py is marked GPL-3.0-only and adds a disabled AMD candidate transform. It consumes only the user's local target files after exact baseline hash checks. No complete NAIA source module, model, application binary, or third-party runtime is included.

This notice does not license NAIA components beyond the terms granted by their upstream authors, nor does it grant a license to ROCm, PyTorch, ComfyUI, models, or other third-party materials. Those artifacts are not bundled.
