import hashlib, importlib.util, json, os, tempfile, unittest, sys, io
from pathlib import Path
from unittest import mock
from contextlib import redirect_stdout

SPEC=importlib.util.spec_from_file_location("naia_patch",Path(__file__).with_name("naia_patch.py"))
engine=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(engine)
PACKAGE=Path(__file__).resolve().parents[1].parent
def h(b): return hashlib.sha256(b).hexdigest().upper()

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix="NAIA fixture \uD55C\uAE00 spaces "); self.base=Path(self.tmp.name); self.app=self.base/"NAIA fixture \uD55C\uAE00 spaces"; self.app.mkdir(); self.state=self.base/"separate backup"; self.rows=[]
  for name,old,new in (("a",b"old-a",b"new-a"),("b",b"old-b",b"new-b")):
   p=self.app/"resources/naia-backend/core/anima_engine"/(name+".py"); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(old); self.rows.append({"path":p.relative_to(self.app).as_posix(),"original_sha256":h(old),"installed_sha256":h(new),"bytes":new})
  self.tx=engine.Transaction(self.app,self.state,fixture_mode=True)
 def tearDown(self): self.tmp.cleanup()
 def test_install_restore_bytes(self):
  self.tx.install(self.rows,"fixture","fixture"); self.assertEqual(self.tx.restore(),[])
  for r in self.rows:self.assertEqual(h((self.app/r["path"]).read_bytes()),r["original_sha256"])
 def test_tamper_prewrite(self):
  (self.app/self.rows[1]["path"]).write_bytes(b"tampered")
  with self.assertRaises(engine.PatchError):self.tx.install(self.rows,"fixture","fixture")
  self.assertFalse(self.tx.backup.exists()); self.assertFalse(self.tx.receipt.exists()); self.assertEqual((self.app/self.rows[0]["path"]).read_bytes(),b"old-a")
 def test_interrupted_install_rolls_back(self):
  real=os.replace; second=self.app/self.rows[1]["path"]; fired=False
  def replace(a,b):
   nonlocal fired
   if Path(b)==second and not fired:fired=True;raise OSError("interrupt")
   return real(a,b)
  with mock.patch.object(engine.os,"replace",side_effect=replace):
   with self.assertRaises(OSError):self.tx.install(self.rows,"fixture","fixture")
  for r in self.rows:self.assertEqual(h((self.app/r["path"]).read_bytes()),r["original_sha256"])
  self.assertFalse(self.tx.journal.exists())
 def test_conflict_preserved(self):
  self.tx.install(self.rows,"fixture","fixture"); p=self.app/self.rows[0]["path"]; p.write_bytes(b"user edit")
  self.assertEqual(self.tx.restore(),[self.rows[0]["path"]]); self.assertEqual(p.read_bytes(),b"user edit")
 def test_receipt_tamper_and_backup_corruption_fail_closed(self):
  self.tx.install(self.rows,"fixture","fixture")
  envelope=json.loads(self.tx.receipt.read_text(encoding="utf-8"));envelope["document"]["rows"][0]["backup"]="../outside"
  self.tx.receipt.write_text(json.dumps(envelope),encoding="utf-8")
  with self.assertRaisesRegex(engine.PatchError,"authentication"):self.tx.restore()
  # Corrupt a byte-exact backup in a separate fixture. Restore must fail
  # closed and leave the installed app bytes untouched.
  app2=self.base/"backup fixture";app2.mkdir()
  rows2=[]
  for row in self.rows:
   target2=app2/row["path"];target2.parent.mkdir(parents=True,exist_ok=True);target2.write_bytes(b"old-"+target2.stem.encode())
   rows2.append({**row,"original_sha256":h(target2.read_bytes())})
  tx2=engine.Transaction(app2,self.base/"fresh backup",fixture_mode=True)
  tx2.install(rows2,"fixture","fixture")
  backup=tx2.backup/rows2[0]["path"];backup.write_bytes(b"corrupt backup")
  target=app2/rows2[0]["path"]
  with self.assertRaisesRegex(engine.PatchError,"Backup missing or corrupt"):tx2.restore()
  self.assertEqual(target.read_bytes(),b"new-a")

 def test_state_from_other_app_is_rejected(self):
  self.tx.install(self.rows,"fixture","fixture")
  other=self.base/"other app";other.mkdir()
  other_tx=engine.Transaction(other,self.state,fixture_mode=True)
  with self.assertRaisesRegex(engine.PatchError,"another app identity"):other_tx.restore()

 def test_restore_cleanup_resumes_if_journal_unlink_interrupted(self):
  self.tx.install(self.rows,"fixture","fixture")
  real=Path.unlink; fired=False; journal=self.tx.journal
  def unlink(path,*args,**kwargs):
   nonlocal fired
   if path==journal and not fired:
    fired=True
    raise OSError("simulated crash after receipt deletion")
   return real(path,*args,**kwargs)
  with mock.patch.object(Path,"unlink",unlink):
   with self.assertRaisesRegex(OSError,"simulated crash"):self.tx.restore()
  self.assertFalse(self.tx.receipt.exists());self.assertTrue(self.tx.journal.exists())
  self.assertEqual(self.tx.restore(),[])
  self.assertFalse(self.tx.journal.exists())
 def test_partial_restore_resumes(self):
  self.tx.install(self.rows,"fixture","fixture"); real=engine.restore_atomic; second=self.app/self.rows[1]["path"]; fired=False
  def restore(p,b):
   nonlocal fired
   if p==second and not fired:fired=True;raise OSError("interrupt")
   return real(p,b)
  with mock.patch.object(engine,"restore_atomic",side_effect=restore):
   with self.assertRaises(OSError):self.tx.restore()
  self.assertEqual(self.tx.restore(),[])
 def test_unknown_version_and_production_coverage(self):
  with self.assertRaises(engine.PatchError):self.tx.install(self.rows,"v2","v1")
  with self.assertRaises(engine.PatchError):engine.Transaction(self.app,self.state/"strict").install(self.rows,"fixture","fixture")
 def test_disabled_manifest(self):
  with self.assertRaisesRegex(engine.PatchError,"trust pin"):engine.verify_manifest(PACKAGE)
 def test_progress_and_artifact_hash(self):
  self.assertIn("size unknown",engine.progress_line("x",5,None,1));self.assertNotIn("%",engine.progress_line("x",5,None,1));self.assertIn("zero-byte",engine.progress_line("x",0,0,1))
  data=b"bytes";url="https://stable.repo.amd.com/x"
  class R:
   headers={"Content-Length":str(len(data))}
   def __init__(self):self.done=False
   def __enter__(self):return self
   def __exit__(self,*a):return False
   def read(self,n):
    if self.done:return b""
    self.done=True;return data
   def geturl(self):return url
  class O:
   def open(self,*a,**k):return R()
  with tempfile.TemporaryDirectory() as d,mock.patch.object(engine.urllib.request,"build_opener",return_value=O()):
   with self.assertRaisesRegex(engine.PatchError,"SHA-256 mismatch"):engine.download_verified(url,Path(d)/"x","0"*64,{url},progress=lambda _:None)
  with self.assertRaisesRegex(engine.PatchError,"allowlist"):engine.download_verified("https://evil/x",Path("unused"),h(data),set())
 def test_redirect_blocked_unknown_size_progress(self):
  data=b"bytes";url="https://stable.repo.amd.com/x";seen=[]
  class R:
   headers={}
   def __init__(self,redirect=False):self.done=False;self.redirect=redirect
   def __enter__(self):return self
   def __exit__(self,*a):return False
   def read(self,n):
    if self.done:return b""
    self.done=True;return data
   def geturl(self):return "https://evil/x" if self.redirect else url
  class O:
   def __init__(self,redirect=False):self.redirect=redirect
   def open(self,*a,**k):return R(self.redirect)
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"x"
   with mock.patch.object(engine.urllib.request,"build_opener",return_value=O()):engine.download_verified(url,p,h(data),{url},progress=seen.append)
   self.assertTrue(any("size unknown" in x for x in seen))
   with mock.patch.object(engine.urllib.request,"build_opener",return_value=O(True)):
    with self.assertRaisesRegex(engine.PatchError,"Redirected"):engine.download_verified(url,p,h(data),{url})
 def test_path_and_link(self):
  with self.assertRaises(engine.PatchError):engine.safe_target(self.app,"../x")
  p=self.app/"link"
  try:p.symlink_to(self.app/"resources",target_is_directory=True)
  except OSError:self.skipTest("symlink creation unavailable")
  with self.assertRaises(engine.PatchError):engine.safe_target(self.app,"link/new/x")
 def test_locales(self):
  titles=[]
  for lang in ("en","ja","ko"):
   d=json.loads((PACKAGE/"config/resources"/(lang+".json")).read_text(encoding="utf-8"));self.assertTrue(d["unsupported"]);titles.append(d["title"])
  self.assertEqual(len(set(titles)),3)
 def test_package_has_no_private_machine_path_and_lock_is_candidate_only(self):
  for p in PACKAGE.rglob("*"):
   if p.is_file() and p.suffix.lower() in (".json",".py",".md",".ps1",".cmd"):
    self.assertNotIn("E:\\ai\\NAIA-Portable",p.read_text(encoding="utf-8"))
  lock=json.loads((PACKAGE/"config/release-candidate-lock.json").read_text(encoding="utf-8"))
  self.assertEqual(len(lock["reported_wheels"]),9)
  self.assertTrue(all(x["url"] and "%2B" in x["url"] if "+rocm10.0.0" in x["version"] else x["url"] for x in lock["reported_wheels"]))
  self.assertTrue(all(x["sha256"] is None and x["trust"]=="developer-reviewed-content-pin-no-manufacturer-signature" and x["developer_sha256"]==x["observed_sha256"] for x in lock["reported_wheels"]))
  self.assertEqual(lock["status"],"developer-pinned-candidate-content-identity-not-installable")
  manifest=json.loads((PACKAGE/"config/manifest.json").read_text(encoding="utf-8")); self.assertFalse(manifest["enabled"])
 def test_transformer_pin_and_profile_gate(self):
  module=PACKAGE/"config/scripts/amd_transform.py"
  self.assertEqual(engine.sha256_file(module),engine.AMD_TRANSFORM_MODULE_SHA256)
  with self.assertRaisesRegex(engine.PatchError,"Unknown or mismatched"):
   engine.make_transformed_patch_plan(self.app,PACKAGE,{}, {"id":engine.AMD_TRANSFORM_PROFILE_ID}, "nvidia")

 def test_synthetic_transform_install_restore(self):
  transform_path=PACKAGE/"config/scripts/amd_transform.py"
  transform_spec=importlib.util.spec_from_file_location("amd_transform_test",transform_path)
  transform=importlib.util.module_from_spec(transform_spec);transform_spec.loader.exec_module(transform)
  sources={
   "manifest.py": b"# synthetic manifest fixture\nVALUE = 1\n",
   "install.py": b'''from pathlib import Path
import subprocess, time
class ManagedEngineError(RuntimeError): pass
class GpuInfo:
    source: str = "nvidia-smi"
def validate_gpu(gpu):
    pass
class AnimaInstallJob:
    def __init__(self, *, save_root: Path, settings: AnimaSettings, opener=None, run_7z=None, gpu_probe=None,
                 disk_free=None, runtime_factory=None, on_ready=None, clock=time.time, forbidden_roots=(),
                 system_directory=None):
        self.save_root, self.settings = Path(save_root), settings
    def inspect(self, engine_root=None, model_dirs=None):
        return None
''',
   "runtime.py": b'''from pathlib import Path
import subprocess, time
class ManagedEngineError(RuntimeError): pass
class Runtime:
    def __init__(self, engine_root: Path, *, runtime_id: str, reserve_vram_gb: float, idle_minutes: int,
                 model_config=None, command_builder=None, popen=subprocess.Popen, clock=time.monotonic):
        self.engine_root, self.runtime_id = Path(engine_root).resolve(), runtime_id
        self.model_config_path = None
    def _command(self, port):
        return None
    def _engine_environment(self):
        env = clean_environment()
        return env
    def health(self, stats):
                    if not any(x.get("type") == "cuda" for x in stats.get("devices", [])):
                        return False
'''
  }
  baseline={name:h(data) for name,data in sources.items()}
  transformed=transform.transform_sources(sources,baseline)
  self.assertEqual(set(transformed),set(sources))
  relative={"manifest.py":"resources/naia-backend/core/anima_engine/manifest.py",
            "install.py":"resources/naia-backend/core/anima_engine/install.py",
            "runtime.py":"resources/naia-backend/core/anima_engine/runtime.py"}
  rows=[]
  for name,old in sources.items():
   target=self.app/relative[name];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(old)
   new=transformed[name]
   rows.append({"path":relative[name],"original_sha256":h(old),"installed_sha256":h(new),"bytes":new})
  tx=engine.Transaction(self.app,self.state,fixture_mode=True)
  tx.install(rows,"synthetic","synthetic")
  for row in rows:self.assertEqual((self.app/row["path"]).read_bytes(),row["bytes"])
  self.assertEqual(tx.restore(),[])
  for name,old in sources.items():self.assertEqual((self.app/relative[name]).read_bytes(),old)

 def test_headless_install_diagnoses_then_refuses_disabled_manifest(self):
  with tempfile.TemporaryDirectory() as d:
   app=Path(d)/"selected app";app.mkdir()
   argv=["naia_patch.py","install","--package-root",str(PACKAGE),"--app-root",str(app),"--language","ko","--backend-profile","amd-rocm10.0-gfx1201-windows11-25h2-cp313"]
   out=io.StringIO()
   with mock.patch.object(sys,"argv",argv),mock.patch.object(engine,"validate_app_root",return_value=app),mock.patch.object(engine,"diagnose_gpu",return_value=[]),mock.patch.object(engine,"verify_manifest",side_effect=AssertionError("disabled gate must precede trust/install")),redirect_stdout(out):
    self.assertEqual(engine.cli(),2)
   korean=json.loads((PACKAGE/"config/resources/ko.json").read_text(encoding="utf-8"))
   self.assertIn("\uD638\uD658",korean["title"])
   self.assertIn(korean["title"],out.getvalue())
   self.assertIn(korean["unsupported"],out.getvalue())
   self.assertEqual(out.getvalue().encode("utf-8").decode("utf-8"),out.getvalue())
 def test_uninstall_without_receipt_creates_no_state(self):
  with tempfile.TemporaryDirectory() as d:
   app=Path(d)/"selected app";app.mkdir();state=engine.state_root_for_app(app,".backup")
   argv=["naia_patch.py","uninstall","--package-root",str(PACKAGE),"--app-root",str(app),"--language","ko"]
   out=io.StringIO()
   with mock.patch.object(sys,"argv",argv),mock.patch.object(engine,"validate_app_root",return_value=app),mock.patch.object(engine,"assert_not_running"),redirect_stdout(out):
    self.assertEqual(engine.cli(),0)
   self.assertFalse(state.exists());self.assertIn("패치 기록이 없습니다",out.getvalue())
 def test_folder_picker_cancel_and_progress_event_localization(self):
  with tempfile.TemporaryDirectory() as d:
   with mock.patch.object(engine,"locate_naia",return_value=[]):
    with self.assertRaises(engine.PatchError):engine.choose_naia(Path(d),json.loads((PACKAGE/"config/resources/ko.json").read_text(encoding="utf-8")),folder_picker=lambda _:"")
  strings=json.loads((PACKAGE/"config/resources/en.json").read_text(encoding="utf-8"))
  line=engine.render_download_event({"event":"progress","artifact":"x.whl","received_bytes":20,"total_bytes":None,"percent":None,"bytes_per_second":5,"attempt":1},strings)
  self.assertIn("size unknown",line);self.assertNotIn("%",line)
 def test_wrapper_arguments_and_uac_exit_are_forwarded(self):
  for script in ("install-entry.ps1","uninstall-entry.ps1"):
   body=(PACKAGE/"config/scripts"/script).read_text(encoding="utf-8")
   self.assertIn("-Wait -PassThru",body);self.assertIn("$child.ExitCode",body);self.assertIn("--app-root",body);self.assertIn("--language",body);self.assertIn("PYTHONIOENCODING",body);self.assertIn("finally",body);self.assertIn("[Console]::OutputEncoding = $oldEncoding",body)
  for script in ("Install.cmd","Uninstall.cmd"):
   self.assertIn("%*",(PACKAGE/script).read_text(encoding="utf-8"))

if __name__=="__main__":unittest.main(verbosity=2)
