# SPDX-License-Identifier: GPL-3.0-only
# This patch transformer adapts the ANIMA integration points in NAIA Portable 2.0.48.
# Upstream: https://github.com/DNT-LAB/NAIA2.0/tree/6e97c7f4f37e495ad21657ed29d28dd9993a808e
# The upstream v2.0.48 source is GPL-3.0; see config/THIRD_PARTY_LICENSES/GPL-3.0.txt.
# Modified here to construct fail-closed AMD candidate transforms from locally supplied files.

from __future__ import annotations
import ast
import hashlib

class TransformError(ValueError):
    """Refuse unknown or modified source inputs before returning payload bytes."""

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)

def transform_sources(source_files: dict[str, bytes], baseline_hashes: dict[str, str]) -> dict[str, bytes]:
    """Transform supplied app modules after all baseline hashes pass; performs no I/O."""
    originals = {}
    if set(source_files) != set(baseline_hashes):
        raise RuntimeError("baseline target set mismatch")
    for name, expected in baseline_hashes.items():
        data = source_files[name]
        if digest(data) != expected:
            raise TransformError(f"baseline mismatch: {name}")
        originals[name] = data

    manifest = originals["manifest.py"].decode("utf-8")
    manifest += '''\n\n# Private preparation only. This profile is deliberately unavailable until trusted\n# artifacts and an exact Windows/GPU/driver support row are reviewed.\nAMD_PROFILE_ID = "amd-rocm10.0-gfx1201-windows11-25h2-cp313"\nAMD_RUNTIME_ID = "r1-comfyui-0.22.0-amd-rocm10.0-py313"\nAMD_PROFILES = {\n    AMD_PROFILE_ID: {\n        "enabled": False,\n        "trust_status": "untrusted",\n        "artifact_manifest_sha256": None,\n        "runtime_id": AMD_RUNTIME_ID,\n        "python_version": "3.13",\n        "rocm_version": "10.0.0",\n        "windows_builds": (),\n        "pnp_ids": (),\n        "driver_versions": (),\n        "hip_architectures": ("gfx1201",),\n        "candidate_os_release": "Windows 11 25H2",\n        "observed_candidate_gpu_names": ("RX 9070", "RX 9070 XT"),\n        "cuda_only_options": (),\n        "cuda_only_kernels": (),\n    },\n}\n'''

    manifest = replace_once(manifest,
        '        "rocm_version": "10.0.0",\n        "windows_builds": (),',
        '        "torch_version": "2.13.0+rocm10.0.0",\n        "rocm_version": "10.0.0",\n        "hip_runtime_version": "7.15.26333",\n        "windows_builds": (),',
        "pin ROCm package version separately from HIP runtime version")

    install = originals["install.py"].decode("utf-8")
    install = replace_once(install,
        '    source: str = "nvidia-smi"\n',
        '    source: str = "nvidia-smi"\n    backend: str = "nvidia"\n    device_index: int | None = None\n    hip_version: str = ""\n',
        "GpuInfo backend metadata")
    anchor = '\ndef validate_gpu(gpu):\n'
    helper = '''\ndef _resolve_backend_profile(profile_id="nvidia"):\n    """Resolve only checked-in source policy; caller supplied profile data is ignored."""\n    if profile_id == "nvidia":\n        return None\n    profile = manifest.AMD_PROFILES.get(profile_id)\n    if profile is None:\n        raise ManagedEngineError("AMD_PROFILE_UNKNOWN", "AMD profile is not recognized.")\n    if profile.get("enabled") is not True or profile.get("trust_status") != "reviewed":\n        raise ManagedEngineError("AMD_PROFILE_UNTRUSTED", "AMD profile is disabled or lacks trusted review.")\n    digest = profile.get("artifact_manifest_sha256")\n    if not isinstance(digest, str) or not re.fullmatch(r"[0-9A-Fa-f]{64}", digest):\n        raise ManagedEngineError("AMD_ARTIFACT_UNTRUSTED", "AMD artifact manifest has no trusted digest.")\n    return profile\n\n\ndef _amd_hip_inventory(run=None):\n    """Read HIP/target information only for a separately selected, trusted AMD profile."""\n    run = run or subprocess.run\n    try:\n        result = run(["rocminfo"], capture_output=True, text=True, encoding="utf-8",\n                     errors="replace", timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))\n    except (OSError, subprocess.TimeoutExpired):\n        return {"hip_version": "", "architectures": (), "device_indices": ()}\n    output = result.stdout or ""\n    version = re.search(r"HIP version\\s*[:=]\\s*([0-9]+(?:\\.[0-9]+)+)", output, re.IGNORECASE)\n    architectures = tuple(sorted(set(re.findall(r"\\b(gfx[0-9a-f]{3,})\\b", output, re.IGNORECASE))))\n    # rocminfo agent ordinals are not HIP runtime indices; never infer device_index from them.\n    return {"hip_version": version.group(1) if version else "",\n            "architectures": architectures, "device_indices": ()}\n\n'''
    hip_start = helper.index("\ndef _amd_hip_inventory")
    hip_end = helper.index("\n\n", helper.index('"device_indices": ()}', hip_start))
    helper = helper[:hip_start] + helper[hip_end:]
    install = replace_once(install, anchor, helper + anchor, "AMD eligibility helpers")
    install = replace_once(install,
        'def __init__(self, *, save_root: Path, settings: AnimaSettings, opener=None, run_7z=None, gpu_probe=None,\n                 disk_free=None, runtime_factory=None, on_ready=None, clock=time.time, forbidden_roots=(),\n                 system_directory=None):\n',
        'def __init__(self, *, save_root: Path, settings: AnimaSettings, opener=None, run_7z=None, gpu_probe=None,\n                 disk_free=None, runtime_factory=None, on_ready=None, clock=time.time, forbidden_roots=(),\n                 system_directory=None, backend_profile="nvidia"):\n',
        "install job explicit selector")
    install = replace_once(install,
        '        self.save_root, self.settings = Path(save_root), settings\n',
        '        self.save_root, self.settings = Path(save_root), settings\n        self.backend_profile = backend_profile\n',
        "store explicit selector")
    install = replace_once(install,
        '    def inspect(self, engine_root=None, model_dirs=None):\n',
        '    def inspect(self, engine_root=None, model_dirs=None):\n        if self.backend_profile != "nvidia":\n            profile = _resolve_backend_profile(self.backend_profile)\n            if not profile.get("windows_builds") or not profile.get("pnp_ids") or not profile.get("driver_versions"):\n                raise ManagedEngineError("AMD_PROFILE_UNSUPPORTED", "No exact Windows/GPU/driver eligibility row is reviewed.")\n            raise ManagedEngineError("AMD_ARTIFACT_UNTRUSTED", "No trusted AMD runtime artifact set is available.")\n',
        "fail closed selected AMD inspect branch")

    runtime = originals["runtime.py"].decode("utf-8")
    runtime = replace_once(runtime, 'from pathlib import Path\n', 'from pathlib import Path\nimport json\n', "runtime-local ROCm preflight JSON")
    runtime = replace_once(runtime,
        '    def __init__(self, engine_root: Path, *, runtime_id: str, reserve_vram_gb: float, idle_minutes: int,\n                 model_config=None, command_builder=None, popen=subprocess.Popen, clock=time.monotonic):\n',
        '    def __init__(self, engine_root: Path, *, runtime_id: str, reserve_vram_gb: float, idle_minutes: int,\n                 model_config=None, command_builder=None, popen=subprocess.Popen, clock=time.monotonic,\n                 backend_profile="nvidia", hip_device_index=None):\n',
        "runtime explicit selector")
    runtime = replace_once(runtime,
        '        self.engine_root, self.runtime_id = Path(engine_root).resolve(), runtime_id\n',
        '        self.engine_root, self.runtime_id = Path(engine_root).resolve(), runtime_id\n        self.backend_profile, self.hip_device_index = backend_profile, hip_device_index\n        if backend_profile != "nvidia":\n            profile = manifest.AMD_PROFILES.get(backend_profile)\n            if (profile is None or profile.get("enabled") is not True or\n                    profile.get("trust_status") != "reviewed" or runtime_id != profile.get("runtime_id")):\n                raise ManagedEngineError("AMD_PROFILE_UNTRUSTED", "AMD runtime selection is disabled or untrusted.")\n            if not isinstance(hip_device_index, int) or hip_device_index < 0:\n                raise ManagedEngineError("AMD_DEVICE_INDEX_INVALID", "A HIP runtime device index is required.")\n',
        "runtime profile validation")
    amd_methods = '''
    def _amd_runtime_preflight(self):
        """Probe HIP through the exact managed ComfyUI interpreter, never PATH tools."""
        profile = manifest.AMD_PROFILES.get(self.backend_profile)
        if profile is None or self.backend_profile == "nvidia":
            raise ManagedEngineError("AMD_PROFILE_UNKNOWN", "AMD runtime profile is unavailable.")
        if not isinstance(self.hip_device_index, int) or self.hip_device_index < 0:
            raise ManagedEngineError("AMD_DEVICE_INDEX_INVALID", "An exact HIP device selection is required.")
        root = self.engine_root / "runtime" / self.runtime_id / "ComfyUI_windows_portable"
        python = root / "python_embeded" / "python.exe"
        if not python.is_file():
            raise ManagedEngineError("AMD_RUNTIME_PYTHON_MISSING", "The managed runtime Python executable is missing.")
        code = ("import json,torch; d=torch.cuda.current_device(); p=torch.cuda.get_device_properties(d); "
                "print(json.dumps({'torch':torch.__version__,'hip':torch.version.hip,"
                "'rocm':getattr(torch.version,'rocm',None),'available':torch.cuda.is_available(),"
                "'count':torch.cuda.device_count(),'index':d,'name':torch.cuda.get_device_name(d),"
                "'gfx':getattr(p,'gcnArchName',None),'total_memory':p.total_memory},sort_keys=True))")
        try:
            result = subprocess.run([str(python), "-B", "-c", code], cwd=str(root),
                                    env=self._engine_environment(), capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=30, check=False,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode != 0:
                raise ValueError("probe exited nonzero")
            probe = json.loads((result.stdout or "").strip().splitlines()[-1])
        except (OSError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError, IndexError) as exc:
            raise ManagedEngineError("AMD_RUNTIME_PREFLIGHT_FAILED", "Managed HIP runtime preflight failed.",
                                     str(exc)) from exc
        return probe

    def _amd_system_stats_uses_gpu(self, stats, probe, profile):
        """Require ROCm identity from torch.version.hip plus the active /system_stats device."""
        try:
            expected_rocm = str(profile["rocm_version"]).casefold()
            expected_hip = str(profile["hip_runtime_version"]).casefold()
            expected_torch = str(profile["torch_version"]).casefold()
            expected_arches = tuple(x.casefold() for x in profile["hip_architectures"])
            probe_torch = str(probe.get("torch") or "").casefold()
            hip_version = str(probe.get("hip") or "").casefold()
            rocm_version = str(probe.get("rocm") or "").casefold()
            arch = str(probe.get("gfx") or "").split(":", 1)[0].casefold()
            devices = stats.get("devices", [])
            device = next(x for x in devices if int(x.get("index", -1)) == 0)
            system_version = str(stats.get("system", {}).get("pytorch_version") or "").casefold()
            return (probe_torch == expected_torch and system_version == expected_torch
                    and hip_version == expected_hip and rocm_version == expected_rocm
                    and probe.get("available") is True
                    and int(probe.get("count", 0)) == 1 and int(probe.get("index", -1)) == 0
                    and arch in expected_arches and int(probe.get("total_memory", 0)) > 0
                    and str(device.get("type", "")).casefold() == "cuda"
                    and int(device.get("vram_total", 0)) > 0)
        except (AttributeError, KeyError, TypeError, ValueError, StopIteration):
            return False

'''
    runtime = replace_once(runtime,
        '    def _command(self, port):\n',
        amd_methods + '    def _command(self, port):\n',
        "absolute runtime-local ROCm probe and CUDA-API health gate")
    # Keep _command's original NVIDIA body verbatim. AMD gets a Python 3.13 isolated root,
    # no unverified CUDA-only fast flags, and no NVIDIA UUID environment variables.
    runtime = replace_once(runtime,
        '    def _command(self, port):\n',
        '    def _command(self, port):\n        if self.backend_profile != "nvidia":\n            argv, root, env = self._amd_command(port)\n            argv.insert(3, "--disable-dynamic-vram")\n            return argv, root, env\n',
        "NVIDIA command default branch")
    runtime = replace_once(runtime,
        '    def _engine_environment(self):\n',
        '''    def _amd_command(self, port):\n        if self.model_config_path is None:\n            raise ManagedEngineError("ENGINE_START_FAILED", detail="model paths not prepared")\n        profile = manifest.AMD_PROFILES.get(self.backend_profile)\n        if (profile is None or profile.get("enabled") is not True or\n                profile.get("trust_status") != "reviewed" or self.runtime_id != profile.get("runtime_id")):\n            raise ManagedEngineError("AMD_PROFILE_UNTRUSTED", "AMD runtime selection is disabled or untrusted.")\n        if profile.get("python_version") != "3.13" or not isinstance(self.hip_device_index, int) or self.hip_device_index < 0:\n            raise ManagedEngineError("AMD_PROFILE_UNSUPPORTED", "AMD Python 3.13 runtime/device selection is incomplete.")\n        rt = self.engine_root / "runtime" / self.runtime_id / "ComfyUI_windows_portable"\n        state = self.engine_root / "state"\n        argv = [str(rt / "python_embeded/python.exe"), "-s", str(rt / "ComfyUI/main.py"),\n                "--listen", "127.0.0.1", "--port", str(port), "--disable-auto-launch",\n                "--extra-model-paths-config", str(self.model_config_path),\n                "--output-directory", str(state / "comfy_output"), "--temp-directory", str(state / "comfy_temp"),\n                "--user-directory", str(state / "comfy_user"), "--reserve-vram", str(self.reserve_vram_gb)]\n        env = clean_environment()\n        env.pop("CUDA_VISIBLE_DEVICES", None)\n        env.pop("CUDA_DEVICE_ORDER", None)\n        env["HIP_VISIBLE_DEVICES"] = str(self.hip_device_index)\n        env["ROCR_VISIBLE_DEVICES"] = str(self.hip_device_index)\n        return argv, rt, env\n\n    def _engine_environment(self):\n''',
        "isolated AMD command and env")
    runtime = replace_once(runtime,
        '                    if not any(x.get("type") == "cuda" for x in stats.get("devices", [])):\n',
        '                    if self.backend_profile == "nvidia":\n                        gpu_active = any(x.get("type") == "cuda" for x in stats.get("devices", []))\n                    else:\n                        profile = manifest.AMD_PROFILES.get(self.backend_profile)\n                        probe = self._amd_runtime_preflight()\n                        gpu_active = self._amd_system_stats_uses_gpu(stats, probe, profile)\n                    if not gpu_active:\n',
        "backend-aware device health")
    # Keep CUDA UUID pinning unchanged and make AMD path independent of CUDA env.
    runtime = replace_once(runtime,
        '    def _engine_environment(self):\n        env = clean_environment()\n',
        '    def _engine_environment(self):\n        if self.backend_profile != "nvidia":\n            if not isinstance(self.hip_device_index, int) or self.hip_device_index < 0:\n                raise ManagedEngineError("AMD_DEVICE_INDEX_INVALID", "A HIP runtime device index is required.")\n            env = clean_environment()\n            env.pop("CUDA_VISIBLE_DEVICES", None)\n            env.pop("CUDA_DEVICE_ORDER", None)\n            env["HIP_VISIBLE_DEVICES"] = str(self.hip_device_index)\n            env["ROCR_VISIBLE_DEVICES"] = str(self.hip_device_index)\n            return env\n        env = clean_environment()\n',
        "backend-aware environment")

    outputs = {"manifest.py": manifest.encode("utf-8"), "install.py": install.encode("utf-8"), "runtime.py": runtime.encode("utf-8")}
    for name, data in outputs.items():
        ast.parse(data.decode("utf-8"), filename=name)
    return outputs






