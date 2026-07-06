import unittest
from pathlib import Path


class XRayDorsalSamplingRangeTest(unittest.TestCase):
    def test_xray_dorsal_sampling_range_is_marker_centered(self):
        source = Path(__file__).resolve().parents[1] / "ea_mancor_updatescene.m"
        text = source.read_text(encoding="utf-8")

        self.assertIn("slicstra=-10:1:10;", text)
        self.assertNotIn("slicstra=-10:1:20;", text)


if __name__ == "__main__":
    unittest.main()
