# Contributing to AI Assistant with Memory

[项目介绍](README.zh-CN.md) · [English overview](README.md)

Small, focused contributions are welcome: a clearer setup guide, a reproducible bug fix, a model adapter, or a documented improvement to memory and cognition. Open an issue before proposing a large architecture change.

## Local development

Use Python 3.9+ with SQLite 3.37+ and JSON/FTS5 support. Runtime Python dependencies are standard-library only. Work from a source checkout; packaging needs setuptools and wheel.

Start with these offline checks:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_architecture tests.test_chat tests.test_codex_post_usage
node scripts/verification/verify_thought_inspection_ui.mjs
```

Node.js 22+ is used for the component checks. A complete regression run takes considerably longer:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

Run through a normal module or script entry point, not a stdin wrapper: some tests use multiprocessing spawn. Tests need temporary local ports and child processes. Platform-specific tests and explicit local-model tests may be skipped; report skips instead of claiming they passed. Never enable real-model tests or run trial scripts without a configured model and an explicit budget.

## Changes

- Keep domain rules independent of runtime, storage and providers.
- Preserve independent model calls, source verification, permission checks and durable identity/history.
- For schema changes, update the maintained generator, SQL resources and documentation together. New-instance DDL is not an upgrade procedure.
- Do not regenerate frozen research hashes merely to silence a failure. Explain and record material revisions separately from past experimental results.
- Use a new temporary instance for validation; never modify or wake someone else's instance.
- Add focused tests for behavior changes. Documentation-only changes need link and command checks, not a full system run.

## Pull requests

Describe the problem, resulting behavior, validation and any remaining limitations. Include the applicable platform, commands and pass/fail/skip counts. Use synthetic examples; exclude credentials, personal conversations, database files, local paths and model input dumps.

Be considerate when reviewing other contributors' work. Contributions are made under the project's [MIT license](LICENSE); preserve notices for any third-party material.
