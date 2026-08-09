import QtQuick
import QtQuick.Controls

Item {
    id: root
    required property var itemData
    signal clicked()
    width: 164
    height: 292

    Rectangle {
        anchors.fill: parent
        radius: 10
        color: mouse.containsMouse ? "#1a2635" : "#121a25"

        Image {
            id: poster
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 232
            source: root.itemData.image_url || ""
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            sourceSize.width: 328
        }
        Rectangle {
            anchors.fill: poster
            visible: poster.status !== Image.Ready
            color: "#202b39"
            Label { anchors.centerIn: parent; text: "无海报"; color: "#738297" }
        }
        Label {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: 10
            text: root.itemData.display_name || root.itemData.name || "未命名"
            color: "#f2f5f8"
            elide: Text.ElideRight
            font.pixelSize: 14
            font.weight: Font.Medium
        }
        MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.clicked() }
    }
}
