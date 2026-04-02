# copperbot

**TUK001** — a [CopperHead](https://github.com/BethanyJep/copperhead-server) Snake tournament bot (WebSocket client).

## Setup

```bash
python3 -m pip install -r requirements.txt
```

## Run (against a local server)

1. Start [CopperHead Server](https://github.com/BethanyJep/copperhead-server) on port `8765`.
2. Run the bot:

```bash
python3 tuk001.py --server ws://localhost:8765/ws/ --skip-wait --difficulty 8
```

Options: `--name`, `--difficulty` (1–10), `--quiet`, `--skip-wait`.

## Strategy (summary)

BFS toward food, flood-fill when blocked, center-weighted positioning, difficulty-scaled head-on handling vs the opponent’s predicted head.

## License

MIT (see SPDX header in `tuk001.py`).
