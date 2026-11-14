"""Grounding checks for free-text briefing claims."""

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z-])\d[\d,]*(?:\.\d+)?")
_PLAN_NUMBER_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?")
_ROUTE_ID_PATTERN = re.compile(
    r"\broute[-_\s]+\d+(?:[-_][A-Za-z0-9]+)*\b", re.IGNORECASE
)
_PLACE_PATTERN = re.compile(
    r"\b[A-Z][a-z]+(?:['-][A-Z]?[a-z]+)*(?:\s+[A-Z][a-z]+(?:['-][A-Z]?[a-z]+)*)*\b"
)
_NON_PLACE_WORDS = {
    "a",
    "about",
    "after",
    "all",
    "an",
    "and",
    "any",
    "apr",
    "april",
    "are",
    "around",
    "as",
    "at",
    "aug",
    "august",
    "avoid",
    "before",
    "brief",
    "by",
    "checkpoint",
    "checkpoints",
    "consider",
    "confirm",
    "conditions",
    "current",
    "data",
    "dec",
    "december",
    "delay",
    "dispatch",
    "distance",
    "driver",
    "estimated",
    "ensure",
    "expected",
    "every",
    "feb",
    "february",
    "for",
    "forecast",
    "from",
    "gap",
    "high",
    "hold",
    "hours",
    "if",
    "in",
    "is",
    "jan",
    "january",
    "jul",
    "july",
    "jun",
    "june",
    "listed",
    "low",
    "maintain",
    "mar",
    "march",
    "may",
    "medium",
    "miles",
    "moderate",
    "monitor",
    "no",
    "not",
    "notify",
    "nov",
    "november",
    "of",
    "oct",
    "october",
    "or",
    "please",
    "provide",
    "proceed",
    "rain",
    "recommended",
    "reroute",
    "review",
    "reviewing",
    "route",
    "risk",
    "risks",
    "severe",
    "snow",
    "summary",
    "the",
    "these",
    "this",
    "those",
    "that",
    "to",
    "travel",
    "until",
    "use",
    "unavailable",
    "when",
    "weather",
    "with",
    "wind",
    "sep",
    "sept",
    "september",
}


def check_grounding(briefing, route_plan):
    """Return grounding violations in the summary and dispatcher actions."""
    claims = "{} {}".format(briefing.summary, " ".join(briefing.dispatcher_actions))
    unsupported_routes = _unsupported_route_ids(claims, route_plan)

    claims_without_route_ids = _ROUTE_ID_PATTERN.sub("", claims)
    unsupported_numbers = _unsupported_numbers(claims_without_route_ids, route_plan)
    unsupported_places = _unsupported_place_words(claims, route_plan)

    errors = []
    if unsupported_routes:
        errors.append("unsupported_route_id")
    if unsupported_numbers:
        errors.append("unsupported_number")
    if unsupported_places:
        errors.append("unsupported_place_name")
    return errors


def find_offending_tokens(briefing, route_plan):
    """Return exact unsupported number, route-ID, and place-name tokens."""
    claims = "{} {}".format(briefing.summary, " ".join(briefing.dispatcher_actions))
    claims_without_route_ids = _ROUTE_ID_PATTERN.sub("", claims)
    route_ids = _unsupported_route_ids(claims, route_plan)
    return {
        "numbers": _unsupported_numbers(claims_without_route_ids, route_plan),
        "route_ids": list(dict.fromkeys(route_ids)),
        "place_names": _unsupported_place_words(claims, route_plan),
    }


def _unsupported_route_ids(claims, route_plan):
    return list(
        dict.fromkeys(
            match.group()
            for match in _ROUTE_ID_PATTERN.finditer(claims)
            if not _route_id_is_grounded(match.group(), route_plan)
        )
    )


def _route_id_is_grounded(candidate, route_plan):
    aliases = set()
    for route in route_plan["routes"]:
        route_id = str(route["id"])
        aliases.add(_normalize_route_id(route_id))
        prefix = re.match(r"route[-_\s]*(\d+)", route_id, re.IGNORECASE)
        if prefix:
            aliases.add(_normalize_route_id("route{}".format(prefix.group(1))))
    return _normalize_route_id(candidate) in aliases


def _normalize_route_id(route_id):
    return re.sub(r"[^a-z0-9]", "", str(route_id).casefold())


def _unsupported_numbers(claims, route_plan):
    allowed_numbers = _route_plan_numbers(route_plan)
    unsupported = []
    for match in _NUMBER_PATTERN.finditer(claims):
        try:
            number = Decimal(match.group().replace(",", "")).normalize()
        except InvalidOperation:
            continue
        if number not in allowed_numbers:
            unsupported.append(match.group())
    return list(dict.fromkeys(unsupported))


def _unsupported_place_words(claims, route_plan):
    allowed_words = _route_plan_place_words(route_plan)
    return list(
        dict.fromkeys(
            match.group()
            for phrase in _PLACE_PATTERN.finditer(claims)
            for match in re.finditer(r"[A-Za-z]+(?:['-][A-Za-z]+)*", phrase.group())
            if match.group().casefold() not in allowed_words
            and match.group().casefold() not in _NON_PLACE_WORDS
        )
    )


def _route_plan_place_words(route_plan):
    words = set()
    for location_key in ("origin", "destination"):
        location = route_plan.get(location_key, {})
        if isinstance(location, dict):
            for value in location.values():
                if isinstance(value, str):
                    words.update(word.casefold() for word in _place_words(value))
    for route in route_plan["routes"]:
        summary = route.get("summary", "")
        if isinstance(summary, str):
            words.update(word.casefold() for word in _place_words(summary))
    return words


def _place_words(value):
    return {
        word
        for word in re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)*", value)
        if word[:1].isupper()
    }


def _route_plan_numbers(route_plan):
    numbers = set()
    mile_field_sums = {}
    total_checkpoints = 0

    for value in route_plan.values():
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            _add_number(numbers, value)

    for route in route_plan["routes"]:
        checkpoints = route["checkpoints"]
        checkpoint_count = len(checkpoints)
        total_checkpoints += checkpoint_count
        _add_number(numbers, checkpoint_count)
        for index in range(checkpoint_count):
            _add_number(numbers, index)

        for field, value in route.items():
            if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                _add_number(numbers, value)
            if field.endswith("Miles") and value is not None:
                _add_to_sum(mile_field_sums, field, value)
            if field in {"arrival"} and isinstance(value, str):
                _add_numbers_from_datetime(numbers, value)

        mile_marker_sum = Decimal(0)
        has_mile_markers = False
        for checkpoint in checkpoints:
            for field, value in checkpoint.items():
                if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                    _add_number(numbers, value)
                if field == "mile" and value is not None:
                    mile_marker_sum += Decimal(str(value))
                    has_mile_markers = True
                if field in {"eta", "forecastHour"} and isinstance(value, str):
                    _add_numbers_from_datetime(numbers, value)
        if has_mile_markers:
            _add_number(numbers, mile_marker_sum)

    _add_number(numbers, total_checkpoints)
    for value in mile_field_sums.values():
        _add_number(numbers, value)
    return numbers


def _add_to_sum(sums, field, value):
    try:
        sums[field] = sums.get(field, Decimal(0)) + Decimal(str(value))
    except InvalidOperation:
        return


def _add_numbers_from_datetime(numbers, value):
    for match in _PLAN_NUMBER_PATTERN.finditer(value):
        try:
            _add_number(numbers, Decimal(match.group().replace(",", "")))
        except InvalidOperation:
            continue


def _add_number(numbers, value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return
    if not number.is_finite():
        return
    numbers.add(number.normalize())
    numbers.add(number.quantize(Decimal("1"), rounding=ROUND_HALF_UP).normalize())
    numbers.add(number.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP).normalize())
