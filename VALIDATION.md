# Validation Notes

Date: 2026-08-30

## Current public-registry format check

The current Lvivoblenergo public TU registry exposes 8,285 rows and the expected columns for TU number/date, installation type, connection point, voltage, requested power, connection type, and OSR territorial unit.

The parser was manually smoke-validated against connection-point strings visible on the current first two registry pages through the web-access layer.

### Page 1 sample

20 distinct current strings were checked.

- canonical node ID produced: 19/20 (95%)
- review rows: 1/20 (5%)
- the only review string was `ПЛ-10 кВ 201-37 Чишки`, which contains a line identifier but no explicit PS/TP/KTP parent node; the parser intentionally does not guess the parent.

The sample included PS, KTP, ZTP, KTPP, SKTP, ShchTP, PLI, RU, PL, KL, feeder suffixes, addresses, and an alphanumeric compound transformer identifier.

### Page 2 sample

15 distinct current strings were checked.

- canonical node ID produced: 15/15 (100%)
- review rows: 0/15 (0%)

## Sandbox limitation

Direct outbound DNS/network access from the code-execution container is disabled, so the collector could not perform an end-to-end HTTP fetch against the live registry from inside Python. The collector is instead covered by fixture-driven tests using the current live table headers and representative current rows. The public web-access layer independently confirmed that the live registry schema still matches those headers.
