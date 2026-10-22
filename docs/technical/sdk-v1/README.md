# SDK collaboration reference 1.0.0

The authoritative requirements are in [the integrated PRD, technical part](../../PastPort_PRD_EN.md#part-technical). This directory is supporting contract material, not a fourth PRD or a production runtime implementation.

- `sdk-contracts.schema.json`: proposed SDK 1.0.0, plugin API 1.0.0 and runtime wire 0.2.0 definitions. Legacy main wire 0.1.0 is not replaced in production by this file.
- `plugin-api.d.ts`: proposed pure-logic, host control and view interfaces.
- `examples/host-lifecycle.json`: nine synthetic control/attempt examples, not a production host.
- Plugin manifests bind every code/dependency file; the example receipt is explicitly reference-only and cannot approve a production game.
- `examples/game/bundle.json`: self-contained, synthetic offline dependency example. The images are tiny generated color images; they do not demonstrate actual museum matching or style transfer.
- `check_contracts.py`: structural and selected cross-reference checks. Requires Python with `jsonschema`; the existing main development virtual environment has this dependency.
- `check_plugin.mjs`: executable checks for the original synthetic matching plugin; requires Node.js. No browser interaction or main host integration is exercised.

Run from the repository root:

```sh
python docs/technical/sdk-v1/check_contracts.py --owner all
node docs/technical/sdk-v1/check_plugin.mjs
python -m unittest discover -s docs/technical/sdk-v1 -p test_reference_contracts.py -v
```

The Python checker also accepts `--owner wcheung|maslan|wehan` and `--bundle <directory>`. It is an offline reference checker, not the complete production package validator, secure archive importer, licensing audit or code execution sandbox. New production validators and generated types must be implemented in the main repository under the ownership in PRD 2.9.

The fixture's photograph/cartoon flags are explicit. One viewpoint remains photographic, so passing this fixture does not certify a complete cartoon museum. The source text, claims and locations are invented and marked synthetic. Existing native task examples were adapted from main's synthetic reference fixtures.

Checks performed for this documentation delivery: all three owner checks, six negative cases, nine host-control examples, seven entrypoint/integrity/control regression tests, plugin logic lifecycle/rejection checks, strict mypy and Ruff for the reference Python checker, local document links/anchors and schema reference closure. Real IDML extraction, provider calls, browser interaction, mobile capture, production installation/isolation and human playtests were not run.
