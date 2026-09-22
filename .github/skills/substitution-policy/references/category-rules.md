# Per-Category Rules, Derating Defaults, Safety-Critical Detection

## Status of these numbers

The derating factors below are **proposed defaults**, drawn from common industry
practice. They are configuration, not truth. Before first production use they must be
reviewed and signed off by an engineering authority, stored in
`config/derating.yaml`, versioned, and recorded in every run artifact.

Anywhere a specific standard applies (aerospace, medical, automotive), that standard's
factors override these.

## Derating defaults

Applied to the **requirement** before comparison. `applied × factor ≤ candidate rating`.

| Category | Parameter | Default factor |
|---|---|---|
| Resistor (thick/thin film) | Power | ≤ 60% of rated |
| Resistor | Working voltage | ≤ 80% of max |
| Ceramic capacitor, Class I | DC voltage | ≤ 80% of rated |
| Ceramic capacitor, Class II | DC voltage | ≤ 50% of rated |
| Aluminium electrolytic | Voltage | ≤ 80% of rated |
| Aluminium electrolytic | Ripple current | ≤ 80% of rated at temperature |
| Tantalum (non-polymer) | Voltage | ≤ 50% of rated |
| Tantalum polymer | Voltage | ≤ 80% of rated |
| Film capacitor | Voltage | ≤ 80% of rated |
| Inductor | Saturation current | Isat ≥ 1.5 × peak |
| Inductor | RMS current | Irms ≥ 1.25 × continuous |
| Ferrite bead | Current | ≤ 70% of rated |
| Diode / rectifier | Reverse voltage | ≤ 80% of Vrrm |
| Diode | Forward current | ≤ 75% of If |
| MOSFET | Vds | ≤ 80% of rated |
| MOSFET | Continuous Id | ≤ 75% of rated at case temperature |
| BJT | Vce | ≤ 80% of rated |
| LED | Forward current | ≤ 80% of max |
| Fuse | Continuous current | ≤ 75% of rating |
| Relay | Contact current | ≤ 75% of rating |
| Connector | Contact current | ≤ 80% of rating |
| All | Junction / operating temperature | ≥ 20 °C margin to max |

Tantalum's aggressive voltage derating reflects its failure mode: a shorted tantalum
capacitor can ignite. Do not relax it without explicit authority.

## Per-category compatibility rules

### Resistors

Match: resistance within tolerance, tolerance tighter or equal, power rating after
derating, working voltage, footprint, temperature coefficient (TCR) if specified.

- TCR matters in precision dividers, current-sense, and reference circuits. If the
  requirement states a TCR, a looser TCR is a fail, not a warning.
- Current-sense resistors: the sense element type (metal foil, metal strip) and the
  terminal configuration (2-terminal vs 4-terminal Kelvin) are part of identity.
  Never substitute across terminal counts.
- `0 Ω` jumpers are rated by current, not power.
- Pull-ups and pull-downs are the most tolerant of substitution; precision analog
  paths are the least. The policy engine cannot see circuit function, so it cannot
  relax based on it — the engineer can, during review.

### Capacitors

Match: capacitance, tolerance, voltage rating after derating, dielectric class,
temperature range, footprint. ESR window and ripple current where specified.

- Dielectric class change is a hard fail (see part-normalization reference).
- Class II case-size reduction at equal value and voltage is at minimum tier 2 because
  of DC bias loss.
- Electrolytics additionally match: ESR window, ripple current at temperature, rated
  lifetime hours at temperature, and polarity/form factor.
- X-class and Y-class safety capacitors are safety-critical. See below.

### Inductors and ferrite beads

Match: inductance and tolerance, saturation current, RMS current, DCR maximum,
self-resonant frequency, shielding, footprint.

- DCR is a maximum — lower is generally safe, but a large DCR change affects regulator
  efficiency and loop response. Flag changes beyond a configured band.
- Ferrite beads are specified by impedance at a frequency, not inductance. Matching
  "100 Ω" without matching the frequency is meaningless.
- SRF below the circuit's operating frequency is a fail.

### Diodes, LEDs, transistors

Match: reverse voltage, forward current, forward voltage window, recovery time for
switching, package and pinout.

- Pinout within a package family varies. `SOT-23` transistors exist in multiple pin
  assignments — pinout is part of footprint identity.
- Schottky ↔ standard rectifier substitution changes forward drop and reverse leakage.
  Tier 2 at best.
- LEDs match on colour/wavelength, luminous intensity bin, viewing angle, and lens
  type. Bin codes are part of identity for indicator-matched designs.

### Integrated circuits

Default to **exact MPN**. Tier 0 only, unless the engineer explicitly opens it up.

- Manufacturer suffixes encode package, temperature grade, tape/reel, and lifecycle.
  `XYZ123IDR` and `XYZ123IDT` differ only in packaging; `XYZ123IPW` is a different
  package. Parse suffixes with a per-manufacturer table, never with a generic rule.
- "Pin-compatible" parts from different manufacturers are tier 2 at best: electrical
  characteristics, internal protection, and errata differ.
- Programmable and configured parts (EEPROM-configured, factory-trimmed, firmware-
  loaded) are never substitutable without engineering action.

### Crystals and oscillators

Match: frequency, frequency tolerance, frequency stability over temperature, **load
capacitance**, ESR maximum, drive level, footprint.

Load capacitance mismatch pulls the oscillator off frequency and can prevent start-up.
It is a hard parameter, not a preference. Crystal substitution is tier 2 minimum.

### Connectors, switches, relays

Mechanical identity dominates. Mating cycles, contact plating, current and voltage
ratings, mounting style, keying, and gender must all match. Substitution is tier 2
minimum and frequently tier 3. A connector that mates with an external harness is
effectively `do_not_substitute`.

## Safety-critical detection

Classify a requirement as `safety` when any of these hold. Safety-critical parts are
restricted to tier 0 — exact MPN only.

**By category:**

- Fuses, PTC resettable fuses, thermal cutoffs
- X-class and Y-class safety capacitors (mains-connected)
- Optocouplers and digital isolators
- Isolation transformers, common-mode chokes in mains paths
- Mains-rated relays and switches
- Varistors / MOVs used for surge protection
- Creepage- and clearance-dependent parts
- Medical, aerospace, or functional-safety qualified parts

**By description or parameter token:**

`Y1`, `Y2`, `X1`, `X2`, `VDE`, `UL`, `CSA`, `TÜV`, `ENEC`, `IEC 60384-14`,
`IEC 62368`, `reinforced insulation`, `basic insulation`, `safety agency`,
`mains`, `line voltage`, `SELV`, `creepage`, `clearance`, `functional safety`,
`SIL`, `ASIL`, `ISO 13849`, `IEC 61508`

**By engineer marking:** an explicit `do_not_substitute` or criticality column in the
BOM always wins over automatic classification.

Automatic classification may only ever *increase* criticality. It can never downgrade
a part the engineer marked.

## Compliance tags

| Tag | Regression rule |
|---|---|
| `RoHS` | compliant → non-compliant or unknown = fail |
| `REACH` | SVHC status may not worsen; unknown = fail when required |
| `AEC-Q100` / `AEC-Q200` | required → not qualified = fail |
| `halogen_free` | required → not stated = fail |
| `conflict_minerals` | informational, surfaced not gated |
| `ITAR` / `export_controlled` | informational, surfaced prominently |

Unknown compliance status never satisfies a required compliance tag. Fail closed.

## Lifecycle sources

Lifecycle comes from the supplier catalog or manufacturer, with provenance. If two
sources disagree, take the more pessimistic value and record both.
