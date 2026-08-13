import QtQuick
import QtQuick.Controls
import QtQuick.Controls.impl
import AutoAnime 1.0

Button {
    id: control
    required property string iconName
    property string tooltip: ""
    property int iconSize: 20
    property color foreground: enabled ? (hovered ? Theme.textPrimary : Theme.textSecondary) : Theme.textDisabled

    implicitWidth: Metrics.controlHeight
    implicitHeight: Metrics.controlHeight
    padding: 0
    text: ""
    icon.source: "qrc:/AutoAnime/qml/icons/" + iconName + ".svg"
    icon.width: iconSize
    icon.height: iconSize
    icon.color: foreground
    scale: down ? 0.98 : 1
    contentItem: IconLabel {
        display: AbstractButton.IconOnly
        icon: control.icon
        color: control.foreground
    }
    background: Rectangle {
        radius: Metrics.radiusS
        color: control.hovered ? Theme.surfaceHover : "transparent"
        border.width: control.activeFocus ? 2 : 0
        border.color: Theme.focusRing
        Behavior on color { ColorAnimation { duration: 140 } }
    }
    ToolTip.visible: tooltip.length > 0 && hovered
    ToolTip.delay: 500
    ToolTip.text: tooltip
    Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }
}
