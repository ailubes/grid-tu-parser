# Grid TU Parser - Design Specification

Date: 2026-08-30
Scope: MVP parser for public Distribution System Operator (DSO/OSR) technical-conditions registries, starting with Lvivoblenergo.

## 1. Goal

Build a deterministic parser that converts raw technical-conditions registry rows into normalized electrical-network entities suitable for later aggregation by node and calculation of Generation / Load / BESS pressure indicators.

The parser must preserve the original raw source record, extract structured fields when confidence is sufficient, and explicitly mark ambiguous records for manual review rather than guessing.

## 2. MVP input

Primary source: public Lvivoblenergo technical-conditions registry HTML pages.

Each source row is stored unchanged with at least:
- source_url
- source_page
- fetched_at
- tu_number
- tu_date
- installation_type
- connection_point_raw
- voltage_raw if separately published
- requested_power_kw
- connection_type
- rem / district

## 3. Core parsing principles

1. Raw data is immutable.
2. Parsing is deterministic and rule-based.
3. Parent network nodes and connection-side objects are separate concepts.
4. Unknown or ambiguous values are not inferred silently.
5. Every parsed record carries a confidence score and parse flags.
6. Canonical identifiers must be stable across punctuation and wording variants.

## 4. Entity model

### 4.1 Parent node

Supported MVP parent node types:
- PS - substation / ПС
- KTP - kiosk/package transformer substation / КТП
- ZTP - enclosed transformer substation / ЗТП
- TP - generic transformer substation / ТП
- RP - distribution point / РП
- CRP - central distribution point / ЦРП

Fields:
- parent_object_type
- parent_number
- parent_name
- parent_voltage_levels_kv[]
- canonical_node_id

### 4.2 Connection-side object

Supported MVP types:
- RU - switchgear / РУ
- PL - overhead line / ПЛ
- KL - cable line / КЛ
- feeder - feeder / фідер / Л-N
- bus_section - bus or section if recognizable

Fields:
- connection_object_type
- connection_voltage_kv
- connection_object_number/name
- feeder_id if present

### 4.3 Registry activity type

Normalize source installation type into:
- generation
- consumption
- bess
- mixed
- unknown

Recognize common Ukrainian variants including УЗЕ for BESS.

## 5. Parsing pipeline

### Stage A - text normalization

Normalize:
- Unicode spaces
- repeated whitespace
- commas in decimal voltages where needed
- different number signs: №, N, No.
- hyphen/dash variants
- case for matching, while preserving original text

Do not transliterate source names for display.

### Stage B - detect parent entity

Search with ordered rules, preferring explicitly named substations over downstream objects when both are present.

Examples:
- `РУ-10 кВ ПС 35/10 кВ №144 Страдч`
  - parent = PS 144 Stradch
  - connection object = RU 10 kV

- `ПЛ-0,4 кВ КТП-208-11 Л-2`
  - parent = KTP 208-11
  - connection object = PL 0.4 kV
  - feeder = L-2

### Stage C - voltage extraction

Extract ordered voltage levels associated with the parent entity.

Examples:
- `ПС 110/10/6 кВ` -> [110, 10, 6]
- `ПС 35/10 кВ` -> [35, 10]
- `ПЛ-0,4 кВ` -> connection_voltage_kv = 0.4

### Stage D - canonical node ID

Canonical ID rules:
- Prefer object type + official numeric identifier where present.
- Preserve compound identifiers such as `208-11`.
- Add normalized name only when needed for disambiguation or when no number exists.

Examples:
- `ПС 35/10 кВ №144 Страдч` -> `PS-144-STRADCH`
- `ПС №144 Страдч` -> same canonical ID
- `КТП-208-11` -> `KTP-208-11`

For MVP, transliteration for IDs is deterministic ASCII Ukrainian transliteration with punctuation collapsed to hyphens.

### Stage E - confidence and flags

Confidence guide:
- 1.00: parent type + unique identifier + structured voltages parsed cleanly
- 0.90: parent type + number/name parsed, partial voltage data
- 0.75: parent node inferred from recognizable pattern without unique number
- <0.75: `needs_review = true`

Flags may include:
- multiple_parent_candidates
- missing_parent_identifier
- unparsed_voltage
- unknown_object_type
- conflicting_voltage_context
- malformed_source_text

## 6. Output schema

Each normalized row should include:

```json
{
  "source": "lvivoblenergo",
  "tu_number": "...",
  "tu_date": "2026-05-28",
  "activity_type": "bess",
  "requested_power_kw": 3000.0,
  "connection_point_raw": "РУ-10 кВ ПС 35/10 кВ №144 Страдч",
  "connection_object_type": "RU",
  "connection_voltage_kv": 10.0,
  "parent_object_type": "PS",
  "parent_number": "144",
  "parent_name": "Страдч",
  "parent_voltage_levels_kv": [35.0, 10.0],
  "canonical_node_id": "PS-144-STRADCH",
  "confidence": 1.0,
  "needs_review": false,
  "flags": []
}
```

## 7. Aggregation-ready outputs

The parser itself does not calculate GridScore. It produces clean records that allow a separate aggregator to calculate, per canonical node:
- gross TU generation MW
- gross TU consumption MW
- gross TU BESS MW
- counts by type
- 3/6/12 month additions
- activity velocity
- first/last observed dates

This separation avoids coupling parser correctness to later scoring logic.

## 8. Error handling

- HTTP/page errors are logged and retried by the collector, not hidden.
- Rows that fail field conversion remain stored in raw form.
- Parser exceptions must be converted into parse-error records with the raw text preserved.
- No source row may disappear because parsing failed.

## 9. Testing strategy

Use fixture-driven tests with real anonymized/public examples.

Minimum initial test cases:
1. `РУ-10 кВ ПС 35/10 кВ №144 Страдч`
2. `РУ-6 кВ ПС 110/10/6 кВ №249 Львів-10`
3. `ПЛ-0,4 кВ КТП-208-11 Л-2`
4. parent PS without RU prefix
5. KTP/ZTP/TP variants
6. decimal comma voltage
7. missing number but present name
8. two possible parent entities -> needs_review
9. malformed punctuation/spacing
10. УЗЕ activity normalization

Success criteria for MVP:
- >=95% deterministic parse rate on clearly structured rows
- zero silent dropping of source rows
- identical canonical IDs for known textual variants of the same node
- ambiguous rows surfaced for review

## 10. Initial implementation boundary

MVP components:
1. `collector.py` - fetch paginated registry rows
2. `models.py` - dataclasses / typed records
3. `normalize.py` - text and transliteration normalization
4. `parser.py` - deterministic extraction rules
5. `activity.py` - generation/consumption/BESS normalization
6. `export.py` - CSV and JSON output
7. `tests/` - fixture-driven unit tests

Not in MVP:
- PostGIS
- full physical grid topology
- SCADA/AMI integration
- GridScore calculation
- LLM fallback
- automatic entity reconciliation across different OSRs

## 11. Extension path

After Lvivoblenergo validation, add OSR-specific adapters while keeping the normalized output schema unchanged. Shared parser primitives should be reused where wording overlaps; source-specific quirks remain in adapters.
