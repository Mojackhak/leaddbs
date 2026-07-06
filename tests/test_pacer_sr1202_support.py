import shutil
import subprocess
import unittest
from pathlib import Path


class PacerSceneRaySr1202SupportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[1]

    def test_leaddbs_maps_sr1202_to_pacer_and_uses_last_contact_as_tail(self):
        source = (self.repo / "ea_runpacer.m").read_text(encoding="utf-8")

        self.assertIn("case 'SceneRay SR1202'", source)
        self.assertIn("model='SceneRay SR1202';", source)
        self.assertIn("markers(side).tail=coords_mm{side}(end,:);", source)
        self.assertNotIn("markers(side).tail=coords_mm{side}(4,:);", source)

    def test_pacer_accepts_sr1202_as_explicit_electrode_type(self):
        pacer_source = (self.repo / "ext_libs/PaCER/src/PaCER.m").read_text(encoding="utf-8")
        refit_source = (self.repo / "ext_libs/PaCER/src/Functions/refitElec.m").read_text(encoding="utf-8")

        self.assertIn("'SceneRay SR1202'", pacer_source)
        self.assertIn("'SceneRay SR1202'", refit_source)

    def test_pacer_geometry_library_contains_sr1202(self):
        matlab = shutil.which("matlab") or "/Applications/MATLAB_R2024b.app/bin/matlab"
        if not Path(matlab).exists():
            self.skipTest("MATLAB is required to inspect electrodeGeometries.mat")

        code_lines = [
            f"cd('{self.repo.as_posix()}');",
            "data = load('ext_libs/PaCER/res/electrodeGeometries.mat');",
            "names = {data.electrodeGeometries.string};",
            "idx = find(strcmp(names, 'SceneRay SR1202'));",
            "assert(numel(idx) == 1, 'SceneRay SR1202 geometry is missing or duplicated.');",
            "geom = data.electrodeGeometries(idx);",
            "assert(geom.noRingContacts == 8, 'SR1202 must have 8 ring contacts.');",
            "assert(abs(geom.diameterMm - 1.27) < 1e-9, 'SR1202 diameter must be 1.27 mm.');",
            "assert(abs(geom.ringContactLengthMm - 1.5) < 1e-9, 'SR1202 contact length must be 1.5 mm.');",
            "assert(isequal(size(geom.ringContactCentersMm), [1 8]), 'SR1202 centers must be a row vector with 8 entries.');",
            "assert(max(abs(geom.ringContactCentersMm - [0.75 2.75 4.75 6.75 8.75 10.75 12.75 14.75])) < 1e-9, 'SR1202 centers are incorrect.');",
            "assert(isequal(size(geom.diffsMm), [1 7]), 'SR1202 diffs must be a row vector with 7 entries.');",
            "assert(max(abs(geom.diffsMm - [2 2 2 2 2 2 2])) < 1e-9, 'SR1202 contact spacing diffs are incorrect.');",
            "assert(abs(geom.zeroToFirstPeakMm - 0.75) < 1e-9, 'SR1202 zeroToFirstPeakMm is incorrect.');",
            "assert(abs(geom.tipToFirstPeakMm - 2.25) < 1e-9, 'SR1202 tipToFirstPeakMm is incorrect.');",
        ]
        code = " ".join(code_lines)

        result = subprocess.run(
            [matlab, "-batch", code],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
        )

        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
