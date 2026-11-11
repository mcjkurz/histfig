"""Finding and stopping an earlier HistFig that still holds the port.

A running server records itself in <data_dir>/histfig.pid ({"pid": ..., "port": ...})
and removes the file when it exits. If the port is busy at start-up and that file
names a live process on the same port, the CLI can offer to stop it — typically a
HistFig that was suspended with Ctrl+Z or left running in another window.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from pathlib import Path


def pid_path(data_dir: Path) -> Path:
    return data_dir / "histfig.pid"


def port_free(host: str, port: int) -> bool:
    """Can a server listen here? Checked the way uvicorn binds, so connections that are
    still closing after a restart (TIME_WAIT) don't count as "in use"."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sys.platform != "win32":  # on Windows this option would even allow stealing a port in use
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def write_pid(data_dir: Path, port: int) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    pid_path(data_dir).write_text(json.dumps({"pid": os.getpid(), "port": port}), encoding="utf-8")


def remove_pid(data_dir: Path) -> None:
    """Remove the PID file, but only if it is ours (a newer server may have replaced it)."""
    try:
        if json.loads(pid_path(data_dir).read_text(encoding="utf-8")).get("pid") == os.getpid():
            pid_path(data_dir).unlink()
    except (OSError, ValueError, AttributeError):
        pass


def alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # os.kill(pid, 0) would *terminate* the process on Windows; ask the OS instead.
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, but belongs to someone else
    return True


def previous_server(data_dir: Path, port: int) -> int | None:
    """PID of an earlier HistFig for this data folder on this port, if it is still alive."""
    try:
        info = json.loads(pid_path(data_dir).read_text(encoding="utf-8"))
        pid = int(info["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if pid == os.getpid() or info.get("port") != port or not alive(pid):
        return None
    return pid


def stop(pid: int, host: str, port: int, timeout: float = 5.0) -> bool:
    """Stop the process politely, then forcefully; True once the port is free again."""
    if sys.platform == "win32":
        os.kill(pid, signal.SIGTERM)  # TerminateProcess
    else:
        os.kill(pid, signal.SIGTERM)
        os.kill(pid, signal.SIGCONT)  # a suspended (Ctrl+Z) process only sees SIGTERM once resumed
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not alive(pid) and port_free(host, port):
            return True
        time.sleep(0.2)
    if sys.platform != "win32" and alive(pid):
        os.kill(pid, signal.SIGKILL)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if port_free(host, port):
            return True
        time.sleep(0.2)
    return port_free(host, port)
