#!/usr/bin/env python3
"""
meshbot.py — MeshCore channel bot for the Fitchburg channel.

Commands:
  !version              — bot version
  !df                   — disk usage
  !uptime               — system uptime
  !top                  — CPU/memory summary
  !wxf [zip]            — weather in °F (default 01420)
  !wxc [zip]            — weather in °C (default 01420)
  !alerts [zip]         — NOAA active weather alerts (default 01420)
  !fitchfact            — random Fitchburg fact
  !hello                — greeting
  !joke                 — random joke
  !quote                — random quote
  !catfact / !dogfact   — animal facts
  !trivia               — general trivia
  !startrek / !starwars — fandom trivia
  !roll [NdN]           — dice roller (e.g. 2d6)
  !remind <min> <msg>   — post a message to channel after N minutes
  !ping                 — PONG!
  !help                 — list commands

Usage:
  python meshbot.py [--port /dev/ttyUSB0] [--baud 115200]
"""

import asyncio
import argparse
import subprocess
import logging
import json
import random
import re
import urllib.request
from datetime import datetime
from pathlib import Path

from meshcore import MeshCore, EventType

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BOT_VERSION = "1.2.0"
DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 115200
TARGET_CHANNEL_NAME = "Fitchburg"
DATA_DIR = Path(__file__).parent / "data"

# ---------------------------------------------------------------------------
# Data loader
# ---------------------------------------------------------------------------

def load_data(filename: str) -> list[str]:
    """Load a list of strings from a line-per-entry text file in data/."""
    path = DATA_DIR / filename
    if not path.exists():
        logging.warning("Data file not found: %s", path)
        return [f"[missing data file: {filename}]"]
    return [line for line in path.read_text().splitlines() if line.strip()]

# ---------------------------------------------------------------------------
# Sync command handlers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Data tables
# ---------------------------------------------------------------------------

# Q-code reference table
Q_CODES = {
    "QRA": "What is the name of your station?",
    "QRB": "How far are you from my station?",
    "QRG": "What is my exact frequency?",
    "QRH": "Does my frequency vary?",
    "QRI": "How is the tone of my transmission?",
    "QRK": "What is the intelligibility of my signals?",
    "QRL": "Are you busy? / I am busy.",
    "QRM": "Are you being interfered with? / Interference from other stations.",
    "QRN": "Are you troubled by static? / Troubled by static.",
    "QRO": "Shall I increase transmitter power?",
    "QRP": "Shall I decrease power? / Low power operation.",
    "QRQ": "Shall I send faster?",
    "QRS": "Shall I send more slowly?",
    "QRT": "Shall I stop sending? / Shutting down.",
    "QRU": "Have you anything for me? / Nothing for you.",
    "QRV": "Are you ready? / I am ready.",
    "QRX": "When will you call again? / Stand by.",
    "QRZ": "Who is calling me?",
    "QSB": "Are my signals fading?",
    "QSK": "Can you hear between my signals? / Break-in operation.",
    "QSL": "Can you acknowledge receipt? / I confirm receipt.",
    "QSO": "Can you communicate with me? / A contact between two stations.",
    "QSP": "Will you relay to another station?",
    "QST": "General call to all amateur stations.",
    "QSX": "Will you listen on another frequency?",
    "QSY": "Shall I change frequency?",
    "QTH": "What is your location? / My location is...",
    "QTR": "What is the exact time?",
}



# Amateur band plan (US)
BAND_PLAN = [
    (1800, 2000, "160m"),
    (3500, 4000, "80m"),
    (5330, 5405, "60m"),
    (7000, 7300, "40m"),
    (10100, 10150, "30m"),
    (14000, 14350, "20m"),
    (18068, 18168, "17m"),
    (21000, 21450, "15m"),
    (24890, 24990, "12m"),
    (28000, 29700, "10m"),
    (50000, 54000, "6m"),
    (144000, 148000, "2m"),
    (222000, 225000, "1.25m"),
    (420000, 450000, "70cm"),
    (902000, 928000, "33cm"),
    (1240000, 1300000, "23cm"),
]



# ---------------------------------------------------------------------------
# Weather helpers (shared by !wxf, !wxc, !alerts)
# ---------------------------------------------------------------------------

def _fetch_wttr(location: str) -> dict:
    url = f"https://wttr.in/{urllib.request.quote(location)}?format=j1"
    req = urllib.request.Request(url, headers={"User-Agent": "meshbot/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

def _get_latlon(zipcode: str) -> tuple[float, float]:
    url = f"https://api.zippopotam.us/us/{zipcode}"
    req = urllib.request.Request(url, headers={"User-Agent": "meshbot/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    place = data["places"][0]
    return float(place["latitude"]), float(place["longitude"])


# ---------------------------------------------------------------------------
# Sync command handlers (alphabetical)
# ---------------------------------------------------------------------------

def cmd_alerts_sync(zipcode: str) -> str:
    """Fetch active NOAA weather alerts for a zip code."""
    try:
        lat, lon = _get_latlon(zipcode)
        url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
        req = urllib.request.Request(url, headers={"User-Agent": "meshbot/1.0", "Accept": "application/geo+json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        features = data.get("features", [])
        if not features:
            return f"No active weather alerts for {zipcode}."
        props = features[0]["properties"]
        event = props.get("event", "Alert")
        headline = props.get("headline") or props.get("description", "")[:100]
        return f"ALERT {event}: {headline}"
    except Exception as exc:
        return f"Alerts lookup failed: {exc}"

def cmd_band(arg="") -> str:
    freq_str = arg.strip().replace(",", "")
    if not freq_str:
        return "Usage: !band <freq in MHz> e.g. !band 146.52"
    try:
        freq_mhz = float(freq_str)
        freq_khz = int(freq_mhz * 1000)
        for lo, hi, name in BAND_PLAN:
            if lo <= freq_khz <= hi:
                return f"{freq_mhz} MHz is in the {name} amateur band."
        return f"{freq_mhz} MHz is not in a US amateur band."
    except ValueError:
        return "Usage: !band <freq in MHz> e.g. !band 146.52"


def cmd_callsign(arg="") -> str:
    call = arg.strip().upper()
    if not call:
        return "Usage: !callsign <call> e.g. !callsign W1AW"
    try:
        url = f"https://callook.info/{urllib.request.quote(call)}/json"
        req = urllib.request.Request(url, headers={"User-Agent": "meshbot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data.get("status") != "VALID":
            return f"{call}: Not found or invalid callsign."
        name = data.get("name", "Unknown")
        addr = data.get("address", {})
        loc = addr.get("line2", "")
        lic_type = data.get("type", "")
        op_class = data.get("current", {}).get("operClass", "")
        cls = f" ({op_class})" if op_class else ""
        return f"{call}{cls}: {name} - {loc} [{lic_type}]"
    except Exception as exc:
        return f"Callsign lookup failed: {exc}"


def cmd_catfact(arg="") -> str:
    return random.choice(load_data("cat_facts.txt"))


def cmd_df(arg="") -> str:
    result = subprocess.run(
        ["df", "-h", "--output=target,size,used,avail,pcent"],
        capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip() if result.returncode == 0 else f"Error: {result.stderr.strip()}"


def cmd_dogfact(arg="") -> str:
    return random.choice(load_data("dog_facts.txt"))


def cmd_fitchfact(arg="") -> str:
    return random.choice(load_data("fitchburg_facts.txt"))


def cmd_futurama(arg="") -> str:
    return random.choice(load_data("futurama_trivia.txt"))


def cmd_hamfact(arg="") -> str:
    return random.choice(load_data("ham_facts.txt"))


def cmd_hello(arg="") -> str:
    return random.choice(load_data("hello_responses.txt"))


def cmd_joke(arg="") -> str:
    return random.choice(load_data("jokes.txt"))


def cmd_lotr(arg="") -> str:
    return random.choice(load_data("lotr_trivia.txt"))


def cmd_onthisday(arg="") -> str:
    try:
        from datetime import datetime
        now = datetime.now()
        url = (f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/"
               f"{now.month}/{now.day}")
        req = urllib.request.Request(url, headers={"User-Agent": "meshbot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        events = data.get("events", [])
        if not events:
            return "No events found for today."
        e = random.choice(events)
        return f"{e['year']}: {e['text']}"
    except Exception as exc:
        return f"On This Day lookup failed: {exc}"

def cmd_prop(arg="") -> str:
    try:
        req = urllib.request.Request(
            "https://services.swpc.noaa.gov/json/f107_cm_flux.json",
            headers={"User-Agent": "meshbot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            sfi_data = json.loads(r.read())
        sfi = sfi_data[-1]["flux"]

        req2 = urllib.request.Request(
            "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
            headers={"User-Agent": "meshbot/1.0"}
        )
        with urllib.request.urlopen(req2, timeout=10) as r:
            kdata = json.loads(r.read())
        kp = float(kdata[-1]["Kp"])

        def band_cond(lo_sfi, hi_sfi, storm_ok=True):
            if kp >= 5 and not storm_ok:
                return "Poor"
            if sfi >= hi_sfi:
                return "Good"
            if sfi >= lo_sfi:
                return "Fair"
            return "Poor"

        return "\n".join([
            f"HF Prop (SFI={sfi:.0f} Kp={kp:.1f}):",
            f"80m={band_cond(70,90)}",
            f"40m={band_cond(80,100)}",
            f"20m={band_cond(100,120)}",
            f"15m={band_cond(120,150)}",
            f"10m={band_cond(150,180)}",
        ])
    except Exception as exc:
        return f"Propagation lookup failed: {exc}"

def cmd_q(arg="") -> str:
    code = arg.strip().upper()
    if not code:
        return "Usage: !q <code> e.g. !q QTH"
    if code in Q_CODES:
        return f"{code}: {Q_CODES[code]}"
    return f"Unknown Q-code: {code}. Try QTH, QSL, QRM, QRP, QRT, QRZ, QSO, QST..."

def cmd_quote(arg="") -> str:
    return random.choice(load_data("quotes.txt"))


def cmd_roll(arg="") -> str:
    spec = arg.strip().lower() or "1d6"
    m = re.fullmatch(r"(\d+)d(\d+)", spec)
    if not m:
        return "Usage: !roll NdN (e.g. !roll 2d6)"
    num, sides = int(m.group(1)), int(m.group(2))
    if num < 1 or num > 20 or sides < 2 or sides > 100:
        return "Roll limits: 1-20 dice, 2-100 sides."
    rolls = [random.randint(1, sides) for _ in range(num)]
    total = sum(rolls)
    detail = "+".join(str(r) for r in rolls) if num > 1 else str(total)
    return f"Roll {spec}: {detail} = {total}" if num > 1 else f"Roll {spec}: {total}"

def cmd_secret(arg="") -> str:
    return random.choice(load_data("secrets.txt"))


def cmd_simpsons(arg="") -> str:
    return random.choice(load_data("simpsons_trivia.txt"))


def cmd_solar(arg="") -> str:
    try:
        req = urllib.request.Request(
            "https://services.swpc.noaa.gov/json/f107_cm_flux.json",
            headers={"User-Agent": "meshbot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            sfi_data = json.loads(r.read())
        sfi = sfi_data[-1]["flux"]

        req2 = urllib.request.Request(
            "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
            headers={"User-Agent": "meshbot/1.0"}
        )
        with urllib.request.urlopen(req2, timeout=10) as r:
            kdata = json.loads(r.read())
        kp = float(kdata[-1]["Kp"])

        if sfi >= 150:
            prop = "Excellent"
        elif sfi >= 120:
            prop = "Good"
        elif sfi >= 100:
            prop = "Fair"
        else:
            prop = "Poor"

        if kp >= 5:
            geo = f"Storm (Kp={kp:.1f})"
        elif kp >= 3:
            geo = f"Unsettled (Kp={kp:.1f})"
        else:
            geo = f"Quiet (Kp={kp:.1f})"

        return f"Solar: SFI={sfi:.0f} ({prop}) | Geomag: {geo}"
    except Exception as exc:
        return f"Solar lookup failed: {exc}"

def cmd_space(arg="") -> str:
    return random.choice(load_data("space_trivia.txt"))


def cmd_startrek(arg="") -> str:
    return random.choice(load_data("startrek_trivia.txt"))


def cmd_starwars(arg="") -> str:
    return random.choice(load_data("starwars_trivia.txt"))


def cmd_sun(arg="") -> str:
    try:
        lat, lon = _get_latlon(arg.strip() or "01420")
        url = f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&formatted=0"
        req = urllib.request.Request(url, headers={"User-Agent": "meshbot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        from datetime import timezone
        def utc_to_local(s):
            dt = datetime.fromisoformat(s.replace("+00:00", "").rstrip("Z"))
            dt = dt.replace(tzinfo=timezone.utc).astimezone()
            return dt.strftime("%H:%M")
        res = data["results"]
        return (f"Sun for {arg.strip() or '01420'}: "
                f"Rise {utc_to_local(res['sunrise'])} | "
                f"Set {utc_to_local(res['sunset'])} | "
                f"Solar noon {utc_to_local(res['solar_noon'])}")
    except Exception as exc:
        return f"Sunrise lookup failed: {exc}"

def cmd_top(arg="") -> str:
    result = subprocess.run(["top", "-bn1"], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return "\n".join(result.stdout.splitlines()[:5]).strip()


def cmd_trivia(arg="") -> str:
    return random.choice(load_data("trivia.txt"))


def cmd_uptime(arg="") -> str:
    result = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else f"Error: {result.stderr.strip()}"


def cmd_version(arg="") -> str:
    return f"Fitchbot v{BOT_VERSION} | {datetime.now().strftime('%Y-%m-%d')} | Fitchburg Mesh"


def cmd_wxc(arg="") -> str:
    zipcode = arg.strip() or "01420"
    try:
        data = _fetch_wttr(zipcode)
        c = data["current_condition"][0]
        desc = c["weatherDesc"][0]["value"]
        return (f"{zipcode} | {desc} | {c['temp_C']}C | "
                f"Precip: {c['precipMM']}mm | {c['pressure']} hPa")
    except Exception as exc:
        return f"Weather lookup failed: {exc}"

def cmd_wxf(arg="") -> str:
    zipcode = arg.strip() or "01420"
    try:
        data = _fetch_wttr(zipcode)
        c = data["current_condition"][0]
        desc = c["weatherDesc"][0]["value"]
        return (f"{zipcode} | {desc} | {c['temp_F']}F | "
                f"Precip: {c['precipInches']}\" | {c['pressure']} hPa")
    except Exception as exc:
        return f"Weather lookup failed: {exc}"

# ---------------------------------------------------------------------------
# COMMANDS dict (alphabetical by trigger)
# ---------------------------------------------------------------------------

COMMANDS = {
    "!band":      cmd_band,
    "!callsign":  cmd_callsign,
    "!catfact":   cmd_catfact,
    "!df":        cmd_df,
    "!dogfact":   cmd_dogfact,
    "!fitchfact": cmd_fitchfact,
    "!futurama":  cmd_futurama,
    "!hamfact":   cmd_hamfact,
    "!hello":     cmd_hello,
    "!joke":      cmd_joke,
    "!lotr":      cmd_lotr,
    "!onthisday": cmd_onthisday,
    "!ping":      lambda arg="": "PONG!",
    "!prop":      cmd_prop,
    "!q":         cmd_q,
    "!quote":     cmd_quote,
    "!roll":      cmd_roll,
    "!secret":    cmd_secret,
    "!simpsons":  cmd_simpsons,
    "!solar":     cmd_solar,
    "!space":     cmd_space,
    "!startrek":  cmd_startrek,
    "!starwars":  cmd_starwars,
    "!sun":       cmd_sun,
    "!top":       cmd_top,
    "!trivia":    cmd_trivia,
    "!uptime":    cmd_uptime,
    "!ver":       cmd_version,
    "!wxc":       cmd_wxc,
    "!wxf":       cmd_wxf,
}


# ---------------------------------------------------------------------------
# Channel discovery
# ---------------------------------------------------------------------------

async def init_device(meshcore: MeshCore) -> None:
    result = await meshcore.commands.send_appstart()
    if result.type == EventType.ERROR:
        logging.warning("send_appstart failed: %s", result.payload)
    else:
        logging.debug("send_appstart OK: %s", result.payload)


async def find_channel_index(meshcore: MeshCore, name: str) -> int | None:
    for idx in range(8):
        result = await meshcore.commands.get_channel(idx)
        if result.type == EventType.ERROR:
            logging.debug("Channel slot %d: error — %s", idx, result.payload)
            continue
        ch_name = result.payload.get("channel_name", "").strip()
        logging.debug("Channel slot %d: '%s'", idx, ch_name)
        if ch_name.lower() == name.lower():
            logging.info("Found channel '%s' at index %d", name, idx)
            return idx
    return None


async def list_channels(meshcore: MeshCore) -> None:
    await init_device(meshcore)
    print("Scanning channels...")
    found = False
    for idx in range(8):
        result = await meshcore.commands.get_channel(idx)
        if result.type == EventType.ERROR:
            continue
        ch_name = result.payload.get("channel_name", "").strip()
        if ch_name:
            print(f"  [{idx}] {ch_name}")
            found = True
    if not found:
        print("  No channels found.")

# ---------------------------------------------------------------------------
# Main bot loop
# ---------------------------------------------------------------------------

async def run_bot(port: str, baud: int, channel_override: int | None = None) -> None:
    logging.info("Connecting to %s at %d baud…", port, baud)
    meshcore = await MeshCore.create_serial(port, baud)
    logging.info("Connected.")

    if channel_override is not None:
        channel_idx = channel_override
        logging.info("Using channel index %d (from --channel flag)", channel_idx)
    else:
        await init_device(meshcore)
        channel_idx = await find_channel_index(meshcore, TARGET_CHANNEL_NAME)
        if channel_idx is None:
            logging.error("Channel '%s' not found. Run with --list-channels.", TARGET_CHANNEL_NAME)
            await meshcore.disconnect()
            return

    logging.info("Listening on channel '%s' (index %d)", TARGET_CHANNEL_NAME, channel_idx)

    async def send_reply(reply: str) -> None:
        if len(reply) > 140:
            reply = reply[:137] + "..."
        result = await meshcore.commands.send_chan_msg(channel_idx, reply)
        if result.type == EventType.ERROR:
            logging.error("Failed to send reply: %s", result.payload)
        else:
            logging.info("Reply sent.")

    async def on_channel_message(event):
        payload = event.payload
        if payload.get("channel_idx") != channel_idx:
            return

        text = payload.get("text", "").strip()
        # Strip "Name: " sender prefix only when result looks like a command
        if ": " in text:
            candidate = text.split(": ", 1)[1].strip()
            if candidate.startswith("!"):
                logging.debug("Stripped prefix: '%s' -> '%s'", text, candidate)
                text = candidate
        sender = payload.get("pubkey_prefix", "unknown")
        logging.info("[%s] %s: %s", TARGET_CHANNEL_NAME, sender, text)

        # --- Async special commands ---

        if text.lower().startswith("!help"):
            await asyncio.sleep(3)
            await send_reply(
                "!df !uptime !top !wxf !wxc !alerts "
                "!fitchfact !hello !joke !quote !catfact !dogfact "
                "!trivia !startrek !starwars !futurama !simpsons"
            )
            await asyncio.sleep(5)
            await send_reply(
                "!lotr !space !onthisday !hamfact "
                "!q !band !solar !prop !sun !callsign "
                "!roll !remind !ping !help"
            )
            return

        if text.lower().startswith("!alerts"):
            zipcode = text[7:].strip() or "01420"
            loop = asyncio.get_event_loop()
            reply = await loop.run_in_executor(None, cmd_alerts_sync, zipcode)
            await send_reply(reply)
            return

        if text.lower().startswith("!remind"):
            parts = text[7:].strip().split(None, 1)
            if len(parts) < 2 or not parts[0].isdigit():
                await send_reply("Usage: !remind <minutes> <message>")
                return
            minutes = int(parts[0])
            message = parts[1]
            if minutes < 1 or minutes > 1440:
                await send_reply("Remind time must be 1-1440 minutes.")
                return
            await send_reply(f"Reminder set for {minutes} min.")

            async def _remind():
                await asyncio.sleep(minutes * 60)
                await send_reply(f"Reminder: {message}")

            asyncio.create_task(_remind())
            return

        # --- Sync commands ---
        for trigger, handler in COMMANDS.items():
            if text.lower().startswith(trigger):
                logging.info("Triggered: %s", trigger)
                arg = text[len(trigger):].strip()
                try:
                    reply = handler(arg)
                except Exception as exc:
                    reply = f"Error running {trigger}: {exc}"
                await send_reply(reply)
                break
        else:
            logging.debug("No command matched for: '%s'", text)

    meshcore.subscribe(EventType.CHANNEL_MSG_RECV, on_channel_message)
    await meshcore.start_auto_message_fetching()

    logging.info("Bot v%s running. Press Ctrl+C to stop.", BOT_VERSION)
    try:
        await asyncio.sleep(float("inf"))
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await meshcore.stop_auto_message_fetching()
        await meshcore.disconnect()
        logging.info("Disconnected.")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MeshCore channel bot")
    parser.add_argument("--port", default=DEFAULT_PORT, help="Serial port (default: %(default)s)")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="Baud rate (default: %(default)s)")
    parser.add_argument("--channel", type=int, default=None, metavar="IDX",
                        help="Override channel index instead of searching by name")
    parser.add_argument("--list-channels", action="store_true",
                        help="List all channels on the device and exit")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.list_channels:
        async def _list():
            mc = await MeshCore.create_serial(args.port, args.baud)
            await list_channels(mc)
            await mc.disconnect()
        asyncio.run(_list())
        return

    asyncio.run(run_bot(args.port, args.baud, channel_override=args.channel))


if __name__ == "__main__":
    main()
