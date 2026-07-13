# Generic VTA Stimulation Contract Design

## Status

```text
design_approved_in_discussion
documentation_written
implementation_not_started
current_study_base_unchanged
```

This document defines the project-independent stimulation hierarchy consumed by
the VTA/E-field pipeline. It preserves the existing `study_base.json` field
names and nesting. It does not introduce duty-cycle fields and does not assign
HF/ULF meaning to raw stimulation components.

## Contract Boundary

```text
program
└── electrode_program
    └── frequency_groups[]
        ├── frequency_group_id
        ├── delivery_mode
        └── sources[]
            ├── source_id
            ├── source_label
            ├── component_id
            ├── frequency_hz
            ├── control_mode
            ├── amplitude
            ├── pulse_width_us
            └── contacts[]
                ├── contact
                ├── polarity
                └── fraction
```

The hierarchy describes recorded stimulation, not anatomy-derived model roles.
`component_id` remains a raw component identity. Frequency classes and clinical
model roles are resolved downstream.

## Frequency Groups

Every source in one frequency group must have exactly the same finite positive
`frequency_hz`. Sources with different frequencies belong to different groups.
Source-level frequency remains serialized even though group membership imposes
this equality invariant.

`delivery_mode = continuous` requires one or more sources. Those sources are
delivered continuously or simultaneously. The fact that all current STNSNr
continuous groups contain one source is a dataset property, not a generic
cardinality limit.

`delivery_mode = alternating` requires at least two sources. Those sources are
distinct alternating stimulation states. No source duty cycle is inferred or
serialized. Sources in either delivery mode may differ in control mode,
amplitude, pulse width, component identity, contact configuration, polarity,
and fraction.

## Sources And Contacts

A source is one independently parameterized stimulation pulse train or state.
Its frequency, control mode, amplitude, and pulse width apply to all contacts
owned by that source. A source contains at least one cathode and at least one
anode. Electrode contacts and `case` may not be duplicated within a source, and
`case` may appear at most once.

The contract supports:

```text
monopolar case-return stimulation
double-monopolar stimulation
bipolar stimulation
multipolar stimulation
multiple independent current control
```

A case-return source uses `case` as its only anode. An electrode-return source
does not also include `case`; one or more electrode contacts provide the return.

## Contact Fraction Resolution

Fractions are resolved independently within each source and polarity. They are
never normalized across sources, including sources in one alternating group.

### Voltage Control

Every active voltage-controlled contact has:

```text
fraction = 1.0
```

Fraction is an active-contact indicator in voltage mode; voltage is not divided
by the number of active contacts.

### Current Control

Explicit contact-specific allocation has precedence. When absolute contact
currents are supplied, the resolved fraction is:

\[
f_{s,k} = \frac{I_{s,k}}{\sum_{j \in C_{s,p}} I_{s,j}}
\]

When complete normalized fractions are supplied, they are preserved after
validating that they are finite, positive, and sum to one within each polarity.

When allocation is absent for every contact of one source and polarity, equal
allocation is inferred:

\[
f_{s,k} = \frac{1}{n_{s,p}}
\]

Partially supplied allocation is invalid. The resolver must not combine
observed fractions with inferred fractions, fill a residual silently, or
silently normalize incomplete input.

For a current-controlled source with total amplitude \(I_s\):

\[
I_{s,k} = I_s f_{s,k}
\]

Cathode fractions and anode fractions each sum to one. A sole case return has
anode fraction `1.0`.

## Voltage Amplitude Semantics

In voltage mode, `source.amplitude = A` is the total cathode-to-anode potential
difference.

For case return:

\[
V_{\mathrm{cathodes}} = -A, \qquad V_{\mathrm{case}} = 0
\]

For bipolar or multipolar electrode return:

\[
V_{\mathrm{cathodes}} = -\frac{A}{2}, \qquad
V_{\mathrm{anodes}} = +\frac{A}{2}
\]

Therefore every cathode-anode pair has potential difference \(A\). Multiple
contacts of one polarity are equipotential, and every active contact retains
fraction `1.0`.

## Delivery-Aware VTA Execution

Continuous sources in one frequency group represent one simultaneous physical
state and require a backend capable of a joint solve. A backend that computes
each source independently and takes a maximum must not label that result as a
joint continuous solve.

Alternating sources are solved independently. Without a recorded duty cycle,
the core pipeline does not generate a time-weighted E-field. An optional binary
union may report whether any alternating state is suprathreshold, but it must be
named as an ever-active union rather than a simultaneous physical field.

Unsupported combinations fail explicitly with
`unsupported_backend_capability`; they do not fall back to a scientifically
different calculation.

## Schema And Validation Requirements

Implementation must preserve field names while adding conditional validation:

```text
control_mode: voltage | current
continuous sources: minItems = 1
alternating sources: minItems = 2
all source frequencies within a group: exactly equal
source contacts: at least one cathode and one anode
voltage fractions: exactly 1.0
current fractions: sum to 1.0 within each polarity
partial current allocation: invalid before serialization
```

The current STNSNr importer remains a voltage-only source adapter unless its
authoritative workbook gains explicit current-control and contact-allocation
fields. It must not infer current mode from voltage columns.

## Current STNSNr Compatibility

The current real study base contains 166 continuous groups with one source and
14 alternating groups with two sources. All 194 sources are voltage controlled,
and every source currently contains one electrode cathode plus case return. The
resolved fraction remains `1.0` for every existing contact record. Adopting this
contract therefore does not alter current stimulation values.

## Evidence Basis

- Lead-DBS Horn treats nonzero contact percentage as activation in constant
  voltage mode and does not split amplitude; in constant current mode it scales
  amplitude by `perc / 100`:
  <https://github.com/netstim/leaddbs/blob/develop/ea_genvat_horn.m>
- Current steering can use simultaneous contacts and unequal independently
  controlled current amplitudes:
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC3360111/>
- MICC divides total current over multiple contacts and supports independent
  contact control:
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC9203070/>
- Interleaving uses distinct alternating settings that may differ in contacts,
  amplitude, and pulse width while sharing frequency:
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC5266041/>
- Dual-frequency DBS supports multiple frequency-defined stimulation groups in
  one clinical program:
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC6858889/>
