"""Membership cache, statistics, and ranking contract tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from my_helper.fiber.core.seed_target_connectivity.config import resolve_config
from my_helper.fiber.core.seed_target_connectivity.engine import compute_memberships
from my_helper.fiber.core.seed_target_connectivity.errors import CacheError, MembershipError
from my_helper.fiber.core.seed_target_connectivity.statistics import compute_statistics
from my_helper.fiber.core.seed_target_connectivity.tests.helpers import (
    RecordingAdapter,
    line,
    resolved_atlas,
    resolved_mask,
)
from my_helper.fiber.core.seed_target_connectivity.traversal import optimized_membership


class MembershipStatisticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.streamlines = [
            line((0, 1, 1), (4, 1, 1)),
            line((0, 1, 1), (2, 1, 1)),
            line((2.5, 1, 1), (3.25, 1, 1)),
            line((0, 3, 3), (1, 3, 3)),
        ]
        self.seed = resolved_mask([(1, 1, 1)], roi_id="seed", role="seed")
        self.atlas = resolved_atlas(
            [
                resolved_mask([(1, 1, 1)], roi_id="a"),
                resolved_mask([(3, 1, 1)], roi_id="b"),
                resolved_mask([(1, 3, 1)], roi_id="unsupported"),
                resolved_mask([], roi_id="empty"),
            ]
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _config(self, chunk_size: int = 2, cache: bool = True):
        return resolve_config(
            {
                "schema_version": 1,
                "execution": {
                    "fiber_chunk_size": chunk_size,
                    "cache_membership": cache,
                },
            }
        )

    def test_memberships_and_five_statistics_match_hand_calculation(self) -> None:
        membership = compute_memberships(
            RecordingAdapter(self.streamlines),
            self.seed,
            self.atlas,
            self._config(cache=False),
        )
        rows = compute_statistics(membership, self.atlas, ranking_enabled=True)
        by_id = {row.target_id: row for row in rows}

        self.assertEqual(membership.seed_fiber_ids.tolist(), [1, 2])
        self.assertEqual(membership.target_membership.ids_for("a").tolist(), [1, 2])
        self.assertEqual(membership.target_membership.ids_for("b").tolist(), [1, 3])
        self.assertEqual(by_id["a"].raw_fiber_count, 2)
        self.assertEqual(by_id["a"].seed_normalized_fraction, 1.0)
        self.assertEqual(by_id["a"].target_background_prevalence, 0.5)
        self.assertEqual(by_id["a"].connectivity_lift, 2.0)
        self.assertEqual(by_id["a"].connectivity_pmi, 1.0)
        self.assertEqual(by_id["a"].rank, 1)
        self.assertEqual(by_id["b"].raw_fiber_count, 1)
        self.assertEqual(by_id["b"].connectivity_lift, 1.0)
        self.assertEqual(by_id["b"].connectivity_pmi, 0.0)
        self.assertEqual(by_id["b"].rank, 2)

    def test_missing_seed_and_target_caches_share_one_traversal_per_chunk(self) -> None:
        adapter = RecordingAdapter(self.streamlines)
        with patch(
            "my_helper.fiber.core.seed_target_connectivity.engine.optimized_membership",
            wraps=optimized_membership,
        ) as traversed:
            compute_memberships(
                adapter,
                self.seed,
                self.atlas,
                self._config(chunk_size=2, cache=False),
            )

        self.assertEqual(traversed.call_count, 2)

    def test_zero_background_and_empty_target_semantics_are_explicit(self) -> None:
        membership = compute_memberships(
            RecordingAdapter(self.streamlines),
            self.seed,
            self.atlas,
            self._config(cache=False),
        )
        by_id = {
            row.target_id: row
            for row in compute_statistics(membership, self.atlas, ranking_enabled=True)
        }

        unsupported = by_id["unsupported"]
        self.assertEqual(unsupported.target_status, "no_connectome_support")
        self.assertIsNone(unsupported.connectivity_lift)
        self.assertIsNone(unsupported.connectivity_pmi)
        self.assertEqual(unsupported.connectivity_pmi_status, "not_estimable_no_target_support")
        self.assertEqual(unsupported.rank, 3)
        empty = by_id["empty"]
        self.assertEqual(empty.target_status, "empty_after_threshold")
        self.assertIsNone(empty.rank)

    def test_zero_joint_count_uses_negative_infinity_status_not_nonfinite_number(self) -> None:
        seed = resolved_mask([(0, 0, 0)], roi_id="seed", role="seed")
        atlas = resolved_atlas([resolved_mask([(3, 3, 3)], roi_id="target")])
        streamlines = [
            line((-1, 0, 0), (1, 0, 0)),
            line((2.5, 3, 3), (3.25, 3, 3)),
        ]
        membership = compute_memberships(
            RecordingAdapter(streamlines),
            seed,
            atlas,
            self._config(cache=False),
        )

        row = compute_statistics(membership, atlas, ranking_enabled=True)[0]

        self.assertEqual(row.raw_fiber_count, 0)
        self.assertEqual(row.connectivity_lift, 0.0)
        self.assertIsNone(row.connectivity_pmi)
        self.assertEqual(row.connectivity_pmi_status, "negative_infinity")

    def test_chunk_size_does_not_change_membership_or_statistics(self) -> None:
        first = compute_memberships(
            RecordingAdapter(self.streamlines),
            self.seed,
            self.atlas,
            self._config(chunk_size=1, cache=False),
        )
        second = compute_memberships(
            RecordingAdapter(self.streamlines),
            self.seed,
            self.atlas,
            self._config(chunk_size=3, cache=False),
        )

        self.assertTrue(np.array_equal(first.seed_fiber_ids, second.seed_fiber_ids))
        self.assertEqual(
            [row.as_serializable_mapping() for row in compute_statistics(first, self.atlas, ranking_enabled=True)],
            [row.as_serializable_mapping() for row in compute_statistics(second, self.atlas, ranking_enabled=True)],
        )

    def test_ranking_uses_target_id_as_final_tie_break_and_can_be_disabled(self) -> None:
        atlas = resolved_atlas(
            [
                resolved_mask([(1, 1, 1)], roi_id="zeta"),
                resolved_mask([(1, 1, 1)], roi_id="alpha"),
            ]
        )
        membership = compute_memberships(
            RecordingAdapter([line((0, 1, 1), (2, 1, 1))]),
            self.seed,
            atlas,
            self._config(cache=False),
        )

        ranked = {row.target_id: row.rank for row in compute_statistics(membership, atlas, ranking_enabled=True)}
        disabled = compute_statistics(membership, atlas, ranking_enabled=False)

        self.assertEqual(ranked, {"zeta": 2, "alpha": 1})
        self.assertTrue(all(row.rank is None for row in disabled))

    def test_seed_and_target_caches_are_reused_independently(self) -> None:
        config = self._config()
        first_adapter = RecordingAdapter(self.streamlines)
        first = compute_memberships(first_adapter, self.seed, self.atlas, config, self.root)
        self.assertFalse(first.seed_cache_hit)
        self.assertFalse(first.target_cache_hit)
        self.assertEqual(first_adapter.iteration_count, 1)

        repeated_adapter = RecordingAdapter(self.streamlines)
        repeated = compute_memberships(repeated_adapter, self.seed, self.atlas, config, self.root)
        self.assertTrue(repeated.seed_cache_hit)
        self.assertTrue(repeated.target_cache_hit)
        self.assertEqual(repeated_adapter.iteration_count, 0)

        changed_seed = resolved_mask([(2, 1, 1)], roi_id="changed-seed", role="seed")
        changed_seed_adapter = RecordingAdapter(self.streamlines)
        seed_result = compute_memberships(changed_seed_adapter, changed_seed, self.atlas, config, self.root)
        self.assertFalse(seed_result.seed_cache_hit)
        self.assertTrue(seed_result.target_cache_hit)
        self.assertEqual(changed_seed_adapter.iteration_count, 1)

        changed_atlas = resolved_atlas([resolved_mask([(2, 1, 1)], roi_id="changed-target")])
        changed_atlas_adapter = RecordingAdapter(self.streamlines)
        atlas_result = compute_memberships(changed_atlas_adapter, self.seed, changed_atlas, config, self.root)
        self.assertTrue(atlas_result.seed_cache_hit)
        self.assertFalse(atlas_result.target_cache_hit)
        self.assertEqual(changed_atlas_adapter.iteration_count, 1)

    def test_disabled_cache_does_not_write_cache_root(self) -> None:
        cache_root = self.root / "disabled"
        compute_memberships(
            RecordingAdapter(self.streamlines),
            self.seed,
            self.atlas,
            self._config(cache=False),
            cache_root,
        )
        self.assertFalse(cache_root.exists())

    def test_tampered_cache_is_rejected(self) -> None:
        result = compute_memberships(
            RecordingAdapter(self.streamlines),
            self.seed,
            self.atlas,
            self._config(),
            self.root,
        )
        result.seed_cache_path.write_bytes(b"tampered")

        with self.assertRaisesRegex(CacheError, "hash"):
            compute_memberships(
                RecordingAdapter(self.streamlines),
                self.seed,
                self.atlas,
                self._config(),
                self.root,
            )

    def test_seed_without_connectome_support_fails_run(self) -> None:
        seed = resolved_mask([(3, 0, 0)], roi_id="seed", role="seed")
        atlas = resolved_atlas([resolved_mask([(1, 1, 1)], roi_id="target")])
        with self.assertRaisesRegex(MembershipError, "seed"):
            compute_memberships(
                RecordingAdapter([line((0, 1, 1), (2, 1, 1))]),
                seed,
                atlas,
                self._config(cache=False),
            )


if __name__ == "__main__":
    unittest.main()
