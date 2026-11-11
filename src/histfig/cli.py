"""Command line: `histfig [serve]`, `histfig setup`, `histfig doctor`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import threading
import webbrowser
from pathlib import Path

from histfig.config import Config, config_path, default_data_dir, load_config, save_config


async def check_models(cfg) -> bool:
    """Send one tiny request to each configured model and print the outcome."""
    from histfig.providers.chat import ChatProvider
    from histfig.providers.embed import make_embedder

    ok = True
    print(f"Chat:      {cfg.chat.provider} {cfg.chat.model} @ {cfg.chat.base_url}")
    try:
        reply = await ChatProvider(cfg.chat).complete(
            [{"role": "user", "content": "Reply with the single word: OK"}]
        )
        print(f"  OK — replied {reply.strip()[:60]!r}")
    except Exception as e:
        ok = False
        print(f"  FAILED — {e}")
    print(f"Embedding: {cfg.embedding.provider} {cfg.embedding.model}")
    try:
        vec = await make_embedder(cfg.embedding, key=cfg.embedding_key).embed_query("test")
        print(f"  OK — {len(vec)}-dimensional vectors")
    except Exception as e:
        ok = False
        print(f"  FAILED — {e}")
    return ok


def _setup(data_dir: Path):
    from histfig.wizard import run_wizard

    try:
        cfg = run_wizard(data_dir)
    except (KeyboardInterrupt, EOFError):
        sys.exit("\nSetup cancelled; nothing was saved.")
    print("\nChecking the models…")
    if not asyncio.run(check_models(cfg)):
        print("Fix this with `histfig setup` again, or by editing the config file.")
    return cfg


def _load_or_create(data_dir: Path):
    """The configuration; on the very first run, an empty one that the browser fills in."""
    cfg = load_config(data_dir)
    if cfg is None:
        cfg = Config()
        save_config(cfg, data_dir)
        print("First run: choose your models on the Settings page that opens in your browser.")
        print("(Prefer the terminal? Stop with Ctrl+C and run `histfig setup`.)")
    return cfg


def cmd_setup(args) -> None:
    _setup(args.data_dir)


def cmd_doctor(args) -> None:
    cfg = load_config(args.data_dir)
    if cfg is None:
        sys.exit(f"No configuration at {config_path(args.data_dir)}. Start HistFig, or run `histfig setup`.")
    print(f"Config: {config_path(args.data_dir)}")
    for p in cfg.validate():
        print(f"  ! {p}")
    sys.exit(0 if asyncio.run(check_models(cfg)) else 1)


def _free_port_or_exit(data_dir: Path, host: str, port: int, url: str) -> None:
    """Make sure the port is free; offer to stop an earlier HistFig that holds it."""
    from histfig import running

    if running.port_free(host, port):
        return
    pid = running.previous_server(data_dir, port)
    if pid is not None:
        print(f"HistFig is already running on port {port} (process {pid}).")
        print("It may be in another terminal window, or suspended with Ctrl+Z.")
        answer = "y"
        if sys.stdin.isatty():
            try:
                answer = input("Stop it and start a new one? [Y/n] ").strip().lower() or "y"
            except (EOFError, KeyboardInterrupt):
                answer = "n"
        else:
            answer = "n"
        if answer.startswith("y"):
            print("Stopping it…")
            if running.stop(pid, host, port):
                print("Stopped.")
                return
            sys.exit(f"Could not stop process {pid}. Close the terminal window it runs in, then try again.")
        sys.exit(f"Leaving it running: open {url}")
    sys.exit(
        f"Port {port} is already in use by another program, so HistFig can't start.\n"
        f"  - If HistFig is running elsewhere, just open {url}\n"
        f"  - Or start this one on another port: histfig serve --port {port + 1}"
    )


def cmd_serve(args) -> None:
    cfg = _load_or_create(args.data_dir)
    needs_setup = bool(cfg.validate())
    host = args.host or cfg.server.host
    port = args.port or cfg.server.port

    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}"
    _free_port_or_exit(args.data_dir, host, port, url)

    import uvicorn

    from histfig.server.app import create_app

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = create_app(cfg, args.data_dir, public=args.public)
    open_url = url + "/#/settings" if needs_setup else url
    print(f"\n  HistFig is running at {url}")
    if args.public:
        print(f"  PUBLIC (read-only) mode: visitors can chat but not change anything.\n"
              f"  Their conversations are deleted after {cfg.public.keep_days} days unused; "
              f"limit {cfg.public.messages_per_hour} messages per hour each.")
    print("  To stop it: press Ctrl+C here (or close this terminal window).\n")
    if not args.no_browser and not os.environ.get("CODESPACES"):
        threading.Timer(1.5, lambda: webbrowser.open(open_url)).start()
    from histfig import running

    running.write_pid(args.data_dir, port)
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    finally:
        running.remove_pid(args.data_dir)


def main(argv: list[str] | None = None) -> None:
    # Windows consoles/pipes may use a legacy code page; never crash on a "—".
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(prog="histfig", description="Chat with historical figures, locally.")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="where config, database and uploads live (default: ./data or $HISTFIG_DATA)")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the web app (default)")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    serve.add_argument("--public", action="store_true",
                       help="read-only server to share: visitors can chat, but not change anything")
    sub.add_parser("setup", help="configure in the terminal instead of the browser's Settings page")
    sub.add_parser("doctor", help="check that the configured models respond")

    args = parser.parse_args(argv)
    args.data_dir = (args.data_dir or default_data_dir()).resolve()
    if args.command is None:
        args.command, args.host, args.port, args.no_browser, args.public = "serve", None, None, False, False
    {"serve": cmd_serve, "setup": cmd_setup, "doctor": cmd_doctor}[args.command](args)
