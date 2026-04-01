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

def cmd_version(arg="") -> str:
    return f"Fitchbot v{BOT_VERSION} | {datetime.now().strftime('%Y-%m-%d')} | Fitchburg Mesh"

def cmd_df(arg="") -> str:
    result = subprocess.run(
        ["df", "-h", "--output=target,size,used,avail,pcent"],
        capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip() if result.returncode == 0 else f"Error: {result.stderr.strip()}"

def cmd_uptime(arg="") -> str:
    result = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else f"Error: {result.stderr.strip()}"

def cmd_top(arg="") -> str:
    result = subprocess.run(["top", "-bn1"], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return "\n".join(result.stdout.splitlines()[:5]).strip()

def cmd_fitchfact(arg="") -> str:
    return random.choice(load_data("fitchburg_facts.txt"))

def cmd_hello(arg="") -> str:
    return random.choice(load_data("hello_responses.txt"))

def cmd_joke(arg="") -> str:
    return random.choice(load_data("jokes.txt"))

def cmd_quote(arg="") -> str:
    return random.choice(load_data("quotes.txt"))

def cmd_catfact(arg="") -> str:
    return random.choice(load_data("cat_facts.txt"))

def cmd_dogfact(arg="") -> str:
    return random.choice(load_data("dog_facts.txt"))

def cmd_trivia(arg="") -> str:
    return random.choice(load_data("trivia.txt"))

def cmd_secret(arg="") -> str:
    return random.choice(load_data("secrets.txt"))

def cmd_startrek(arg="") -> str:
    return random.choice(load_data("startrek_trivia.txt"))

def cmd_starwars(arg="") -> str:
    return random.choice(load_data("starwars_trivia.txt"))

def cmd_futurama(arg="") -> str:
    return random.choice(load_data("futurama_trivia.txt"))

def cmd_simpsons(arg="") -> str:
    return random.choice(load_data("simpsons_trivia.txt"))

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

def cmd_help(arg="") -> str:
    return (
        "!df !uptime !top !wxf !wxc !alerts "
        "!fitchfact !hello !joke !quote !catfact !dogfact "
        "!trivia !startrek !starwars !futurama !simpsons !roll !remind !ping !help"
    )

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

# ---------------------------------------------------------------------------
# COMMANDS dict (sync handlers only)
# ---------------------------------------------------------------------------

COMMANDS = {
    "!ver":      cmd_version,
    "!df":       cmd_df,
    "!uptime":   cmd_uptime,
    "!top":      cmd_top,
    "!wxf":      cmd_wxf,
    "!wxc":      cmd_wxc,
    "!fitchfact":cmd_fitchfact,
    "!catfact":  cmd_catfact,
    "!dogfact":  cmd_dogfact,
    "!trivia":   cmd_trivia,
    "!startrek": cmd_startrek,
    "!starwars": cmd_starwars,
    "!futurama": cmd_futurama,
    "!simpsons": cmd_simpsons,
    "!joke":     cmd_joke,
    "!quote":    cmd_quote,
    "!hello":    cmd_hello,
    "!roll":     cmd_roll,
    "!ping":     lambda arg="": "PONG!",
    "!secret":   cmd_secret,
    "!help":     cmd_help,
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

