import hashlib, importlib.util, json, os, tempfile, unittest
from pathlib import Path
from unittest import mock

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
  self.assertTrue(all(x["sha256"] is None and x["trust"]=="unverified" for x in lock["reported_wheels"]))

if __name__=="__main__":unittest.main(verbosity=2)
