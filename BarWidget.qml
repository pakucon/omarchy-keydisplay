import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui

// Shows the last Omarchy keybinding you pressed, captured in a scoped way.
// A helper (keymonitor.py) runs as the dedicated "keydisplay" user — the only
// member of the system "input" group — so your other processes never gain
// access to raw keyboard events. The helper only ever prints combos that match
// a real Omarchy keybinding (from `omarchy menu keybindings --print`); typed
// text such as passwords is read by the helper but never printed or displayed.

BarWidget {
  id: root
  moduleName: "jp.keydisplay"

  property string display: "⌨"
  property string pluginPath: String(Qt.resolvedUrl("keymonitor.py")).replace("file://", "")
  property string dir: pluginPath.substring(0, pluginPath.lastIndexOf("/") + 1)

  function onCombo(line) {
    var text = String(line || "").trim()
    if (text === "__clear__") { root.display = "⌨"; return }
    if (text.length > 0 && !text.startsWith("error:"))
      root.display = text
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Process {
    id: keyProc
    running: true
    command: ["/bin/sh", "-c",
      "/usr/share/omarchy/bin/omarchy menu keybindings --print > '" + dir + "bindings.txt' 2>/dev/null; " +
      "exec /usr/bin/sudo -u keydisplay /usr/bin/python3 '" + dir + "keymonitor.py'"]

    stdout: SplitParser {
      onRead: function(line) { root.onCombo(line) }
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.display
    tooltipText: "Last keybinding pressed"
  }
}
