import os
import sys
import time
import struct
import select

EVENT_SIZE = struct.calcsize("qqHHi")  # struct input_event on 64-bit Linux
EV_KEY = 1

# Left/right variants of each modifier collapse to one friendly name.
MODIFIER_CODES = {
    29: "Ctrl", 97: "Ctrl",      # KEY_LEFTCTRL, KEY_RIGHTCTRL
    42: "Shift", 54: "Shift",    # KEY_LEFTSHIFT, KEY_RIGHTSHIFT
    56: "Alt", 100: "Alt",       # KEY_LEFTALT, KEY_RIGHTALT
    125: "Super", 126: "Super",  # KEY_LEFTMETA, KEY_RIGHTMETA
}

# Render order for the modifier cluster.
MOD_ORDER = ["Super", "Ctrl", "Alt", "Shift"]

# Curated short names for the keys people press most. Everything else falls
# back to the canonical Linux keycode name parsed from input-event-codes.h,
# so no real key is ever unnamed or mislabeled.
FRIENDLY = {
    1: "Esc", 2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 9: "8",
    10: "9", 11: "0", 12: "-", 13: "=", 14: "Backspace", 15: "Tab",
    26: "[", 27: "]", 28: "Enter", 41: "`", 43: "\\",
    39: ";", 40: "'", 51: ",", 52: ".", 53: "/",
    57: "Space", 58: "CapsLock",
    59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5", 64: "F6", 65: "F7",
    66: "F8", 67: "F9", 68: "F10", 69: "NumLock", 70: "ScrollLock",
    71: "KP 7", 72: "KP 8", 73: "KP 9", 74: "KP -", 75: "KP 4", 76: "KP 5",
    77: "KP 6", 78: "KP +", 79: "KP 1", 80: "KP 2", 81: "KP 3", 82: "KP 0",
    83: "KP .", 96: "KP Enter", 87: "F11", 88: "F12", 99: "Print",
    102: "Home", 103: "\u2191", 104: "PageUp", 105: "\u2190",
    106: "\u2192", 107: "End", 108: "\u2193", 109: "PageDown", 110: "Insert",
    111: "Delete", 119: "Pause",
}

# code -> lower-case letter. Linux keycodes are NOT contiguous across the
# three letter rows (QWERTY 16-25, ASDF 30-38, ZXCV 44-50), so list them.
LETTER_CODES = {
    16: "q", 17: "w", 18: "e", 19: "r", 20: "t", 21: "y", 22: "u", 23: "i",
    24: "o", 25: "p",
    30: "a", 31: "s", 32: "d", 33: "f", 34: "g", 35: "h", 36: "j", 37: "k",
    38: "l",
    44: "z", 45: "x", 46: "c", 47: "v", 48: "b", 49: "n", 50: "m",
}

# code -> canonical Linux name (e.g. "KEY_MUTE" -> "Mute"), filled at load.
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


def canon_name(code):
    raw = CANONICAL.get(code)
    if raw is None:
        return None
    nm = raw[4:] if raw.startswith("KEY_") else raw
    # "KEY_VOLUMEUP" -> "Volumeup", "KEY_ALL_APPLICATIONS" -> "All Applications".
    return nm.replace("_", " ").title()


# Currently held modifier keycodes -> canonical name.
mod_codes = {}
# Currently held non-modifier keycodes, in press order. Names are resolved at
# display time, so a key's identity stays stable regardless of Shift state.
pressed_codes = []


def key_display(code, shift):
    # Letters: case follows Shift. Keycodes are non-contiguous (see LETTER_CODES).
    if code in LETTER_CODES:
        ch = LETTER_CODES[code]
        return ch.upper() if shift else ch
    if code in FRIENDLY:
        return FRIENDLY[code]
    cn = canon_name(code)
    if cn is not None:
        return cn
    return "Key%d" % code


def emit():
    shift = "Shift" in mod_codes.values()
    parts = []
    for m in MOD_ORDER:
        if m in mod_codes.values():
            parts.append(m)
    for code in pressed_codes:
        parts.append(key_display(code, shift))
    text = " + ".join(parts)
    if text:
        print(text, flush=True)


def handle_press(code):
    # Mouse / touchpad buttons live in 0x100..0x1ff; ignore them.
    if 256 <= code <= 511:
        return
    if code in MODIFIER_CODES:
        mod_codes[code] = MODIFIER_CODES[code]
        emit()
        return
    if code not in pressed_codes:
        pressed_codes.append(code)
    emit()


def handle_release(code):
    if 256 <= code <= 511:
        return
    if code in MODIFIER_CODES:
        mod_codes.pop(code, None)
        emit()
        clear_if_idle()
        return
    if code in pressed_codes:
        pressed_codes.remove(code)
    emit()
    clear_if_idle()


def clear_if_idle():
    # Clear the moment every key is released — no delay.
    if not pressed_codes and not mod_codes:
        print("__clear__", flush=True)


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
    load_canonical()
    fds = open_devices()
    if not fds:
        print("error:no keyboard devices", flush=True)
        sys.exit(1)

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
                if value == 1:
                    handle_press(code)
                elif value == 0:
                    handle_release(code)
                # value == 2 (repeat) is ignored


if __name__ == "__main__":
    main()
