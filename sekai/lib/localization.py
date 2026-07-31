import tomllib
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, dataclass_transform, get_args

from sonolus.script.metadata import Locale, encode_localization_text
from sonolus.script.options import Options, options

LOCALIZATION_PATH = Path(__file__).parents[2] / "localization.toml"

LOCALES = frozenset(get_args(Locale.__value__))
OPTION_FIELDS = {"name", "title", "description"}
ENTRY_FIELDS = {"title", "description", "values"}
LOCALIZE_PREFIX = "##LOCALIZE:"


@dataclass_transform(kw_only_default=True)
def localized_options[T](cls: type[T]) -> T | Options:
    """Define options, applying the text in `localization.toml` to them.

    This is used in place of `@options`.
    """
    check_no_inline_text(cls)
    entries = load_option_localization()
    for key, option in class_options(cls):
        apply_localization(option, key, entries.pop(key, None))
    if entries:
        raise ValueError(
            f"{LOCALIZATION_PATH.name} has entries for {sorted(entries)}, which are not options of {cls.__name__}"
        )
    return options(cls)


def load_option_localization() -> dict[str, Any]:
    """Return the `[options]` table of `localization.toml`."""
    data = tomllib.loads(LOCALIZATION_PATH.read_text(encoding="utf-8"))
    unexpected = set(data) - {"options"}
    if unexpected:
        raise ValueError(f"Unexpected tables in {LOCALIZATION_PATH.name}: {sorted(unexpected)}")
    return data.get("options", {})


def class_options(cls: type) -> list[tuple[str, Any]]:
    """Return the name and definition of each option declared in a class."""
    return [(key, value) for key, value in vars(cls).items() if is_option(value)]


def is_option(value: Any) -> bool:
    """Return whether a class attribute is an option definition."""
    return is_dataclass(value) and {field.name for field in fields(value)} >= OPTION_FIELDS


def check_no_inline_text(cls: type):
    """Check that no option localizes its own text, since that comes from `localization.toml`."""
    for key, option in class_options(cls):
        if option.title is not None or option.description is not None:
            raise ValueError(f"{cls.__name__}.{key} sets a title or description directly")
        if any(value.startswith(LOCALIZE_PREFIX) for value in getattr(option, "values", ())):
            raise ValueError(f"{cls.__name__}.{key} localizes a value directly")


def apply_localization(option: Any, key: str, entry: Any):
    """Set the localized text of an option from its `localization.toml` entry, which may be absent."""
    entry = option_entry(key, entry)
    name = option.name or key
    if "title" in entry:
        option.title = localized_text(name, f"{key}.title", entry["title"])
    if "description" in entry:
        option.description = localized_text(name, f"{key}.description", entry["description"])
    if hasattr(option, "values"):
        option.values = value_texts(option, key, entry.get("values", {}))
    elif "values" in entry:
        raise ValueError(f"{key} in {LOCALIZATION_PATH.name} has values, but only a select option has those")


def option_entry(key: str, entry: Any) -> dict[str, Any]:
    """Validate and return an option's entry, treating a missing one as empty."""
    if entry is None:
        return {}
    if not isinstance(entry, dict):
        raise TypeError(f"Expected a table for {key} in {LOCALIZATION_PATH.name}")
    if not entry:
        raise ValueError(f"Empty entry for {key} in {LOCALIZATION_PATH.name}")
    unexpected = set(entry) - ENTRY_FIELDS
    if unexpected:
        raise ValueError(f"Unexpected keys for {key} in {LOCALIZATION_PATH.name}: {sorted(unexpected)}")
    return entry


def value_texts(option: Any, key: str, entry: Any) -> list[str]:
    """Return a select option's encoded values, each given per locale like any other text."""
    location = f"{key}.values"
    if not isinstance(entry, dict):
        raise TypeError(f"Expected a table of values to text for {location} in {LOCALIZATION_PATH.name}")
    unknown = set(entry) - set(option.values)
    if unknown:
        raise ValueError(f"Unknown values for {location} in {LOCALIZATION_PATH.name}: {sorted(unknown)}")
    return [localized_text(value, f"{location}.{value}", entry.get(value)) for value in option.values]


def localized_text(subject: str, location: str, value: Any) -> str:
    """Encode the text given for a title, description, or value into the value of a single option field."""
    standard = is_standard_text(subject)
    if value is None:
        if not standard:
            raise ValueError(f"Missing text for {location} in {LOCALIZATION_PATH.name}")
        return subject
    table = locale_table(value, location)
    if standard:
        return encode_localization_text(table)
    if "en" not in table:
        raise ValueError(f"Missing en text for {location} in {LOCALIZATION_PATH.name}")
    return encode_locale_table(table)


def is_standard_text(text: str) -> bool:
    """Return whether text is a standard text such as `#NOTE_SPEED`, which Sonolus localizes on its own."""
    return text.startswith("#")


def locale_table(value: Any, location: str) -> dict[str, str]:
    """Validate and return a table mapping locale codes to text."""
    if not isinstance(value, dict):
        raise TypeError(f"Expected a table of locales to text for {location} in {LOCALIZATION_PATH.name}")
    if not value:
        raise ValueError(f"Empty table for {location} in {LOCALIZATION_PATH.name}")
    for locale, text in value.items():
        if locale not in LOCALES:
            raise ValueError(
                f"Unknown locale {locale} for {location} in {LOCALIZATION_PATH.name}; expected one of {sorted(LOCALES)}"
            )
        if not isinstance(text, str):
            raise TypeError(f"Expected text for {location}.{locale} in {LOCALIZATION_PATH.name}")
    return value


def encode_locale_table(table: dict[str, str]) -> str:
    """Encode a table of locales to text into the value of a single option field."""
    if set(table) == {"en"}:
        return table["en"]
    return encode_localization_text(table)
