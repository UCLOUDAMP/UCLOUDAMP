import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "gcce-transform.py"

spec = importlib.util.spec_from_file_location("gcce_transform", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class TransformTests(unittest.TestCase):
    def _base_metadata(self) -> str:
        return """---
site_title: Test Site
legal_name: Test Legal
brand: Test Brand
founder_name: Founder Name
founder_title: Founder Title
location: Test City
domain: example.test
theme: dark
tagline: Test tagline
meta_description: Test description
contact_url: https://github.com/UCLOUDAMP
logo_path: assets/ucloudamp-mark.svg
navigation:
  - label: Home
    id: home
---
"""

    def test_duplicate_section_ids_fail(self):
        document = self._base_metadata() + """
<!-- §section: HERO | id: home -->
## Home
Alpha

<!-- §section: CONTENT | id: home -->
## Duplicate
Beta
"""
        metadata, body = module.parse_frontmatter(document)
        with self.assertRaises(module.BuildError) as ctx:
            module.parse_sections(body)
        self.assertIn("Duplicate section id", str(ctx.exception))
        self.assertEqual(metadata["theme"], "dark")

    def test_unresolved_navigation_anchor_fails(self):
        document = self._base_metadata().replace("id: home", "id: missing") + """
<!-- §section: HERO | id: home -->
## Home
Alpha
"""
        metadata, body = module.parse_frontmatter(document)
        sections = module.parse_sections(body)
        with self.assertRaises(module.BuildError) as ctx:
            module.validate_master(metadata, sections, REPO_ROOT)
        self.assertIn("Unresolved navigation anchor", str(ctx.exception))

    def test_malformed_section_delimiter_fails(self):
        document = self._base_metadata() + """
<!-- §section HERO | id: home -->
## Home
Alpha
"""
        _, body = module.parse_frontmatter(document)
        with self.assertRaises(module.BuildError) as ctx:
            module.parse_sections(body)
        self.assertIn("Malformed section delimiter", str(ctx.exception))

    def test_stale_output_inside_dist_is_replaced(self):
        source = REPO_ROOT / "master.md"
        with tempfile.TemporaryDirectory() as temp_root:
            temp_root_path = Path(temp_root)
            dist = temp_root_path / "dist"
            external = temp_root_path / "outside.txt"
            external.write_text("do not delete", encoding="utf-8")

            module.build(source, dist)
            stale = dist / "stale.txt"
            stale.write_text("old content", encoding="utf-8")

            module.build(source, dist)

            self.assertFalse(stale.exists())
            self.assertTrue(external.exists())

    def test_build_is_deterministic(self):
        source = REPO_ROOT / "master.md"
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            left_dist = Path(left) / "dist"
            right_dist = Path(right) / "dist"
            module.build(source, left_dist)
            module.build(source, right_dist)

            left_manifest = (left_dist / "manifest-sha256.txt").read_text(encoding="utf-8")
            right_manifest = (right_dist / "manifest-sha256.txt").read_text(encoding="utf-8")
            self.assertEqual(left_manifest, right_manifest)

            left_index_hash = hashlib.sha256((left_dist / "index.html").read_bytes()).hexdigest()
            right_index_hash = hashlib.sha256((right_dist / "index.html").read_bytes()).hexdigest()
            self.assertEqual(left_index_hash, right_index_hash)


if __name__ == "__main__":
    unittest.main()
