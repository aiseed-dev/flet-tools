import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "write_build_version", Path(__file__).resolve().parent.parent / "write_build_version.py",
)
wbv = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(wbv)


class VersionFor(unittest.TestCase):
    def test_a_tag_gives_its_number(self):
        self.assertEqual(wbv.version_for("refs/tags/app-v0.1.1", "abcdef1234"), ("0.1.1", True))
        self.assertEqual(wbv.version_for("refs/tags/app-v12.0.30", "abcdef1234"), ("12.0.30", True))

    def test_a_tag_of_the_wrong_shape_is_refused(self):
        for name in ["app-v0.1", "app-v1.2.3.4", "app-v1.2.x", "v0.1.1", "app-v0.1.1-rc1", "app-v"]:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, r"app-vX\.Y\.Z"):
                wbv.version_for(f"refs/tags/{name}", "abcdef1234")

    def test_another_prefix(self):
        self.assertEqual(wbv.version_for("refs/tags/desk.v2.0.1", "abc", "desk.v"), ("2.0.1", True))
        # The prefix is literal: "." is not a wildcard.
        with self.assertRaises(ValueError):
            wbv.version_for("refs/tags/deskxv2.0.1", "abc", "desk.v")

    def test_a_branch_gets_a_dev_version_with_the_short_sha(self):
        self.assertEqual(wbv.version_for("refs/heads/main", "0123456789abcdef"),
                         ("0.0.0.dev0+0123456", False))
        self.assertEqual(wbv.version_for("", "0123456789abcdef"), ("0.0.0.dev0+0123456", False))


class Main(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.out = self.root / "_build_version.py"
        self.github_env = self.root / "github_env"

    def test_writes_the_file_and_exports_the_release_version(self):
        env = {"GITHUB_REF": "refs/tags/app-v0.2.0", "GITHUB_SHA": "abc", "GITHUB_ENV": str(self.github_env)}
        self.assertEqual(wbv.main(["--out", str(self.out)], env), 0)
        self.assertEqual(self.out.read_text(), '__version__ = "0.2.0"\n')
        self.assertEqual(self.github_env.read_text(), "BUILD_VERSION=0.2.0\n")

    def test_a_branch_exports_nothing(self):
        env = {"GITHUB_REF": "refs/heads/main", "GITHUB_SHA": "abcdef123456", "GITHUB_ENV": str(self.github_env)}
        self.assertEqual(wbv.main(["--out", str(self.out)], env), 0)
        self.assertIn("0.0.0.dev0+abcdef1", self.out.read_text())
        self.assertFalse(self.github_env.exists())

    def test_a_bad_tag_fails_and_writes_nothing(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = wbv.main(["--out", str(self.out)], {"GITHUB_REF": "refs/tags/app-v1.2", "GITHUB_SHA": "abc"})
        self.assertEqual(code, 1)
        self.assertIn("app-vX.Y.Z", err.getvalue())
        self.assertFalse(self.out.exists())

    def test_the_tag_prefix_option(self):
        env = {"GITHUB_REF": "refs/tags/desk-v1.0.0", "GITHUB_SHA": "abc"}
        self.assertEqual(wbv.main(["--out", str(self.out), "--tag-prefix", "desk-v"], env), 0)
        self.assertEqual(self.out.read_text(), '__version__ = "1.0.0"\n')


if __name__ == "__main__":
    unittest.main()
