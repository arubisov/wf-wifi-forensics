# wf-wifi-forensics

## Local development

```
uv init
uv add ...
uv pip install -e .
uv run wf <command>
```

## Execution

```
uv run wf ingest TEST ~/dev/better_rover/data/input/kismet
uv run wf analyze TEST
uv run wf serve TEST --port 8000
```