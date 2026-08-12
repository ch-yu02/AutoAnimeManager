import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: root
    signal openSubject(int id)
    property string collectionType: "DOING"
    property bool localOnly: false
    property var timeGroups: {
        const sorted = backend.subjects.slice().sort((left, right) => {
            const dateOrder = (right.air_date || "").localeCompare(left.air_date || "")
            return dateOrder !== 0 ? dateOrder : (left.display_name || "").localeCompare(right.display_name || "")
        })
        const groups = []
        for (let i = 0; i < sorted.length; ++i) {
            const year = sorted[i].air_date ? sorted[i].air_date.slice(0, 4) : "unknown"
            if (groups.length === 0 || groups[groups.length - 1].year !== year)
                groups.push({ year: year, label: year === "unknown" ? "时间未知" : year + " 年", items: [] })
            groups[groups.length - 1].items.push(sorted[i])
        }
        return groups
    }

    function jumpToGroup(index) {
        const item = groupRepeater.itemAt(index)
        if (item && contentColumn.height > scroll.availableHeight)
            scroll.ScrollBar.vertical.position = Math.min(1, item.y / (contentColumn.height - scroll.availableHeight))
    }

    background: Rectangle { color: "#0b1018" }
    header: ColumnLayout {
        spacing: 12
        anchors.leftMargin: 30; anchors.rightMargin: 30
        Label { text: "我的条目"; color: "#f2f5f8"; font.pixelSize: 30; font.weight: Font.DemiBold }
        RowLayout {
            Repeater {
                model: [
                    { name: "在看", value: "DOING" }, { name: "想看", value: "WISH" },
                    { name: "看过", value: "COLLECTED" }, { name: "搁置", value: "ON_HOLD" },
                    { name: "抛弃", value: "DROPPED" }
                ]
                delegate: Button {
                    required property var modelData
                    text: modelData.name
                    flat: root.collectionType !== modelData.value
                    highlighted: root.collectionType === modelData.value
                    onClicked: { root.collectionType = modelData.value; backend.loadSubjects(root.collectionType, root.localOnly) }
                }
            }
            Item { Layout.fillWidth: true }
            Switch {
                text: "只显示本地已匹配"
                checked: root.localOnly
                onToggled: { root.localOnly = checked; backend.loadSubjects(root.collectionType, root.localOnly) }
            }
            ComboBox {
                Layout.preferredWidth: 130
                model: root.timeGroups
                textRole: "label"
                displayText: "跳转到时间"
                onActivated: root.jumpToGroup(currentIndex)
            }
        }
    }
    ScrollView {
        id: scroll
        anchors.fill: parent
        anchors.margins: 28
        contentWidth: availableWidth
        Column {
            id: contentColumn
            width: scroll.availableWidth
            spacing: 18
            Repeater {
                id: groupRepeater
                model: root.timeGroups
                delegate: Column {
                    required property var modelData
                    width: contentColumn.width
                    spacing: 10
                    Label { text: parent.modelData.label; color: "#93a1b2"; font.pixelSize: 16; font.weight: Font.DemiBold }
                    Flow {
                        width: parent.width
                        spacing: 16
                        Repeater {
                            model: parent.parent.modelData.items
                            delegate: MediaCard { required property var modelData; itemData: modelData; onClicked: root.openSubject(modelData.id) }
                        }
                    }
                }
            }
        }
    }
    BusyIndicator { anchors.centerIn: parent; running: backend.busy && backend.subjects.length === 0 }
    Component.onCompleted: backend.loadSubjects(collectionType, localOnly)
}
