from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))


class EvidenceConstellationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        static = PROJECT_DIR / "static"
        cls.html = (static / "index.html").read_text(encoding="utf-8")
        cls.javascript = (static / "app.js").read_text(encoding="utf-8")
        cls.css = (static / "styles.css").read_text(encoding="utf-8")

    def test_native_modal_has_named_inspection_controls(self):
        self.assertIn('<dialog id="constellation-modal"', self.html)
        self.assertIn('aria-labelledby="constellation-modal-title"', self.html)
        for control_id in (
            "open-constellation",
            "zoom-in-constellation",
            "zoom-out-constellation",
            "reset-constellation",
            "close-constellation",
        ):
            self.assertIn(f'id="{control_id}"', self.html)

    def test_graph_supports_zoom_pan_keyboard_and_selection(self):
        self.assertIn('addEventListener("wheel"', self.javascript)
        self.assertIn('addEventListener("pointermove"', self.javascript)
        self.assertIn('event.key === "ArrowLeft"', self.javascript)
        self.assertIn("showSelection(", self.javascript)
        self.assertIn("Math.min(3.5", self.javascript)
        self.assertIn("Math.max(0.55", self.javascript)

    def test_graph_uses_semantic_bands_and_compact_node_captions(self):
        self.assertIn('targetSvg.dataset.layout = "evidence-hierarchy"', self.javascript)
        for band in ("retrieved-paper", "evidence", "citation", "concept", "author"):
            self.assertIn(f'"{band}"', self.javascript)
        self.assertIn("function wrapGraphCaption", self.javascript)
        self.assertIn('label.setAttribute("text-anchor", "middle")', self.javascript)

    def test_relationship_labels_are_progressively_disclosed(self):
        self.assertIn('id="toggle-relationship-labels"', self.html)
        self.assertIn('aria-pressed="false"', self.html)
        self.assertIn("relationshipLabelsPinned", self.javascript)
        self.assertIn("show-all-relationship-labels", self.css)
        self.assertIn(".relationship-label.is-previewed", self.css)

    def test_inspection_view_is_responsive_and_reduced_motion_safe(self):
        self.assertIn("height: 100dvh", self.css)
        self.assertIn("touch-action: none", self.css)
        self.assertIn("@media (max-width: 520px)", self.css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.css)


if __name__ == "__main__":
    unittest.main()
