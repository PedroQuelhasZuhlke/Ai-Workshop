# Value Notation, Tolerance Codes, Dielectrics, Packages

## SI prefixes

| Prefix | Symbol | Factor |
|---|---|---|
| pico | `p` | 1e-12 |
| nano | `n` | 1e-9 |
| micro | `u`, `µ`, `μ`, `U` | 1e-6 |
| milli | `m` | 1e-3 |
| kilo | `k`, `K` | 1e3 |
| mega | `M`, `Meg` | 1e6 |
| giga | `G` | 1e9 |

`m` vs `M` is case-sensitive and consequential: `1m` = 1 milli, `1M` = 1 mega.
Many BOMs are written by humans who ignore this. When the result is implausible for
the category (a 1 mΩ pull-up, a 1 MF capacitor), flag rather than auto-correct.

## RKM / EIA shorthand

The unit or prefix letter replaces the decimal point. Designed to survive bad
photocopies; still ubiquitous.

| Notation | Value |
|---|---|
| `4k7` | 4.7 kΩ |
| `1R0`, `1R` | 1.0 Ω |
| `R47`, `0R47` | 0.47 Ω |
| `2M2` | 2.2 MΩ |
| `100R` | 100 Ω |
| `4u7` | 4.7 µF |
| `1n5` | 1.5 nF |
| `10p` | 10 pF |
| `2u2` | 2.2 µF |

Grammar: `^(\d*)([RKMGpnuµm])(\d*)$` where the letter is both the multiplier and the
decimal point. Leading group empty means `0.x`.

## Capacitor 3-digit code

Two significant digits plus a decimal exponent, **in picofarads**.

| Code | Value |
|---|---|
| `104` | 10 × 10⁴ pF = 100 nF = 0.1 µF |
| `221` | 22 × 10¹ pF = 220 pF |
| `475` | 47 × 10⁵ pF = 4.7 µF |
| `100` | 10 × 10⁰ pF = 10 pF |
| `4R7` | 4.7 pF (R as decimal point, values < 10 pF) |
| `010` | 1 pF |

A bare 3-digit number on a capacitor is ambiguous with a plain value. `100` is 10 pF
as a code but might mean 100 nF as a careless entry. Flag bare 3-digit capacitor
values unless the source column is explicitly a code column.

## Tolerance letter codes

**These differ between capacitors and resistors. Using the wrong table is a silent
order of magnitude error.**

Capacitors (EIA):

| Code | Tolerance |
|---|---|
| `B` | ±0.1 pF |
| `C` | ±0.25 pF |
| `D` | ±0.5 pF |
| `F` | ±1% |
| `G` | ±2% |
| `J` | ±5% |
| `K` | ±10% |
| `M` | ±20% |
| `Z` | +80% / −20% |

Resistors (IEC 60062):

| Code | Tolerance |
|---|---|
| `B` | ±0.1% |
| `C` | ±0.25% |
| `D` | ±0.5% |
| `F` | ±1% |
| `G` | ±2% |
| `J` | ±5% |
| `K` | ±10% |
| `M` | ±20% |

Note `B`, `C`, `D` mean absolute picofarads on capacitors and percentages on
resistors. Category must be known before decoding.

## E-series

Preferred values. Useful for validating a parsed value and for finding the nearest
standard value during substitution.

| Series | Tolerance | Values per decade |
|---|---|---|
| E6 | ±20% | 6 |
| E12 | ±10% | 12 |
| E24 | ±5% | 24 |
| E48 | ±2% | 48 |
| E96 | ±1% | 96 |
| E192 | ±0.5% / ±0.25% / ±0.1% | 192 |

A parsed resistance that is not an E-series value at the stated tolerance is a
parsing-error signal worth flagging.

## Ceramic capacitor dielectrics

EIA three-character code: low temp limit, high temp limit, capacitance change over
that range.

| Char 1 | Low temp | Char 2 | High temp | Char 3 | Change |
|---|---|---|---|---|---|
| `X` | −55 °C | `4` | +65 °C | `P` | ±10% |
| `Y` | −30 °C | `5` | +85 °C | `R` | ±15% |
| `Z` | +10 °C | `6` | +105 °C | `S` | ±22% |
| | | `7` | +125 °C | `T` | +22 / −33% |
| | | `8` | +150 °C | `U` | +22 / −56% |
| | | `9` | +200 °C | `V` | +22 / −82% |

| Class | Examples | Character |
|---|---|---|
| Class I | `C0G` / `NP0`, `U2J` | Stable, near-zero TC, no DC bias loss, tight tolerance, low capacitance density |
| Class II | `X7R`, `X5R`, `X6S`, `X7S` | High density, significant DC bias and temperature loss |
| Class III | `Y5V`, `Z5U` | Very high density, severe loss. Avoid in new designs |

**Substitution rules that must never be violated:**

- Class I → Class II is never a valid substitution. It changes timing, filtering, and
  oscillator behavior.
- Class II → Class I is only valid if the capacitance is achievable and the engineer
  accepts the package/cost change.
- `X7R` → `X5R` reduces the temperature range (125 °C → 85 °C). Only valid if the
  requirement's temperature range still fits.
- Anything → `Y5V` / `Z5U` requires explicit engineer approval.

**DC bias effect:** Class II MLCCs lose substantial capacitance under applied DC
voltage, and the loss is worse in smaller case sizes. A 0402 X5R 10 µF 6.3 V part can
fall to a small fraction of its nominal value at 5 V. Consequences:

- Voltage rating alone does not make a Class II capacitor equivalent.
- A smaller case size at the same nominal value and voltage is **not** a drop-in.
- Case size reduction on a Class II capacitor is at minimum tier 2, and for bulk
  decoupling or regulator compensation it requires engineer review.

## Passive package codes

| Imperial | Metric | Size (mm) |
|---|---|---|
| `01005` | `0402` | 0.4 × 0.2 |
| `0201` | `0603` | 0.6 × 0.3 |
| `0402` | `1005` | 1.0 × 0.5 |
| `0603` | `1608` | 1.6 × 0.8 |
| `0805` | `2012` | 2.0 × 1.25 |
| `1206` | `3216` | 3.2 × 1.6 |
| `1210` | `3225` | 3.2 × 2.5 |
| `1812` | `4532` | 4.5 × 3.2 |
| `2010` | `5025` | 5.0 × 2.5 |
| `2512` | `6332` | 6.3 × 3.2 |

**The collision:** `0402`, `0603`, `1206` and others are valid codes in *both*
systems with completely different meanings. Rules:

- If the footprint string says `Metric` or uses an IPC prefix (`RESC`, `CAPC`,
  `INDC`), the system is stated — use it.
- Otherwise apply the EDA tool's convention and record `package_system_source` in the
  artifact.
- Never convert between systems without recording both the input and the resolution.

Typical power ratings by imperial size (thick film resistors, verify per series):
`0201` 50 mW, `0402` 62.5–100 mW, `0603` 100 mW, `0805` 125 mW, `1206` 250 mW,
`1210` 500 mW, `2010` 750 mW, `2512` 1 W.

## Common semiconductor and IC packages

| Family | Examples |
|---|---|
| Small-signal | `SOT-23`, `SOT-23-5`, `SOT-23-6`, `SOT-323`, `SOT-89`, `SOT-223` |
| Diodes | `SOD-123`, `SOD-323`, `SOD-523`, `SMA` (DO-214AC), `SMB` (DO-214AA), `SMC` (DO-214AB) |
| Small ICs | `SOIC-8/14/16`, `TSSOP-8..48`, `MSOP-8/10`, `SSOP` |
| No-lead | `DFN`, `QFN`, `WSON`, `VQFN` — pin count and thermal pad matter |
| Quad flat | `QFP`, `LQFP`, `TQFP` |
| Ball grid | `BGA`, `FBGA`, `WLCSP` — ball pitch and count are part of identity |
| Power | `TO-220`, `TO-252`/`DPAK`, `TO-263`/`D2PAK`, `TO-247` |

Lead pitch, thermal pad presence, and pin count are all part of footprint identity.
`QFN-32` with a 4 mm body and `QFN-32` with a 5 mm body are different parts. Never
treat a package *family* name as a footprint match.

## Temperature range notation

Accept `-40..85C`, `-40~85°C`, `-40 to +85 C`, `-40/+85`, `IND` (industrial,
−40…+85 °C), `COM` (commercial, 0…+70 °C), `AUTO` (−40…+125 °C), `MIL`
(−55…+125 °C). Store as explicit min/max in °C; never store the abbreviation alone.
