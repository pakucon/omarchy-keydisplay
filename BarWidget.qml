import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui

// Shows the last key or key combination pressed anywhere on the system.
// Reads keyboard events from a helper that monitors /dev/input/event*, then
// prints the resolved combo one line at a time; we stream each line into the
// bar label. Clicking does nothing by design.

BarWidget {
  id: root
  moduleName: "jp.keydisplay"

  property string display: "⌨"

  function onCombo(line) {
    var text = String(line || "").trim()
    if (text === "__clear__") { root.display = "⌨"; return }
    if (text.length > 0 && text !== "error:no keyboard devices")
      root.display = text
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Process {
    id: keyProc
    running: true
    command: ["python3", String(Qt.resolvedUrl("keymonitor.py")).replace("file://", "")]

    stdout: SplitParser {
      onRead: function(line) { root.onCombo(line) }
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.display
    tooltipText: "Last key pressed"
  }
}
