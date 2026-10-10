print (" [+] Loading basics...")
import contextlib
import gzip
import json
import os

if os.name == 'nt':
    os.system("color")
    os.system("title Social Empires Server")
else:
    import sys
    sys.stdout.write("\x1b]2;Social Empires Server\x07")

print (" [+] Loading game config...")
from get_game_config import get_game_config

print (" [+] Loading players...")
from get_player_info import get_neighbor_info, get_player_info
from sessions import (
    all_saves_info,
    all_saves_userid,
    fb_friends_str,
    load_saved_villages,
    neighbor_session,
    new_village,
    save_info,
)

load_saved_villages()

print (" [+] Loading server...")
from flask import (
    Flask,
    Response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
)

from bundle import ASSETS_DIR, BASE_DIR, STUB_DIR, TEMPLATES_DIR
from command import command, do_command
from constants import Constant
from engine import timestamp_now
from logger import capture, log
from quests import get_quest_map
from version import version_name

host = '0.0.0.0'
port = 5050

app = Flask(__name__, template_folder=TEMPLATES_DIR)
# Session signing key, available outside __main__ so `flask run` and the test
# client can use session-backed routes. Override with SE_SECRET_KEY for anything
# that is not a single-player local install.
app.secret_key = os.environ.get("SE_SECRET_KEY", "SECRET_KEY")
# Let the browser cache the (immutable) game assets to cut repeat requests.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 3600

def _server_ip() -> str:
    # Use the host the client actually connected to, so devices on the LAN
    # get the PC's LAN IP instead of 127.0.0.1 (which would point to themselves).
    return request.host.rsplit(':', 1)[0]


def _param(name: str, default=None):
    """Read a client-supplied value without raising BadRequestKeyError.

    The Flash client treats an error page as a fatal desync, so a missing
    parameter must reach the handler as an absent value it can reason about.
    """
    return request.values.get(name, default)


def _int_param(name: str, default=None):
    """Read an integer parameter, tolerating absence and malformed values."""
    raw = _param(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        log(f"[WARN] ignoring non-numeric parameter {name}={raw!r}")
        return default


def _json_error(reason: str, status: int = 400):
    """Answer a misbehaving client in the game's protocol, not with an HTML page."""
    log(f"[ERROR] {reason}")
    return Response(
        json.dumps({"result": "error", "reason": reason}),
        status=status,
        mimetype="application/json",
    )


def _download_asset(url: str, destination: str) -> bool:
    """Fetch one missing asset from the original CDN. True when it was stored.

    ``urllib.request`` is imported here rather than at module scope: it costs
    about 130 ms of the server's startup, and this path only runs for assets that
    are neither bundled nor already cached locally.
    """
    import urllib.request

    directory = os.path.dirname(destination)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
    try:
        with urllib.request.urlopen(url, timeout=30) as response, \
                open(destination, "wb") as out_file:
            out_file.write(response.read())
    except OSError:
        # URLError and HTTPError are both OSError subclasses. Never leave a
        # partial file behind: it would be served from cache as a corrupt asset.
        with contextlib.suppress(OSError):
            os.remove(destination)
        return False
    return True

print (" [+] Configuring server routes...")

##########
# ROUTES #
##########

## PAGES AND RESOURCES

@app.route("/", methods=['GET', 'POST'])
def login():
    # Log out previous session
    session.pop('USERID', default=None)
    session.pop('GAMEVERSION', default=None)
    # NOTE: saves are loaded once at startup. Reloading all files here on
    # every request blocks the dev server with disk I/O.
    # If logging in, set session USERID, and go to play
    if request.method == 'POST':
        session['USERID'] = request.form['USERID']
        session['GAMEVERSION'] = request.form['GAMEVERSION']
        log("[LOGIN] USERID:", request.form['USERID'])
        log("[LOGIN] GAMEVERSION:", request.form['GAMEVERSION'])
        return redirect("/play.html")
    # Login page
    if request.method == 'GET':
        saves_info = all_saves_info()
        return render_template("login.html", saves_info=saves_info, version=version_name)

@app.route("/play.html")
def play():
    log(session)

    if 'USERID' not in session:
        return redirect("/")
    if 'GAMEVERSION' not in session:
        return redirect("/")

    if session['USERID'] not in all_saves_userid():
        return redirect("/")
    
    USERID = session['USERID']
    GAMEVERSION = session['GAMEVERSION']
    log("[PLAY] USERID:", USERID)
    log("[PLAY] GAMEVERSION:", GAMEVERSION)
    return render_template("play.html", save_info=save_info(USERID), serverTime=timestamp_now(), friendsInfo=fb_friends_str(USERID), version=version_name, GAMEVERSION=GAMEVERSION, SERVERIP=_server_ip())

@app.route("/ruffle.html")
def ruffle():
    log(session)

    if 'USERID' not in session:
        return redirect("/")
    if 'GAMEVERSION' not in session:
        return redirect("/")

    if session['USERID'] not in all_saves_userid():
        return redirect("/")
    
    USERID = session['USERID']
    GAMEVERSION = session['GAMEVERSION']
    log("[RUFFLE] USERID:", USERID)
    log("[RUFFLE] GAMEVERSION:", GAMEVERSION)
    return render_template("ruffle.html", save_info=save_info(USERID), serverTime=timestamp_now(), version=version_name, GAMEVERSION=GAMEVERSION, SERVERIP=_server_ip())


@app.route("/new.html")
def new():
    session['USERID'] = new_village()
    session['GAMEVERSION'] = "SocialEmpires0926bsec.swf"
    return redirect("play.html")

@app.route("/crossdomain.xml")
def crossdomain():
    return send_from_directory(STUB_DIR, "crossdomain.xml")

@app.route("/img/<path:path>")
def images(path):
    return send_from_directory(TEMPLATES_DIR + "/img", path)

@app.route("/css/<path:path>")
def css(path):
    return send_from_directory(TEMPLATES_DIR + "/css", path)

## GAME STATIC


@app.route("/default01.static.socialpointgames.com/static/socialempires/swf/05122012_projectiles.swf")
def similar_05122012_projectiles():
    return send_from_directory(ASSETS_DIR + "/swf", "20130417_projectiles.swf")

@app.route("/default01.static.socialpointgames.com/static/socialempires/swf/05122012_magicParticles.swf")
def similar_05122012_magicParticles():
    return send_from_directory(ASSETS_DIR + "/swf", "20131010_magicParticles.swf")

@app.route("/default01.static.socialpointgames.com/static/socialempires/swf/05122012_dynamic.swf")
def similar_05122012_dynamic():
    return send_from_directory(ASSETS_DIR + "/swf", "120608_dynamic.swf")

@app.route("/default01.static.socialpointgames.com/static/socialempires/<path:path>")
def static_assets_loader(path):
    download_dir = os.path.join(BASE_DIR, "download_assets", "assets")
    bundled_path = os.path.join(ASSETS_DIR, path)
    cached_path = os.path.join(download_dir, path)

    if os.path.exists(bundled_path):
        # Use provided asset
        return send_from_directory(ASSETS_DIR, path)

    if os.path.exists(cached_path):
        # Use previously downloaded CDN asset
        log(f"====== USING EXTERNAL: download_assets/assets/{path}")
        return send_from_directory(download_dir, path)

    # Neither bundled nor cached: fetch it from the original CDN.
    URL = f"https://static.socialpointgames.com/static/socialempires/assets/{path}"
    if not _download_asset(URL, cached_path):
        return ("", 404)

    log(f"====== DOWNLOADED ASSET: {URL}")
    return send_from_directory(download_dir, path)

## GAME DYNAMIC

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/track_game_status.php", methods=['POST'])
def track_game_status_response():
    status = _param('status')
    installId = _param('installId')
    user_id = _param('user_id')

    log(f"track_game_status: status={status}, installId={installId}, user_id={user_id}. --", request.values)
    return ("", 200)

_game_config_payloads = None  # (raw bytes, gzipped bytes), built once on demand


def _config_payloads():
    """Serialise the (2 MB) config once, in both encodings.

    Gzip level 6 takes it from 2.01 MB to 0.14 MB, and building both here keeps
    the per-request path to a single lookup, exactly like the cached JSON did.
    The compressed form is cached rather than recomputed per request because the
    client pulls this payload on every reload.
    """
    global _game_config_payloads
    if _game_config_payloads is None:
        raw = json.dumps(get_game_config()).encode("utf-8")
        # One assignment, so a concurrent reader never sees half of the pair.
        _game_config_payloads = (raw, gzip.compress(raw, 6))
    return _game_config_payloads


@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/get_game_config.php", methods=['GET','POST'])
def get_game_config_response():
    # The client also sends user_key, spdebug and language here; the config is
    # identical for everyone, so they are not decoded. This call is part of the
    # client's boot sequence and tolerates a partially formed request.
    USERID = _param('USERID')

    log(f"get_game_config: USERID: {USERID}. --", request.values)

    raw, gzipped = _config_payloads()
    if "gzip" in (request.headers.get("Accept-Encoding") or "").lower():
        response = Response(gzipped, mimetype="application/json")
        response.headers["Content-Encoding"] = "gzip"
    else:
        response = Response(raw, mimetype="application/json")
    # The body depends on Accept-Encoding, so caches must key on it too.
    response.headers["Vary"] = "Accept-Encoding"
    return response

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/get_player_info.php", methods=['POST'])
def get_player_info_response():

    # The client also sends user_key, spdebug, language, a neighbour count and
    # client_id on this call. Only the identity, the requested subject and the map
    # index are needed, so the rest is not decoded.
    USERID = _param('USERID')
    user = _param('user')
    # Default to the player's first map: a missing or malformed index used to
    # reach list indexing with None and raise.
    map_number = _int_param('map', default=0)

    log(f"get_player_info: USERID: {USERID}. user: {user} --", request.values)

    # Current Player
    if user is None:
        if USERID not in all_saves_userid():
            return _json_error(f"unknown USERID: {USERID!r}")
        return (get_player_info(USERID), 200)
    # Arthur
    elif user == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_1 \
    or user == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_2 \
    or user == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_3:
        return (get_neighbor_info(user, map_number), 200)
    # Quest
    elif user.startswith("100000"): # Dirty but quick
        return get_quest_map(user)
    # Neighbor
    else:
        if neighbor_session(user) is None:
            return _json_error(f"unknown neighbour: {user!r}")
        return (get_neighbor_info(user, map_number), 200)

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/sync_error_track.php", methods=['POST'])
def sync_error_track_response():
    # Pure telemetry: never reject the client here, it is already reporting an
    # error. The client sends more fields than are logged (user_key, spdebug,
    # language, current_failed, survival, previous_failed, description,
    # user_id); they are deliberately left undecoded.
    USERID = _param('USERID')
    error = _param('error')
    tries = _param('tries')

    log(f"sync_error_track: USERID: {USERID}. [Error: {error}] tries: {tries}. --", request.values)
    return ("", 200)

@app.route("/null")
def flash_sync_error_response():
    # Recovery route: the client calls it after losing sync. It must never
    # raise, whatever the client sends, because it is already the error path.
    sp_ref_cat = request.values.get('sp_ref_cat')
    reason = {
        "flash_sync_error": "reload On Sync Error",
        "flash_reload_quest": "reload On End Quest",
        "flash_reload_attack": "reload On End Attack",
    }.get(sp_ref_cat, f"unknown sp_ref_cat: {sp_ref_cat!r}")

    log("flash_sync_error", reason, ". --", request.values)
    return redirect("/play.html")

_COMMAND_PAYLOAD_KEYS = ("ts", "first_number", "accessToken", "tries", "publishActions", "commands")


def _parse_command_envelope(data_str: str):
    """Decode ``<64-char digest>;<json payload>`` and validate its shape.

    Returns the payload dict, or None when the client's bytes are unusable. The
    digest is not verified, matching the original backend, which did not either.
    """
    if not isinstance(data_str, str) or len(data_str) < 66 or data_str[64] != ';':
        return None
    try:
        data = json.loads(data_str[65:])
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if any(key not in data for key in _COMMAND_PAYLOAD_KEYS):
        return None
    if not isinstance(data["commands"], list):
        return None
    return data


@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/command.php", methods=['POST'])
def command_response():
    # The client also sends user_key, spdebug, language and client_id here; the
    # envelope is self-describing, so they are not decoded.
    USERID = _param('USERID')

    log(f"command: USERID: {USERID}. --", request.values)

    # Only a save the server actually holds may be mutated. This replaces an
    # assert that vanished under python -O and left the payload unchecked.
    if USERID not in all_saves_userid():
        return _json_error(f"unknown USERID: {USERID!r}")

    data = _parse_command_envelope(_param('data'))
    # Opt-in wire capture (SE_CAPTURE=<path>): both the original bytes and the
    # decoded payload, written before anything can reject it, because an unusable
    # payload is exactly what needs studying while a format is undocumented.
    capture({"userid": USERID, "raw": _param('data'), "payload": data})
    if data is None:
        return _json_error("malformed command envelope")

    command(USERID, data)
    
    return ({"result": "success"}, 200)


@app.route("/mods/collect_all", methods=['POST'])
def mods_collect_all():
    """QoL trigger for CMD_MASS_COLLECT for the logged-in player.

    The stock SWF never sends mass_collect, so this companion endpoint lets
    a web button do in one click what would otherwise be N clicks on N
    buildings. Same math as CMD_COLLECT per building, no readiness invented.
    """
    if 'USERID' not in session:
        return _json_error("not logged in", status=401)
    USERID = session['USERID']
    if USERID not in all_saves_userid():
        return _json_error(f"unknown USERID: {USERID!r}")
    town_id = _int_param('town_id', default=0)
    multiplier = _int_param('multiplier', default=1)
    from sessions import save_session as _save_session
    do_command(USERID, Constant.CMD_MASS_COLLECT, [town_id, multiplier])
    _save_session(USERID)
    return ({"result": "success", "town_id": town_id}, 200)

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/get_continent_ranking.php")
def get_continent_ranking_response():
    # The client sends USERID, worldChange, spdebug, map and user_key here. The
    # response is still a stub (see the ranking gap in the phase-2 document), so
    # none of them is decoded yet.

    # TODO - stub
    response = {
        "world_id": 0,
        "continent": [
            {"posicion": 0, "nivel": 1, "user_id": 1111}, # villages/AcidCaos
            {"posicion": 1, "nivel": 0},
            {"posicion": 2, "nivel": 0},
            {"posicion": 3, "nivel": 0},
            {"posicion": 4, "nivel": 0},
            {"posicion": 5, "nivel": 0},
            {"posicion": 6, "nivel": 0},
            {"posicion": 7, "nivel": 0}
        ]
    }
    return(response)


########
# MAIN #
########

print (" [+] Running server...")

if __name__ == '__main__':
    app.run(host=host, port=port, debug=False, threaded=True)
