import QtQuick
import QtQuick.Controls
import AutoAnime 1.0

Item {
    id: root
    required property var itemData
    property real progress: Number(itemData.progress_ratio || itemData.watched_ratio || 0)
    property bool localReady: !!(itemData.local_ready || itemData.has_local_media)
    property string metadata: itemData.air_date ? String(itemData.air_date).slice(0, 4) : ""
    signal clicked()
    width: Metrics.posterWidth
    height: Metrics.mediaCardHeight
    activeFocusOnTab: true
    Keys.onReturnPressed: root.clicked()
    Keys.onEnterPressed: root.clicked()
    scale: mouse.containsMouse ? 1.018 : 1

    RoundedImage {
        id: poster
        anchors.top: parent.top
        anchors.left: parent.left
        width: Metrics.posterWidth
        height: Metrics.posterHeight
        source: root.itemData.image_url || ""
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        sourceSize.width: Metrics.posterWidth * 2
        radius: Metrics.radiusM
        cornerColor: Theme.canvas
    }
    Rectangle {
        anchors.fill: poster
        color: Theme.surface
        visible: poster.status !== Image.Ready
        radius: Metrics.radiusM
        Image { anchors.centerIn: parent; source: "qrc:/AutoAnime/qml/icons/image.svg"; sourceSize.width: 28; sourceSize.height: 28; opacity: 0.45 }
    }
    Rectangle {
        anchors.fill: poster
        color: "transparent"
        radius: Metrics.radiusM
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? Theme.focusRing : (mouse.containsMouse ? Theme.borderStrong : Theme.border)
    }
    Rectangle {
        anchors.left: poster.left
        anchors.right: poster.right
        anchors.bottom: poster.bottom
        height: root.progress > 0 ? 3 : 0
        radius: height / 2
        color: Qt.rgba(1, 1, 1, 0.22)
        Rectangle { width: parent.width * Math.max(0, Math.min(1, root.progress)); height: parent.height; radius: height / 2; color: Theme.accent }
    }
    StatusBadge {
        visible: root.localReady
        anchors.right: poster.right
        anchors.bottom: poster.bottom
        anchors.margins: Metrics.space2
        text: "本地"
        status: "READY"
    }
    Label {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: poster.bottom
        anchors.topMargin: Metrics.space2
        text: root.itemData.display_name || root.itemData.name || "未命名"
        color: mouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
        font.family: Typography.family
        font.pixelSize: Typography.body
        font.weight: Typography.medium
        maximumLineCount: root.metadata.length > 0 ? 1 : 2
        elide: Text.ElideRight
        wrapMode: Text.Wrap
    }
    Label {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        visible: root.metadata.length > 0
        text: root.metadata
        color: Theme.textTertiary
        font.family: Typography.family
        font.pixelSize: Typography.meta
    }
    MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.clicked() }
    Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
}
