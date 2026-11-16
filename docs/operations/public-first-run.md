# First run / 首次运行

Run from a source checkout. Commands below always use a separate `work/public-preview` instance; replace that path consistently if it already exists. Never point a demo at an existing personal instance.

## 1. Requirements

- Python 3.9+ with SQLite 3.37+, JSON functions and FTS5.
- A Unix-style environment for the full process runtime; some candidate-sandbox features are currently macOS-specific.
- A browser. A model is optional for panel preview.

No runtime Python packages need downloading for the preview. From the repository directory:

```sh
python3 -c 'import sqlite3; c=sqlite3.connect(":memory:"); print(sqlite3.sqlite_version); print(c.execute("select json_valid(?)", ("{}",)).fetchone()); c.execute("create virtual table probe using fts5(content)")'
```

If your Python bundles an older SQLite, use a Python build with a compatible SQLite; the system's separate `sqlite3` command does not determine Python's SQLite version.

## 2. Locked preview, no model calls

```sh
python3 -m digital_life --data work/public-preview prepare
python3 scripts/development/install_accounts.py --data work/public-preview --install
python3 -m digital_life --data work/public-preview check
python3 -m digital_life --data work/public-preview serve --port 18766
```

Open <http://127.0.0.1:18766/>. Set the initial root password locally, then inspect the empty panel. Nothing has been woken; a queued message will not be processed by itself. Ctrl+C closes this foreground panel.

账户安装是显式步骤；不能直接省略后宣称新实例已有账户登录。该步骤仅用于这里新建、停止中的原生实例，不适用于严格 schema4 实例。

## 3. Optional conversation using your own Ollama service

This step requires an already installed, running Ollama service and a model you have selected and downloaded yourself. It can incur substantial local compute; other providers may charge per call. This guide does not install a model or silently switch providers.

Copy the template, then edit `model` to the installed model identifier and review its limits:

```sh
mkdir -p config/local
cp config/examples/llm/ollama.example.json config/local/public-demo-ollama.json
```

Close the preview panel first. Keep the instance stopped while configuring:

```sh
python3 -m digital_life --data work/public-preview configure-model config/local/public-demo-ollama.json --offline
python3 -m digital_life --data work/public-preview cognition enable
python3 -m digital_life --data work/public-preview people-relations enable
```

These commands save configuration, not inference. The model name in the template is an example, not an assertion that it is available or suitable for every device.

Start the instance and panel explicitly:

```sh
python3 manage.py --data work/public-preview start --port 18766 --open
```

Confirm the displayed demo path, then enter **`WAKE public-preview`** when prompted. Keep the terminal open. A started runner can process messages; deployment acceptance may also call a model if that gate is enabled. Review the model and budget before this step.

Use the root account for this preview. Ordinary accounts do not yet support every global life feature. The default tool policy is retained; this guide does not grant source-code writes, enable autonomous exploration or personality growth.

For cleanup, stop the running foreground command and confirm the demo process is gone. You can record a stop and lock explicitly:

```sh
python3 manage.py --data work/public-preview lock
```

Do not delete an instance that is still running or that contains information you want to preserve.

## Other providers and current limits

See [model configuration](llm-configuration.md) for the local llama.cpp and remote-compatible adapters. Review secrets, limits and output contracts for your provider.

Codex device authorization has its own [configuration guide](codex-configuration.md). New Codex post-usage startup requires a strict schema4 instance, while the current account adapter is limited to native instances. **Do not combine this native panel recipe with a strict Codex setup and assume it has been validated as an end-to-end public quickstart.** That integration remains a release limitation; use the validated native preview above first.

The project does not ship credentials, model weights or the maintainer's identity and memory. Your fresh instance will not inherit the maintainer's personality or history.
