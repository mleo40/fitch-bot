#!/usr/bin/env python3
"""
meshbot.py — MeshCore channel bot for the Fitchburg channel.

Listens for commands on a named channel and replies with results:
  !df          — disk usage (df -h)
  !uptime      — system uptime
  !top         — CPU/memory summary (top -bn1)
  !wxf <zip>   — live weather in °F for a zip code
  !wxc <zip>   — live weather in °C for a zip code
  !fitchfact    — random fact about Fitchburg, MA
  !wx          — contents of a local weather file

Usage:
  python meshbot.py [--port /dev/ttyUSB0] [--baud 115200]
"""

import asyncio
import argparse
import subprocess
import logging
import json
import random
import urllib.request

from meshcore import MeshCore, EventType

# ---------------------------------------------------------------------------
# Configuration — edit these or override via CLI args
# ---------------------------------------------------------------------------

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 115200
TARGET_CHANNEL_NAME = "Fitchburg"

# ---------------------------------------------------------------------------
# Command handlers — each returns a string to post back to the channel
# ---------------------------------------------------------------------------

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
    # -bn1: batch mode, 1 iteration; show only the summary lines (first 5)
    result = subprocess.run(
        ["top", "-bn1"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    lines = result.stdout.splitlines()
    # First 5 lines contain CPU, memory, and load summary
    return "\n".join(lines[:5]).strip()


FITCHBURG_FACTS = [
    "Fitchburg was incorporated as a city in 1872, making it one of the older cities in central Massachusetts.",
    "Fitchburg is home to Fitchburg State University, founded in 1894 as a normal school for teacher training.",
    "The Fitchburg Art Museum, founded in 1925, is one of the oldest art museums in New England.",
    "Fitchburg was a major center of the paper manufacturing industry in the 19th and early 20th centuries.",
    "The Fitchburg Railroad, established in 1845, connected Fitchburg to Boston and helped drive industrial growth.",
    "Fitchburg sits along the Nashua River, which powered the mills that fueled its industrial economy.",
    "At its peak, Fitchburg was one of the leading manufacturing cities in Massachusetts, producing machinery, textiles, and paper.",
    "Fitchburg's Rollstone Boulder — a 110-ton granite erratic deposited by glaciers — was moved downtown in 1930 to preserve it.",
    "The city covers about 28 square miles and sits at roughly 400 feet above sea level in north-central Massachusetts.",
    "Fitchburg has a strong Finnish heritage; Finnish immigrants came to work in the paper mills in the early 1900s.",
    "The Fitchburg Public Library, opened in 1859, is one of the earliest public libraries in the state.",
    "Fitchburg's zip code 01420 covers the main city area, with 01422 covering the Westminster street area.",
    "Lunenburg, Westminster, Leominster, and Ashby all border the city of Fitchburg.",
    "The Wallace Civic Center (now the Fidelity Bank Memorial Center) has hosted concerts, hockey, and community events since 1976.",
    "Fitchburg has one of the largest Portuguese-American communities in Massachusetts.",
    "The city's motto is 'Tradition and Progress,' reflecting its industrial history and ongoing development.",
    "Mount Elam Pond and Coburn Park offer green space and recreation within the city limits.",
    "Fitchburg experienced significant deindustrialization in the mid-20th century, leading to urban renewal efforts that continue today.",
    "The Fitchburg line commuter rail still runs to Boston's North Station, a route established over 175 years ago.",
    "Fitchburg is the seat of Worcester County's northern district and home to a district courthouse.",
]


def cmd_fitchfact(arg="") -> str:
    return random.choice(FITCHBURG_FACTS)


def _fetch_wttr(location: str) -> dict:
    """Fetch current conditions from wttr.in for a zip code or city."""
    url = f"https://wttr.in/{urllib.request.quote(location)}?format=j1"
    req = urllib.request.Request(url, headers={"User-Agent": "meshbot/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def cmd_wxf(arg="") -> str:
    zipcode = arg.strip() or "01420"
    try:
        data = _fetch_wttr(zipcode)
        c = data["current_condition"][0]
        desc = c["weatherDesc"][0]["value"]
        temp = c["temp_F"]
        precip = c["precipInches"]
        pressure = c["pressure"]  # hPa
        return f"{zipcode} | {desc} | Temp: {temp}°F | Precip: {precip}\" | Pressure: {pressure} hPa"
    except Exception as exc:
        return f"Weather lookup failed: {exc}"


def cmd_wxc(arg="") -> str:
    zipcode = arg.strip() or "01420"
    try:
        data = _fetch_wttr(zipcode)
        c = data["current_condition"][0]
        desc = c["weatherDesc"][0]["value"]
        temp = c["temp_C"]
        precip = c["precipMM"]
        pressure = c["pressure"]  # hPa
        return f"{zipcode} | {desc} | Temp: {temp}°C | Precip: {precip}mm | Pressure: {pressure} hPa"
    except Exception as exc:
        return f"Weather lookup failed: {exc}"


def cmd_help(arg="") -> str:
    return (
        "Fitchbot commands: "
        "!df | !uptime | !top | "
        "!wxf <zip> | !wxc <zip> | "
        "!fitchfact | !help"
    )


COMMANDS = {
    "!df": cmd_df,
    "!uptime": cmd_uptime,
    "!top": cmd_top,
    "!wxf": cmd_wxf,
    "!wxc": cmd_wxc,
    "!fitchfact": cmd_fitchfact,
    "!help": cmd_help,
}

# ---------------------------------------------------------------------------
# Channel discovery
# ---------------------------------------------------------------------------

async def init_device(meshcore: MeshCore) -> None:
    """Initialize device state — required before querying channels/contacts."""
    result = await meshcore.commands.send_appstart()
    if result.type == EventType.ERROR:
        logging.warning("send_appstart failed: %s", result.payload)
    else:
        logging.debug("send_appstart OK: %s", result.payload)


async def find_channel_index(meshcore: MeshCore, name: str) -> int | None:
    """Scan channel slots 0–7 and return the index matching `name`."""
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
    """Print all channel names found on the device."""
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
            logging.error("Channel '%s' not found on device. Exiting.", TARGET_CHANNEL_NAME)
            logging.error("Run with --list-channels to see available channels.")
            await meshcore.disconnect()
            return

    logging.info("Listening on channel '%s' (index %d)", TARGET_CHANNEL_NAME, channel_idx)

    async def on_channel_message(event):
        payload = event.payload
        # Only handle messages on our target channel
        if payload.get("channel_idx") != channel_idx:
            return

        text = payload.get("text", "").strip()
        # Strip optional "Name: " sender prefix that some clients prepend
        if ": " in text:
            stripped = text.split(": ", 1)[1].strip()
            logging.debug("Stripped prefix: '%s' -> '%s'", text, stripped)
            text = stripped
        sender = payload.get("pubkey_prefix", "unknown")
        logging.info("[%s] %s: %s", TARGET_CHANNEL_NAME, sender, text)

        # Check for any recognized command (case-insensitive, allows trailing args)
        for trigger, handler in COMMANDS.items():
            if text.lower().startswith(trigger):
                logging.info("Triggered: %s", trigger)
                arg = text[len(trigger):].strip()
                try:
                    reply = handler(arg)
                except Exception as exc:
                    reply = f"Error running {trigger}: {exc}"
                # Trim reply to fit MeshCore packet limit
                if len(reply) > 140:
                    reply = reply[:137] + "…"
                result = await meshcore.commands.send_chan_msg(channel_idx, reply)
                if result.type == EventType.ERROR:
                    logging.error("Failed to send reply: %s", result.payload)
                else:
                    logging.info("Reply sent.")
                break  # only handle first matching command
        else:
            logging.debug("No command matched for: '%s'", text)

    meshcore.subscribe(EventType.CHANNEL_MSG_RECV, on_channel_message)
    await meshcore.start_auto_message_fetching()

    logging.info("Bot is running. Press Ctrl+C to stop.")
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
