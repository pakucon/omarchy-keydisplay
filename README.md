# Key Display

Shows the last **Omarchy keybinding** you pressed, live in the Omarchy bar. Clicking the widget does nothing.

The widget only ever displays combos that match a real Omarchy keybinding (from `omarchy menu keybindings --print`). Typed text — including passwords you enter in other applications — is never captured, printed, or displayed.

## Privacy model (why this is safe)

This plugin needs raw keyboard access to know which keybinding you pressed. That access is **scoped**, not system-wide:

- A small helper (`keymonitor.py`) runs as a **dedicated, unprivileged user** (`keydisplay`) that is the *only* member of the system `input` group.
- Your normal user and every other process you run gain **no** new access to `/dev/input`, so they cannot read global keystrokes (no system-wide keylogger).
- The helper reads keystrokes **only to match them against the keybinding list**, and prints solely the matching combo. Arbitrary keystrokes are discarded.

In short: the privilege is scoped to this plugin, and the output is limited to keybindings.

## Requirements

- An Omarchy (Quattro) shell.
- A one-time, sudo setup that creates the scoped `keydisplay` user (see Setup). Your user does **not** need to be in the `input` group.

## Setup (one-time, needs sudo)

Create the scoped user and let your user launch its helper without a password:

```sh
sudo useradd -r -s /usr/bin/nologin -G input keydisplay

# Replace <PLUGIN_DIR> with this plugin's directory, e.g.
#   /home/$USER/.config/omarchy/plugins/jp.keydisplay
sudo tee /etc/sudoers.d/keydisplay >/dev/null <<EOF
$USER ALL=(keydisplay) NOPASSWD: /usr/bin/python3 <PLUGIN_DIR>/keymonitor.py
EOF
sudo chmod 0440 /etc/sudoers.d/keydisplay
sudo visudo -c
```

`<PLUGIN_DIR>` is the path printed by:

```sh
ls -d ~/.config/omarchy/plugins/jp.keydisplay
```

## Install

```sh
omarchy plugin add https://github.com/pakucon/omarchy-keydisplay.git --enable
```

## Usage

Press any Omarchy keybinding (e.g. `Super + K`, `Super + Space`, `Print`). The combo appears in the bar and clears the moment you release all keys. Pressing ordinary keys or typing text shows nothing.

## Configure

Move the widget to another bar section:

```sh
omarchy bar move jp.keydisplay --section center
```

## Remove

```sh
omarchy plugin remove jp.keydisplay
sudo userdel keydisplay          # optional: remove the scoped user
sudo rm /etc/sudoers.d/keydisplay # optional: remove the sudoers rule
```

## How it works

A helper reads `/dev/input/event*` **as the `keydisplay` user** (the only member of `input`) and streams each keybinding combo to the QML widget over stdout. Keybinding names come from `omarchy menu keybindings --print`; any combo that is not a known keybinding is dropped before it reaches the widget. There are no external dependencies beyond Python 3.
