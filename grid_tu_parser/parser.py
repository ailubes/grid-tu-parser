from __future__ import annotations

import re
from .activity import normalize_activity
from .models import ParsedTURecord, RawTURecord
from .normalize import normalize_text, slugify_ua


_PARENT_TYPES = [
    ("PS", "ПС"),
    ("CRP", "ЦРП"),
    ("RP", "РП"),
    ("KTP", "КТПП"),
    ("KTP", "СКТП"),
    ("KTP", "КТП"),
    ("ZTP", "ЗТП"),
    ("TP", "ЩТП"),
    ("TP", "ТП"),
]
_CONNECTION_TYPES = [("RU", "РУ"), ("PL", "ПЛІ"), ("PL", "ПЛ"), ("KL", "КЛ")]
_OBJECT_TOKEN_RE = re.compile(r"(?<![А-ЯІЇЄҐA-Z])(ПС|ЦРП|РП|КТПП|СКТП|КТП|ЗТП|ЩТП|ТП|РУ|ПЛІ|ПЛ|КЛ)(?![А-ЯІЇЄҐA-Z])", re.IGNORECASE)
_VOLTAGE_BLOCK_RE = re.compile(r"(?P<volts>\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)+|\d+(?:\.\d+)?)\s*кВ", re.IGNORECASE)
_IDENTIFIER = r"\d+(?:-[A-ZА-ЯІЇЄҐ0-9]+)*"
_NUMBER_RE = re.compile(rf"(?:№\s*|[-]\s*)(?P<number>{_IDENTIFIER})", re.IGNORECASE)


def _parse_voltages(block: str | None) -> list[float]:
    if not block:
        return []
    return [float(part.strip()) for part in block.split("/")]


def _find_object_occurrences(text: str, ua_token: str) -> list[re.Match[str]]:
    return list(re.finditer(rf"(?<![А-ЯІЇЄҐA-Z]){re.escape(ua_token)}(?![А-ЯІЇЄҐA-Z])", text, flags=re.IGNORECASE))


def _next_object_start(text: str, after: int) -> int:
    match = _OBJECT_TOKEN_RE.search(text, after)
    return match.start() if match else len(text)


def _parse_parent_candidate(text: str, code: str, token: str, match: re.Match[str]) -> dict:
    start = match.start()
    token_end = match.end()
    end = _next_object_start(text, token_end)
    segment = text[token_end:end].strip()

    number: str | None = None
    voltage_levels: list[float] = []
    name: str | None = None

    voltage_match = _VOLTAGE_BLOCK_RE.match(segment)
    cursor = 0
    if voltage_match:
        voltage_levels = _parse_voltages(voltage_match.group("volts"))
        cursor = voltage_match.end()

    rest = segment[cursor:].strip()
    number_match = _NUMBER_RE.match(rest)
    if number_match:
        number = number_match.group("number")
        rest = rest[number_match.end():].strip()
    elif code in {"PS", "CRP", "RP", "TP"}:
        explicit = re.match(rf"№\s*({_IDENTIFIER})", rest, re.IGNORECASE)
        if explicit:
            number = explicit.group(1)
            rest = rest[explicit.end():].strip()
    else:
        plain = re.match(rf"(?:-|№)?\s*({_IDENTIFIER})", rest, re.IGNORECASE)
        if plain:
            number = plain.group(1)
            rest = rest[plain.end():].strip()

    if not voltage_levels:
        trailing_voltage = _VOLTAGE_BLOCK_RE.match(rest)
        if trailing_voltage:
            voltage_levels = _parse_voltages(trailing_voltage.group("volts"))
            rest = rest[trailing_voltage.end():].strip()

    if number is None and code in {"PS", "CRP", "RP", "TP"}:
        bare = re.match(rf"({_IDENTIFIER})\b", rest, re.IGNORECASE)
        if bare and not re.match(r"\d+(?:\.\d+)?\s*кВ", rest, re.IGNORECASE):
            number = bare.group(1)
            rest = rest[bare.end():].strip()

    rest = re.split(r"(?:^|\s+)(?=(?:Л|L)\s*-\s*\d|фідер\b)", rest, maxsplit=1, flags=re.IGNORECASE)[0]
    name = rest.strip(" ,-;") or None

    return {
        "code": code,
        "token": token,
        "start": start,
        "number": number,
        "name": name,
        "voltage_levels": voltage_levels,
    }


def _canonical_id(code: str, number: str | None, name: str | None) -> str | None:
    parts = [code]
    if number:
        number_slug = slugify_ua(number)
        if number_slug:
            parts.append(number_slug)
    if name and (code in {"PS", "CRP", "RP"} or not number):
        slug = slugify_ua(name)
        if slug:
            parts.append(slug)
    if len(parts) == 1:
        return None
    return "-".join(parts)


def parse_connection_point(text: str) -> dict:
    normalized = normalize_text(text or "")
    flags: list[str] = []

    result = {
        "connection_object_type": None,
        "connection_voltage_kv": None,
        "connection_object_number": None,
        "connection_object_name": None,
        "feeder_id": None,
        "parent_object_type": None,
        "parent_number": None,
        "parent_name": None,
        "parent_voltage_levels_kv": [],
        "canonical_node_id": None,
        "confidence": 0.0,
        "needs_review": True,
        "flags": flags,
    }

    for code, token in _CONNECTION_TYPES:
        match = re.search(
            rf"(?<![А-ЯІЇЄҐA-Z]){re.escape(token)}\s*-?\s*(\d+(?:\.\d+)?)\s*кВ",
            normalized,
            flags=re.IGNORECASE,
        )
        if match:
            result["connection_object_type"] = code
            result["connection_voltage_kv"] = float(match.group(1))
            break

    feeder_match = re.search(r"(?<![А-ЯІЇЄҐA-Z0-9])(?:Л|L)\s*-\s*(\d+[A-ZА-ЯІЇЄҐ0-9-]*)", normalized, re.IGNORECASE)
    if feeder_match:
        result["feeder_id"] = f"L-{feeder_match.group(1)}".upper()
    else:
        feeder_match = re.search(r"фідер\s*№?\s*([A-ZА-ЯІЇЄҐ0-9-]+)", normalized, re.IGNORECASE)
        if feeder_match:
            result["feeder_id"] = f"FEEDER-{slugify_ua(feeder_match.group(1))}"

    candidates: list[dict] = []
    for code, token in _PARENT_TYPES:
        for match in _find_object_occurrences(normalized, token):
            candidates.append(_parse_parent_candidate(normalized, code, token, match))

    if not candidates:
        flags.append("unknown_object_type")
        return result

    priority = {code: idx for idx, (code, _) in enumerate(_PARENT_TYPES)}
    candidates.sort(key=lambda item: (priority[item["code"]], item["start"]))
    parent = candidates[0]

    distinct = {(item["code"], item["number"], item["start"]) for item in candidates}
    ambiguous = len(distinct) > 1
    if ambiguous:
        flags.append("multiple_parent_candidates")

    result["parent_object_type"] = parent["code"]
    result["parent_number"] = parent["number"]
    result["parent_name"] = parent["name"]
    result["parent_voltage_levels_kv"] = parent["voltage_levels"]
    result["canonical_node_id"] = _canonical_id(parent["code"], parent["number"], parent["name"])

    if parent["number"] and parent["voltage_levels"]:
        confidence = 1.0
    elif parent["number"] or parent["name"]:
        confidence = 0.90 if parent["number"] else 0.75
    else:
        confidence = 0.50
        flags.append("missing_parent_identifier")

    if parent["number"] is None:
        if "missing_parent_identifier" not in flags:
            flags.append("missing_parent_identifier")

    if ambiguous:
        confidence = min(confidence, 0.60)

    result["confidence"] = confidence
    result["needs_review"] = confidence < 0.75
    return result


def parse_record(raw: RawTURecord) -> ParsedTURecord:
    try:
        parsed = parse_connection_point(raw.connection_point_raw or "")
        flags = list(parsed["flags"])
        confidence = parsed["confidence"]
        needs_review = parsed["needs_review"]

        if raw.voltage_raw and parsed["connection_voltage_kv"] is not None:
            voltage_text = normalize_text(raw.voltage_raw)
            try:
                published_voltage = float(voltage_text)
            except ValueError:
                published_voltage = None
            if published_voltage is not None and abs(published_voltage - parsed["connection_voltage_kv"]) > 1e-9:
                flags.append("conflicting_voltage_context")
                confidence = min(confidence, 0.60)
                needs_review = True

        return ParsedTURecord(
            source=raw.source,
            source_url=raw.source_url,
            source_page=raw.source_page,
            fetched_at=raw.fetched_at,
            tu_number=raw.tu_number,
            tu_date=raw.tu_date,
            installation_type=raw.installation_type,
            activity_type=normalize_activity(raw.installation_type or ""),
            requested_power_kw=raw.requested_power_kw,
            connection_type=raw.connection_type,
            rem=raw.rem,
            connection_point_raw=raw.connection_point_raw,
            voltage_raw=raw.voltage_raw,
            connection_object_type=parsed["connection_object_type"],
            connection_voltage_kv=parsed["connection_voltage_kv"],
            connection_object_number=parsed["connection_object_number"],
            connection_object_name=parsed["connection_object_name"],
            feeder_id=parsed["feeder_id"],
            parent_object_type=parsed["parent_object_type"],
            parent_number=parsed["parent_number"],
            parent_name=parsed["parent_name"],
            parent_voltage_levels_kv=parsed["parent_voltage_levels_kv"],
            canonical_node_id=parsed["canonical_node_id"],
            confidence=confidence,
            needs_review=needs_review,
            flags=flags,
        )
    except Exception as exc:
        return ParsedTURecord(
            source=raw.source,
            source_url=raw.source_url,
            source_page=raw.source_page,
            fetched_at=raw.fetched_at,
            tu_number=raw.tu_number,
            tu_date=raw.tu_date,
            installation_type=raw.installation_type,
            activity_type=normalize_activity(raw.installation_type or ""),
            requested_power_kw=raw.requested_power_kw,
            connection_type=raw.connection_type,
            rem=raw.rem,
            connection_point_raw=raw.connection_point_raw,
            voltage_raw=raw.voltage_raw,
            confidence=0.0,
            needs_review=True,
            flags=["parse_error"],
            parse_error=str(exc),
        )
