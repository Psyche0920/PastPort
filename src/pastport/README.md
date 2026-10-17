# PastPort package entry points

The package composes a typed editorial workflow with a shared JS runtime. [Root README](../../README.md) indexes every logical module; [the current guide](../../docs/README.md) owns startup, interfaces, operations and checks. Owner: Wehan/Weijia. Imports must not configure logging, start a service or grant approval.

| File | Purpose |
|---|---|
| [__init__.py](__init__.py) | Package namespace. |
| [__main__.py](__main__.py) | Start one authenticated local editorial service. |
| [contracts.py](contracts.py) | Public schema registry; versions and wire names are part of the compatibility contract. |
| [observability.py](observability.py) | Application-owned JSON diagnostics; never a business audit or payload dump. |
| [py.typed](py.typed) | PEP 561 marker declaring this package typed. |

The CLI owns safe logging; embedding requires explicit configuration. Keep these current file descriptions with the implementation; no historical change records are required.
