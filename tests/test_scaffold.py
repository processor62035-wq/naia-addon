from pathlib import Path
import json
import importlib.util
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryScaffoldTests(unittest.TestCase):
    def test_devcontainer_uses_python_312(self):
        config = json.loads((ROOT / ".devcontainer" / "devcontainer.json").read_text())
        self.assertIn("3.12", config["image"])
        self.assertIn("unittest discover", config["postCreateCommand"])

    def test_example_contains_only_loopback_urls(self):
        lines = [line.strip() for line in (ROOT / ".env.example").read_text().splitlines()]
        assignments = [line for line in lines if line and not line.startswith("#")]
        self.assertEqual(len(assignments), 2)
        for line in assignments:
            key, value = line.split("=", 1)
            self.assertTrue(key.endswith("_BASE_URL"))
            self.assertTrue(value.startswith("http://127.0.0.1:"))

    def test_runtime_and_user_data_are_ignored(self):
        ignored = (ROOT / ".gitignore").read_text()
        for pattern in ("user-data/", "runtime-env/", "*.sqlite3", "*.parquet", "*.safetensors"):
            self.assertIn(pattern, ignored)

    def test_extension_manifest_and_entrypoint_contract(self):
        manifest = json.loads((ROOT / "extension.json").read_text())
        self.assertEqual(manifest["id"], "naia_rocm_runtime")
        self.assertEqual(manifest["naia_ext_api"], 1)
        self.assertEqual(manifest["entry"], "main.py")

        spec = importlib.util.spec_from_file_location("naia_rocm_scaffold", ROOT / "main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class Context:
            messages = []

            def log(self, message):
                self.messages.append(message)

        ctx = Context()
        module.register(ctx)
        self.assertEqual(len(ctx.messages), 1)
        self.assertIn("no backend changes applied", ctx.messages[0])

    def test_docs_mark_gpu_support_unverified(self):
        readme = (ROOT / "README.md").read_text().lower()
        architecture = (ROOT / "ARCHITECTURE.md").read_text().lower()
        self.assertIn("does not claim to enable amd acceleration yet", readme)
        self.assertIn("no gpu success claim is valid before gate 3", architecture)


if __name__ == "__main__":
    unittest.main()

