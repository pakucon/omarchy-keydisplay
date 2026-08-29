#!/usr/bin/env python3
# Scoped keybinding display helper for the jp.keydisplay Omarchy plugin.
#
# This process is meant to run as a dedicated, unprivileged user (e.g.
# "keydisplay") that is the ONLY member of the system "input" group. Because of
# that, the user's normal processes never obtain raw keyboard access — the
# capture is scoped to this helper. It also never surfaces arbitrary keystrokes:
# it only prints a combo when that exact combo is a real Omarchy keybinding
# (parsed from `omarchy menu keybindings --print`). Typed text such as passwords
# is read by the helper but is never printed or displayed.

import os
import sys
import json
import struct
import select
import subprocess

EVENT_SIZE = struct.calcsize("qqHHi")  # struct input_event on 64-bit Linux
EV_KEY = 1

# Collapse left/right modifier variants onto one code so matching is symmetric.
MOD_NORMALIZE = {126: 125, 97: 29, 54: 42, 100: 56}
MOD_NAME_TO_CODE = {
    "SUPER": 125, "META": 125, "WIN": 125,
    "CTRL": 29, "CONTROL": 29,
    "ALT": 56,
    "SHIFT": 42,
}

# code -> lower-case letter. Linux keycodes are not contiguous across the three
# letter rows (QWERTY 16-25, ASDF 30-38, ZXCV 44-50), so list them.
LETTER_CODES = {
    16: "q", 17: "w", 18: "e", 19: "r", 20: "t", 21: "y", 22: "u", 23: "i",
    24: "o", 25: "p",
    30: "a", 31: "s", 32: "d", 33: "f", 34: "g", 35: "h", 36: "j", 37: "k",
    38: "l",
    44: "z", 45: "x", 46: "c", 47: "v", 48: "b", 49: "n", 50: "m",
}
LETTER_CODES_REV = {v: k for k, v in LETTER_CODES.items()}

FRIENDLY = {
    1: "Esc", 2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 9: "8",
    10: "9", 11: "0", 12: "-", 13: "=", 14: "Backspace", 15: "Tab",
    26: "[", 27: "]", 28: "Enter", 41: "`", 43: "\\", 39: ";", 40: "'",
    51: ",", 52: ".", 53: "/", 57: "Space", 58: "CapsLock",
    59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5", 64: "F6", 65: "F7",
    66: "F8", 67: "F9", 68: "F10", 69: "NumLock", 70: "ScrollLock",
    71: "KP 7", 72: "KP 8", 73: "KP 9", 74: "KP -", 75: "KP 4", 76: "KP 5",
    77: "KP 6", 78: "KP +", 79: "KP 1", 80: "KP 2", 81: "KP 3", 82: "KP 0",
    83: "KP .", 96: "KP Enter", 87: "F11", 88: "F12", 99: "Print",
    102: "Home", 103: "Up", 104: "PageUp", 105: "Left", 106: "Right",
    107: "End", 108: "Down", 109: "PageDown", 110: "Insert", 111: "Delete",
    119: "Pause",
}

CANONICAL = {}


def load_canonical():
    path = "/usr/include/linux/input-event-codes.h"
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line.startswith("#define KEY_"):
                    continue
                parts = line.split()
                if len(parts) < 3:
                    continue
                name, valstr = parts[1], parts[2]
                if name in ("KEY_MAX", "KEY_CNT"):
                    continue
                try:
                    value = int(valstr, 0)
                except ValueError:
                    continue
                CANONICAL[value] = name
    except OSError:
        pass


load_canonical()

NAME_TO_CODE = {}
for code, name in CANONICAL.items():
    NAME_TO_CODE[name.replace("KEY_", "").upper()] = code
for code, disp in FRIENDLY.items():
    NAME_TO_CODE[disp.upper()] = code
NAME_TO_CODE.update({
    "RETURN": 28, "ENTER": 28, "PRINT": 210, "SYSRQ": 210, "PNT": 210,
    "PERIOD": 52, "DOT": 52, "COMMA": 51, "SEMICOLON": 39, "SLASH": 53,
    "ESCAPE": 1, "WIN": 125, "META": 125, "HYPER": 125,
    "UP": 103, "DOWN": 108, "LEFT": 105, "RIGHT": 106,
    "ARROWUP": 103, "ARROWDOWN": 108, "ARROWLEFT": 105, "ARROWRIGHT": 106,
})


def resolve_key_name(name):
    u = name.upper()
    if len(u) == 1 and u.isalpha():
        return LETTER_CODES_REV.get(u.lower())
    return NAME_TO_CODE.get(u)


def combo_to_codes(combo):
    segs = []
    for part in combo.split("+"):
        segs.extend(p.strip().upper() for p in part.split())
    if not segs:
        return None
    key = segs[-1]
    codes = []
    for m in segs[:-1]:
        mc = MOD_NAME_TO_CODE.get(m)
        if mc is None:
            return None
        codes.append(mc)
    kc = resolve_key_name(key)
    if kc is None:
        return None
    codes.append(kc)
    return codes


def parse_bindings(text):
    binds = {}
    for line in text.splitlines():
        if "→" not in line:
            continue
        combo, _desc = line.split("→", 1)
        combo = combo.strip()
        c = combo_to_codes(combo)
        if c is not None:
            binds[frozenset(c)] = combo
    return binds


def load_bindings():
    # Prefer the bindings file written next to this script by the widget (it
    # runs as the real user, so it sees that user's custom keybindings).
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bp = os.path.join(script_dir, "bindings.txt")
    if os.path.exists(bp):
        try:
            with open(bp) as f:
                raw = f.read()
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    text = "\n".join("%s → %s" % (c, d) for c, d in data)
                    return parse_bindings(text)
            except (ValueError, TypeError):
                pass
            return parse_bindings(raw)
        except OSError:
            sys.stderr.write("warn: cannot read bindings file, falling back\n")

    for cmd in ("/usr/share/omarchy/bin/omarchy", "omarchy"):
        try:
            out = subprocess.run([cmd, "menu", "keybindings", "--print"],
                                 capture_output=True, text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                return parse_bindings(out.stdout)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return {}


def open_devices():
    fds = []
    for i in range(128):
        path = "/dev/input/event%d" % i
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            fds.append(fd)
        except OSError:
            pass
    return fds


def main():
    binds = load_bindings()
    if not binds:
        sys.stderr.write("error:no keybindings loaded\n")

    fds = open_devices()
    if not fds:
        sys.stderr.write("error:no keyboard devices\n")
        sys.exit(1)

    pressed = []
    while True:
        readable, _, _ = select.select(fds, [], [], None)
        for fd in readable:
            try:
                data = os.read(fd, 4096)
            except OSError:
                try:
                    os.close(fd)
                except OSError:
                    pass
                if fd in fds:
                    fds.remove(fd)
                continue
            if not data:
                continue
            for off in range(0, len(data), EVENT_SIZE):
                chunk = data[off:off + EVENT_SIZE]
                if len(chunk) < EVENT_SIZE:
                    break
                _, _, etype, code, value = struct.unpack("qqHHi", chunk)
                if etype != EV_KEY:
                    continue
                if 256 <= code <= 511:
                    continue  # mouse / touchpad buttons
                if value == 1:
                    if code not in pressed:
                        pressed.append(code)
                    cur = frozenset(MOD_NORMALIZE.get(c, c) for c in pressed)
                    match = binds.get(cur)
                    if match is not None:
                        sys.stdout.write(match + "\n")
                        sys.stdout.flush()
                elif value == 0:
                    if code in pressed:
                        pressed.remove(code)
                    if not pressed:
                        sys.stdout.write("__clear__\n")
                        sys.stdout.flush()


if __name__ == "__main__":
    main()
