import json
import os
import threading

# Request-scoped logging is disabled by default to avoid synchronous console
# I/O on every request (especially slow on Windows). Enable with SE_VERBOSE=1.
VERBOSE = os.environ.get("SE_VERBOSE", "0") not in ("", "0", "false", "False")

_capture_lock = threading.Lock()


def log(*args, **kwargs):
    """Drop-in replacement for print() used on hot request paths."""
    if VERBOSE:
        print(*args, **kwargs)


def capture(record: dict) -> None:
    """Append one decoded client payload to the file named by ``SE_CAPTURE``.

    Opt-in instrumentation for recovering wire formats that are documented
    nowhere: point SE_CAPTURE at a file, reproduce the action in the client, and
    the exact payload the client sent ends up on disk. The variable is read on
    every call so it can be switched without restarting the interpreter, and a
    failure here must never fail the command it was observing.
    """
    path = os.environ.get("SE_CAPTURE")
    if not path:
        return
    try:
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with _capture_lock, open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception as error:  # instrumentation must never break the game
        log(f"[WARN] capture failed: {error!r}")
