"""Concurrency contract for the in-memory village state.

``server.py`` runs the dev server with ``threaded=True``, and a command batch is
a read-modify-write over the very dictionaries that ``save_session`` serializes.
Two things must therefore hold:

1. A save in progress must exclude concurrent mutation, otherwise ``json.dump``
   can raise ``RuntimeError: dictionary changed size during iteration`` or write
   a half-applied village.
2. Concurrent command batches on the same village must not corrupt the save.
"""

import json
import threading

import command as command_module
import sessions
from constants import Constant


def payload_for(commands):
    """The parsed payload ``command()`` receives, after the route decodes it."""
    return {
        "ts": 0,
        "first_number": 0,
        "accessToken": "token",
        "tries": 0,
        "publishActions": 0,
        "commands": commands,
    }


def envelope_for(commands):
    """The wire form: a 64-char digest, a separator, then the JSON payload."""
    return "0" * 64 + ";" + json.dumps(payload_for(commands))


RENAME = [{"cmd": Constant.CMD_NAME_MAP, "args": ["0", "Mutated"]}]
GAME_STATUS = [{"cmd": Constant.CMD_GAME_STATUS, "args": ["ok"]}]
COMMAND_URL = (
    "/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/command.php"
)


def test_command_waits_for_an_in_progress_save(monkeypatch, user):
    """A mutator must not enter the state while a save is serializing it.

    ``json.dump`` is blocked on purpose so the two threads are guaranteed to
    overlap; the mutator is only allowed through once the dump is released.
    """
    dump_entered = threading.Event()
    release_dump = threading.Event()
    mutation_finished = threading.Event()
    errors = []
    real_dump = json.dump
    calls = {"count": 0}

    def blocking_dump(obj, file, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            dump_entered.set()
            release_dump.wait(timeout=10)
        return real_dump(obj, file, **kwargs)

    monkeypatch.setattr(sessions.json, "dump", blocking_dump)

    saver = threading.Thread(target=sessions.save_session, args=(user,))
    saver.start()
    assert dump_entered.wait(timeout=10), "save never reached json.dump"

    def mutate():
        try:
            command_module.command(user, payload_for(RENAME))
        except BaseException as error:  # reported by the assertion below
            errors.append(error)
        finally:
            mutation_finished.set()

    mutator = threading.Thread(target=mutate)
    mutator.start()

    blocked = not mutation_finished.wait(timeout=0.5)

    release_dump.set()
    saver.join(timeout=10)
    mutator.join(timeout=10)

    assert blocked, "a command mutated state while a save was serializing it"
    assert errors == []
    assert mutation_finished.is_set(), "the mutator never completed after the save"

    with open(f"{sessions.SAVES_DIR}/{user}.save.json", encoding="utf-8") as handle:
        saved = json.load(handle)
    assert saved["playerInfo"]["map_names"][0] == "Mutated"


def test_concurrent_command_batches_keep_the_save_valid(client, user, tmp_path):
    """Four threads hammering the same village must still leave a valid save."""
    errors = []
    save_file = tmp_path / f"{user}.save.json"

    def worker():
        try:
            with client.application.test_client() as local_client:
                for _ in range(10):
                    response = local_client.post(
                        COMMAND_URL,
                        data={"USERID": user, "data": envelope_for(GAME_STATUS + RENAME)},
                    )
                    assert response.status_code == 200, response.get_data()[:200]
        except Exception as error:  # collected for the assertion below
            errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    with open(save_file, encoding="utf-8") as handle:
        saved = json.load(handle)
    assert saved["playerInfo"]["map_names"][0] == "Mutated"


def test_state_lock_is_reentrant():
    """Nested acquisition is required: command() holds it across nested calls."""
    with sessions.state_lock, sessions.state_lock:
        assert True
