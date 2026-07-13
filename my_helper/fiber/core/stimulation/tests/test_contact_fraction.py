from __future__ import annotations

import math
import unittest

from core.stimulation.contact_fraction import (
    ContactFractionError,
    resolve_contact_fractions,
    validate_resolved_contact_fractions,
)


CONTACTS = (
    {"contact": 1, "polarity": "cathode"},
    {"contact": 2, "polarity": "cathode"},
    {"contact": "case", "polarity": "anode"},
)


class ContactFractionTests(unittest.TestCase):
    def test_voltage_contacts_are_active_indicators(self) -> None:
        self.assertEqual(
            resolve_contact_fractions(CONTACTS, "voltage"),
            (1.0, 1.0, 1.0),
        )

    def test_current_preserves_complete_observed_fractions(self) -> None:
        self.assertEqual(
            resolve_contact_fractions(
                CONTACTS,
                "current",
                observed_fractions=(0.7, 0.3, 1.0),
            ),
            (0.7, 0.3, 1.0),
        )

    def test_current_normalizes_complete_absolute_currents_by_polarity(self) -> None:
        self.assertEqual(
            resolve_contact_fractions(
                CONTACTS,
                "current",
                observed_currents=(7.0, 3.0, 10.0),
            ),
            (0.7, 0.3, 1.0),
        )

    def test_current_infers_equal_allocation_when_all_values_are_missing(self) -> None:
        self.assertEqual(
            resolve_contact_fractions(
                CONTACTS,
                "current",
                observed_fractions=(None, None, None),
            ),
            (0.5, 0.5, 1.0),
        )

    def test_partial_current_allocation_is_invalid(self) -> None:
        with self.assertRaisesRegex(ContactFractionError, "partial"):
            resolve_contact_fractions(
                CONTACTS,
                "current",
                observed_fractions=(0.7, None, 1.0),
            )

    def test_fraction_and_absolute_current_inputs_are_mutually_exclusive(self) -> None:
        with self.assertRaisesRegex(ContactFractionError, "both"):
            resolve_contact_fractions(
                CONTACTS,
                "current",
                observed_fractions=(0.7, 0.3, 1.0),
                observed_currents=(7.0, 3.0, 10.0),
            )

    def test_invalid_values_and_polarities_are_rejected(self) -> None:
        for values in ((0.7, math.nan, 1.0), (0.7, -0.3, 1.0)):
            with self.subTest(values=values):
                with self.assertRaises(ContactFractionError):
                    resolve_contact_fractions(
                        CONTACTS,
                        "current",
                        observed_fractions=values,
                    )
        with self.assertRaisesRegex(ContactFractionError, "polarity"):
            resolve_contact_fractions(
                ({"contact": 1, "polarity": "neutral"},),
                "current",
            )

    def test_resolved_fraction_validation_is_control_mode_specific(self) -> None:
        validate_resolved_contact_fractions(
            (
                {"contact": 1, "polarity": "cathode", "fraction": 0.7},
                {"contact": 2, "polarity": "cathode", "fraction": 0.3},
                {"contact": "case", "polarity": "anode", "fraction": 1.0},
            ),
            "current",
        )
        with self.assertRaisesRegex(ContactFractionError, "voltage"):
            validate_resolved_contact_fractions(
                (
                    {"contact": 1, "polarity": "cathode", "fraction": 0.5},
                    {"contact": "case", "polarity": "anode", "fraction": 1.0},
                ),
                "voltage",
            )


if __name__ == "__main__":
    unittest.main()
