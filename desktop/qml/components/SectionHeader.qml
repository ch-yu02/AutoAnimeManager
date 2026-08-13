import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import AutoAnime 1.0

RowLayout {
    id: root
    property string title: ""
    property string detail: ""
    default property alias actions: actionSlot.data
    spacing: Metrics.space3

    Label {
        text: root.title
        color: Theme.textPrimary
        font.family: Typography.family
        font.pixelSize: Typography.sectionTitle
        font.weight: Typography.semibold
    }
    Label {
        visible: text.length > 0
        text: root.detail
        color: Theme.textTertiary
        font.family: Typography.family
        font.pixelSize: Typography.meta
    }
    Item { Layout.fillWidth: true }
    RowLayout { id: actionSlot; spacing: Metrics.space2 }
}
