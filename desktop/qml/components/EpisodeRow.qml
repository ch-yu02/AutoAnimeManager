import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import AutoAnime 1.0

Rectangle {
    id: root
    property string numberText: ""
    property string title: ""
    property string metadata: ""
    property string statusText: ""
    property string status: ""
    property real progress: 0
    property bool watched: false
    property bool watchedBusy: false
    property bool playable: false
    property bool searchable: false
    property bool debugVisible: false
    signal playClicked()
    signal searchClicked()
    signal fromStartClicked()
    signal toggleWatchedClicked()
    signal magnetClicked()
    signal debugClicked()

    Layout.fillWidth: true
    implicitHeight: 64
    radius: Metrics.radiusS
    color: hover.hovered ? Theme.surfaceHover : Theme.surfaceLow
    border.width: 1
    border.color: hover.hovered ? Theme.border : Theme.borderSoft
    HoverHandler { id: hover }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Metrics.space4
        anchors.rightMargin: Metrics.space3
        spacing: Metrics.space3
        Label {
            Layout.preferredWidth: 72
            text: root.numberText
            color: Theme.accent
            font.family: Typography.monoFamily
            font.pixelSize: Typography.label
            font.weight: Typography.medium
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Metrics.space1
            Label {
                Layout.fillWidth: true
                text: root.title
                color: Theme.textPrimary
                font.family: Typography.family
                font.pixelSize: Typography.body
                font.weight: Typography.medium
                elide: Text.ElideRight
            }
            Label {
                Layout.fillWidth: true
                text: root.metadata
                color: Theme.textTertiary
                font.family: Typography.family
                font.pixelSize: Typography.meta
                elide: Text.ElideRight
            }
        }
        AppProgressBar { Layout.preferredWidth: 96; visible: root.progress > 0; value: root.progress }
        StatusBadge { visible: root.statusText.length > 0; text: root.statusText; status: root.status }
        AppButton {
            text: root.playable ? "播放" : "搜索"
            variant: root.playable ? "primary" : "secondary"
            iconName: root.playable ? "play" : "search"
            enabled: root.playable || root.searchable
            onClicked: root.playable ? root.playClicked() : root.searchClicked()
        }
        IconButton {
            iconName: "more-horizontal"
            tooltip: "更多操作"
            onClicked: episodeMenu.open()
            Menu {
                id: episodeMenu
                MenuItem { text: root.watched ? "设为未看" : "设为已看"; enabled: !root.watchedBusy; onTriggered: root.toggleWatchedClicked() }
                MenuItem { text: "从头播放"; visible: root.playable; onTriggered: root.fromStartClicked() }
                MenuSeparator { visible: root.searchable }
                MenuItem { text: "输入磁力链接"; visible: root.searchable; onTriggered: root.magnetClicked() }
                MenuItem { text: "调试选择"; visible: root.debugVisible && root.searchable; onTriggered: root.debugClicked() }
            }
        }
    }
}
