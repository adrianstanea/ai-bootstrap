---
name: python-like-rust
description: Use when writing or reviewing Python that returns raw tuples, dicts or Optional values, passes interchangeable ids or paths as plain str/int, models alternatives with Optional fields, or documents call-order rules in a class docstring. Covers type-checked data modelling with dataclasses, NewType, unions and one type per state.
user-invocable: true
---

# Python Like Rust

Move invariants out of comments and into types the checker verifies. Apply this when writing or
reviewing Python, mainly at library boundaries. It works with Python 3.12 and needs no library.

## Quick reference

| Smell in the diff                                                       | Replace with                                            |
| ----------------------------------------------------------------------- | ------------------------------------------------------- |
| `-> tuple[str, str, int]`, `-> dict[str, Any]`                          | a frozen dataclass with named fields                    |
| Two `str` or `int` parameters that must not be swapped                  | `NewType` per meaning                                   |
| One class with `Optional` fields filled in only for some cases          | a union of dataclasses, handled with `match`            |
| `__init__` with optional arguments whose valid combinations are unclear | named classmethod constructors                          |
| Docstring says "call X before Y"                                        | one class per state, each method returns the next state |
| `-> Foo \| None` where `None` hides several reasons                     | a result type, or raise a specific exception            |

## Name the result

```python
# Before: the caller must remember what the three strings mean.
def find_target(name: str) -> tuple[str, str, str]: ...

# After: self-documenting and checkable.
@dataclass(frozen=True, slots=True)
class Target:
    name: str
    board: str
    arch: str

def find_target(name: str) -> Target: ...
```

Make dataclasses `frozen=True, slots=True` unless the value is built up incrementally. Put
validation in a `parse` or `from_*` classmethod that returns only valid values, so a held `Target`
is always well formed.

## Give identifiers their own type

```python
from typing import NewType

PackageName = NewType("PackageName", str)
TargetName = NewType("TargetName", str)

def resolve(package: PackageName, target: TargetName) -> Target: ...

resolve(target_name, package_name)  # mypy: incompatible argument types
```

Use `NewType` where two values share a representation but are never interchangeable: ids, names
from different namespaces, units, raw versus normalised text. Convert once at the boundary
(`PackageName(raw)`), then pass the typed value inward.

## Alternatives as a union

```python
@dataclass(frozen=True, slots=True)
class LocalSource:
    path: Path

@dataclass(frozen=True, slots=True)
class GitSource:
    url: str
    revision: str

Source = LocalSource | GitSource

def describe(source: Source) -> str:
    match source:
        case LocalSource(path):
            return f"path {path}"
        case GitSource(url, revision):
            return f"{url}@{revision}"
```

Add `typing.assert_never(source)` in a final `case _:` so the checker reports an unhandled variant when
the union grows.

## One type per state

```python
class Draft:
    def validate(self) -> Validated: ...  # the only way forward

class Validated:
    def write(self, path: Path) -> None: ...  # not callable on a Draft
```

If a docstring lists ordering rules ("do not call `write` before `validate`"), split the class by
state. The method set of each class is the rule, and mypy enforces it.

## Named constructors and `Self`

Prefer `Rectangle.from_corners(...)` and `Rectangle.from_origin_and_size(...)` over one `__init__`
with optional arguments. Annotate methods that return a modified copy with `typing.Self` so
subclasses keep their own type.

## Boundaries with a project

- Follow the project's error-handling convention; absent one, use exceptions with specific types. Do not add the `returns` library or a
  home-made `Result`; when `None` is the only failure, `Foo | None` is fine.
- Where the project keeps a standard-library-only core, use only the standard library there;
  validate external input at the boundary (for example with pydantic models), which then hands
  out these dataclasses.

## Common mistakes

- Using `NewType` for values that are interchangeable, which only adds casts.
- Returning a mutable dataclass from a function others cache.
- Leaving `Any` in a signature to silence mypy; fix the type instead.
- Wrapping every `str` in a `NewType`; keep it for values that can be confused.

## Provenance

The ideas follow Kobzol's blog post "Writing Python like it's Rust" (kobzol.github.io, 2023). The
text and examples here are original to this repository.

## Limitations

- Typing guidance only; it does not configure mypy or pyright, and it adds no runtime validation
  (use pydantic at external boundaries).
