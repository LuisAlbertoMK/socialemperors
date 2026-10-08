"""The opt-in command capture used to recover undocumented wire formats.

``SE_CAPTURE=<path>`` makes every decoded command batch land in a JSONL file, so
a real client session can be turned into evidence instead of guesses.
"""

import json

import pytest

import sessions
from constants import Constant

COMMAND_URL = (
    "/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/command.php"
)


@pytest.fixture
def user(tmp_path, monkeypatch):
    saves = tmp_path / "saves"
    saves.mkdir()
    monkeypatch.setattr(sessions, "SAVES_DIR", str(saves))
    userid = sessions.new_village()
    yield userid
    sessions.__saves.pop(userid, None)


def post(client, userid, commands):
    payload = {
        "ts": 1700000000,
        "first_number": 7,
        "accessToken": "token",
        "tries": 0,
        "publishActions": 0,
        "commands": commands,
    }
    return client.post(
        COMMAND_URL,
        data={"USERID": userid, "data": "0" * 64 + ";" + json.dumps(payload)},
    )


def test_capture_records_the_raw_envelope_verbatim(tmp_path, monkeypatch, client, user):
    """The original bytes are the evidence: re-serialising can reorder or retype."""
    capture_file = tmp_path / "commands.jsonl"
    monkeypatch.setenv("SE_CAPTURE", str(capture_file))
    envelope = "0" * 64 + ';{"ts":1,"commands":[]}'

    client.post(COMMAND_URL, data={"USERID": user, "data": envelope})

    record = json.loads(capture_file.read_text(encoding="utf-8").splitlines()[-1])
    assert record["raw"] == envelope


def test_an_unusable_envelope_is_still_captured(tmp_path, monkeypatch, client, user):
    """A rejected payload is exactly what needs studying when the format is unknown."""
    capture_file = tmp_path / "commands.jsonl"
    monkeypatch.setenv("SE_CAPTURE", str(capture_file))

    client.post(COMMAND_URL, data={"USERID": user, "data": "garbage-with-no-separator"})

    record = json.loads(capture_file.read_text(encoding="utf-8").splitlines()[-1])
    assert record["raw"] == "garbage-with-no-separator"
    assert record["payload"] is None


def test_capture_records_the_decoded_batch(tmp_path, monkeypatch, client, user):
    capture_file = tmp_path / "captured" / "commands.jsonl"
    capture_file.parent.mkdir()
    monkeypatch.setenv("SE_CAPTURE", str(capture_file))

    response = post(client, user, [{"cmd": Constant.CMD_NAME_MAP, "args": [0, "Renamed"]}])

    assert response.status_code == 200
    records = [json.loads(line) for line in capture_file.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["userid"] == user
    # The whole payload is kept: the envelope fields are part of the wire format
    # that must be recovered, not only the command list.
    assert records[-1]["payload"]["commands"] == [
        {"cmd": Constant.CMD_NAME_MAP, "args": [0, "Renamed"]}
    ]
    assert records[-1]["payload"]["ts"] == 1700000000
    assert records[-1]["payload"]["publishActions"] == 0


def test_capture_appends_one_line_per_batch(tmp_path, monkeypatch, client, user):
    capture_file = tmp_path / "commands.jsonl"
    monkeypatch.setenv("SE_CAPTURE", str(capture_file))

    post(client, user, [{"cmd": Constant.CMD_GAME_STATUS, "args": ["a"]}])
    post(client, user, [{"cmd": Constant.CMD_GAME_STATUS, "args": ["b"]}])

    lines = capture_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert "a" in lines[0] and "b" in lines[1]


def test_no_capture_file_is_written_when_the_variable_is_absent(
    tmp_path, monkeypatch, client, user
):
    monkeypatch.delenv("SE_CAPTURE", raising=False)

    post(client, user, [{"cmd": Constant.CMD_GAME_STATUS, "args": ["x"]}])

    assert list(tmp_path.glob("*.jsonl")) == []


def test_capture_creates_the_target_directory_when_missing(
    tmp_path, monkeypatch, client, user
):
    capture_file = tmp_path / "not-created-yet" / "deep" / "commands.jsonl"
    monkeypatch.setenv("SE_CAPTURE", str(capture_file))

    post(client, user, [{"cmd": Constant.CMD_GAME_STATUS, "args": ["x"]}])

    assert capture_file.exists()


def test_an_unwritable_capture_path_never_breaks_the_game(
    tmp_path, monkeypatch, client, user
):
    """Instrumentation must not turn a healthy session into a failed command."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SE_CAPTURE", str(blocker / "commands.jsonl"))

    response = post(client, user, [{"cmd": Constant.CMD_GAME_STATUS, "args": ["x"]}])

    assert response.status_code == 200


def test_a_malformed_command_is_still_captured(tmp_path, monkeypatch, client, user):
    """The rejected-but-received payload is exactly what needs capturing."""
    capture_file = tmp_path / "commands.jsonl"
    monkeypatch.setenv("SE_CAPTURE", str(capture_file))

    post(
        client,
        user,
        [{"cmd": Constant.CMD_BUY, "args": []}, {"cmd": Constant.CMD_GAME_STATUS, "args": []}],
    )

    records = [json.loads(line) for line in capture_file.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["payload"]["commands"][0] == {"cmd": Constant.CMD_BUY, "args": []}
