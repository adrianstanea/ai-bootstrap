# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""A minimal stand-in for `dataclasses.dataclass`.

Importing `dataclasses` pulls in `inspect` and costs tens of milliseconds, which dominates the
per-tool-call hooks. This supports only what the package uses: annotated fields in order,
plain or `factory(...)` defaults, keyword or positional construction, `eq`, `repr`, `frozen`.
"""

from __future__ import annotations

_REQUIRED = object()


class factory:
    """Marks a default that must be created per instance (a mutable value)."""

    def __init__(self, make):
        self.make = make


def record(cls=None, *, frozen: bool = False):
    def wrap(klass):
        names = list(klass.__dict__.get("__annotations__", {}))
        defaults = {n: klass.__dict__.get(n, _REQUIRED) for n in names}
        for name, value in defaults.items():
            if value is not _REQUIRED and not isinstance(value, factory):
                setattr(klass, name, value)
            elif name in klass.__dict__:
                delattr(klass, name)

        def __init__(self, *args, **kwargs):
            if len(args) > len(names):
                raise TypeError(f"{klass.__name__} takes at most {len(names)} arguments")
            values = dict(zip(names, args))
            for key, value in kwargs.items():
                if key not in defaults or key in values:
                    raise TypeError(f"{klass.__name__}: bad argument {key!r}")
                values[key] = value
            for name in names:
                if name not in values:
                    default = defaults[name]
                    if default is _REQUIRED:
                        raise TypeError(f"{klass.__name__} missing argument {name!r}")
                    values[name] = default.make() if isinstance(default, factory) else default
                object.__setattr__(self, name, values[name])

        def __repr__(self):
            body = ", ".join(f"{n}={getattr(self, n)!r}" for n in names)
            return f"{klass.__name__}({body})"

        def __eq__(self, other):
            if other.__class__ is not self.__class__:
                return NotImplemented
            return all(getattr(self, n) == getattr(other, n) for n in names)

        def __setattr__(self, name, value):
            raise AttributeError(f"cannot assign to field {name!r}")

        klass.__init__ = __init__
        klass.__repr__ = __repr__
        klass.__eq__ = __eq__
        klass.__hash__ = (lambda self: hash(tuple(getattr(self, n) for n in names))) if frozen else None
        if frozen:
            klass.__setattr__ = __setattr__
        return klass

    return wrap if cls is None else wrap(cls)
