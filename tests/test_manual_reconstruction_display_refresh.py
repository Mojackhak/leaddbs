import re
import unittest
from pathlib import Path


class ManualReconstructionDisplayRefreshTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[1]
        cls.source = (cls.repo / "ea_mancor_updatescene.m").read_text(encoding="utf-8")

    def test_updatescene_does_not_save_reconstruction_on_plain_refresh(self):
        self.assertIn("saveOnUpdate=getappdata(mcfig,'saveonupdatescene');", self.source)
        self.assertRegex(
            self.source,
            re.compile(
                r"if\s+~isempty\(saveOnUpdate\)\s+&&\s+saveOnUpdate\s*"
                r"\n\s+ea_save_reconstruction\(coords_mm,trajectory,markers,elmodel,1,options\);"
            ),
        )

        footer = self.source.split("%% outputs")[-1]
        self.assertNotIn(
            "\nea_save_reconstruction(coords_mm,trajectory,markers,elmodel,1,options);\n\nsetappdata",
            footer,
        )

    def test_contrasted_ct_textures_are_clamped_before_display(self):
        self.assertIn("imat=clampToUnitRange(imat);", self.source)
        self.assertIn("displaySlice=clampToUnitRange(slice);", self.source)
        self.assertIn("function img=clampToUnitRange(img)", self.source)

    def test_optional_trajectory_plot_is_guarded_on_first_refresh(self):
        self.assertIn(
            "if ~isempty(trajectory_plot) && all(isgraphics(trajectory_plot))",
            self.source,
        )
        self.assertIn(
            "set(trajectory_plot(1),'visible',ea_bool2onoff(options.visible));",
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
