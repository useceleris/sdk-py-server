from collections.abc import Collection, Iterable
from typing import TypeVar

from pydantic import TypeAdapter, ValidationError
from useceleris_client import ConfigurationError

ParsedValue = TypeVar("ParsedValue")


def validate_input(
    adapter: TypeAdapter[ParsedValue],
    value: object,
    subject: str,
    variant_tags: Collection[str] = (),
) -> ParsedValue:
    """Validates strictly: nothing is coerced, so True is not an int and 1.0
    is not an int."""
    try:
        return adapter.validate_python(value, strict=True)
    except ValidationError as error:
        description = describe_parse_error(subject, error, variant_tags)

    # Raised outside the handler, so the validation error, which holds the
    # input, is not chained to it as context.
    raise ConfigurationError(description)


# end function validate_input


def describe_parse_error(
    subject: str, error: ValidationError, variant_tags: Collection[str] = ()
) -> str:
    """Names every field that failed and the rule it broke. Pydantic's messages
    for the rules used here state the expected type, format or bound, never
    the value. Pydantic also names the variant of a tagged union in the path;
    those tags are left out, so the path is the one the caller wrote."""
    failures = []

    for issue in error.errors(
        include_url=False, include_input=False, include_context=False
    ):
        path = _describe_path(key for key in issue["loc"] if key not in variant_tags)
        rule = issue["msg"]
        failures.append(f"{path}: {rule}." if path else f"{rule}.")

    return f"Invalid {subject}. {' '.join(failures)}"


# end function describe_parse_error


def _describe_path(location: Iterable[int | str]) -> str:
    path = ""

    for key in location:
        if isinstance(key, int):
            path += f"[{key}]"
        else:
            path += f".{key}" if path else key

    return path


# end function _describe_path
