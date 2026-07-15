"""Tests for strict run-local jitter geometry manifests."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from outcome_models.services.jitter_inputs import (
    build_direct_geometry,
    build_fiber_geometry,
    direct_sampling_rows,
    side_field_sampling_rows,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class JitterInputManifestTests(unittest.TestCase):
    @staticmethod
    def _file(root: Path, relative_path: str) -> Path:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative_path.encode("utf-8"))
        return path

    def test_direct_rows_preserve_subject_order_and_hash_every_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            right_1 = self._file(root, "right/s1.nii")
            left_1 = self._file(root, "flipped/s1.nii")
            right_2 = self._file(root, "right/s2.nii")
            left_2 = self._file(root, "flipped/s2.nii")
            rows = direct_sampling_rows(
                [
                    {
                        "subject_id": "s1",
                        "right": [{"path": str(right_1)}],
                        "left_to_right": [{"path": str(left_1)}],
                    },
                    {
                        "subject_id": "s2",
                        "right": [{"path": str(right_2)}],
                        "left_to_right": [{"path": str(left_2)}],
                    },
                ],
                ("s1", "s2"),
            )
            right_1_sha = _sha256(right_1)
            left_2_sha = _sha256(left_2)

        self.assertEqual([row["subject_id"] for row in rows], ["s1", "s2"])
        self.assertEqual(
            rows[0]["right"][0],
            {"path": str(right_1.resolve()), "sha256": right_1_sha},
        )
        self.assertEqual(
            rows[1]["left_to_right"][0],
            {"path": str(left_2.resolve()), "sha256": left_2_sha},
        )

    def test_side_field_rows_resolve_flipped_left_paths_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            right = self._file(root, "source/s1_right.nii")
            left_source = self._file(root, "source/s1_left.nii")
            flipped = self._file(root, "flipped/s1_hemi-L_src-01_to_R.nii")
            rows = side_field_sampling_rows(
                [
                    {"subject_id": "s1", "side": "R", "source_paths": [str(right)]},
                    {"subject_id": "s1", "side": "L", "source_paths": [str(left_source)]},
                ],
                ("s1",),
                flipped_root=root / "flipped",
            )
            right_sha = _sha256(right)
            flipped_sha = _sha256(flipped)

        self.assertEqual(
            rows[0]["right"],
            [{"path": str(right.resolve()), "sha256": right_sha}],
        )
        self.assertEqual(
            rows[0]["left_to_right"],
            [{"path": str(flipped.resolve()), "sha256": flipped_sha}],
        )

    def test_direct_geometry_uses_only_the_declared_direct_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            final_xyz = self._file(root, "final_xyz.npy")
            matched_xyz = self._file(root, "matched_xyz.npy")
            support_xyz = self._file(root, "support_xyz.npy")
            matched_indices = self._file(root, "matched_indices.npy")
            rows = [{"subject_id": "s1", "right": [], "left_to_right": []}]
            geometry = build_direct_geometry(
                final_candidate_xyz=final_xyz,
                hf_component_sampling_qc=rows,
                ulf_component_sampling_qc=rows,
                matched_hf_candidate_xyz=matched_xyz,
                hf_support_xyz=support_xyz,
                matched_hf_candidate_indices_in_support=matched_indices,
                hf_reference_sampling_qc=rows,
            )
            final_xyz_sha = _sha256(final_xyz)

        self.assertEqual(geometry["builder"], "direct_efield_resample_v1")
        self.assertEqual(geometry["final_candidate_xyz"]["sha256"], final_xyz_sha)
        self.assertEqual(
            set(geometry),
            {
                "builder",
                "final_candidate_xyz",
                "hf_component_sampling_qc",
                "ulf_component_sampling_qc",
                "matched_hf_candidate_xyz",
                "hf_support_xyz",
                "matched_hf_candidate_indices_in_support",
                "hf_reference_sampling_qc",
            },
        )

    def test_fiber_geometry_hashes_the_configured_connectome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_mat = self._file(root, "connectome/data.mat")
            rows = [{"subject_id": "s1", "right": [], "left_to_right": []}]
            geometry = build_fiber_geometry(
                connectome_data_mat=data_mat,
                hf_component_sampling_qc=rows,
                ulf_component_sampling_qc=rows,
                hf_reference_sampling_qc=rows,
            )
            data_mat_sha = _sha256(data_mat)

        self.assertEqual(geometry["builder"], "normative_fiber_efield_resample_v1")
        self.assertEqual(
            geometry["connectome_data_mat"],
            {"path": str(data_mat.resolve()), "sha256": data_mat_sha},
        )

    def test_sampling_rows_reject_missing_or_reordered_subjects(self) -> None:
        with self.assertRaisesRegex(ValueError, "subject order mismatch"):
            direct_sampling_rows(
                [{"subject_id": "s2", "right": [], "left_to_right": []}],
                ("s1",),
            )

    def test_side_field_rows_reject_duplicate_empty_side_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "duplicate jitter side-field row"):
                side_field_sampling_rows(
                    [
                        {"subject_id": "s1", "side": "R", "source_paths": []},
                        {"subject_id": "s1", "side": "R", "source_paths": []},
                        {"subject_id": "s1", "side": "L", "source_paths": []},
                    ],
                    ("s1",),
                    flipped_root=Path(tmp) / "flipped",
                )

    def test_side_field_rows_require_explicit_empty_rows_for_both_sides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "missing jitter side-field row"):
                side_field_sampling_rows(
                    [{"subject_id": "s1", "side": "R", "source_paths": []}],
                    ("s1",),
                    flipped_root=Path(tmp) / "flipped",
                )


if __name__ == "__main__":
    unittest.main()
