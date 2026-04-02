# copperbot

This repository contains:

1. **`copperhead-server/`** — full [CopperHead Server](https://github.com/BethanyJep/copperhead-server) tree (game server, `bot-library/`, docs, tests). Use this directory to run the server locally or deploy.
2. **Root `tuk001.py` + `requirements.txt`** — minimal copy of the **TUK001** bot for a quick run without `cd` into `bot-library/` (same logic as `copperhead-server/bot-library/tuk001.py`).

## Quick start (local)

```bash
python3 -m pip install -r copperhead-server/requirements.txt
python3 copperhead-server/main.py --host 127.0.0.1 --port 8765
```

Another terminal:

```bash
python3 -m pip install -r requirements.txt
python3 tuk001.py --server ws://localhost:8765/ws/ --skip-wait --difficulty 8
```

Or use the copy under `copperhead-server/bot-library/tuk001.py` with the same flags.

## Web client

Open the [CopperHead client](https://revodavid.github.io/copperhead-client/?server=ws%3A%2F%2Flocalhost%3A8765%2Fws%2F) with the server running.

## License

Server and upstream files follow the upstream project; `tuk001.py` is MIT (see SPDX header).
