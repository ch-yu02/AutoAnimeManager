import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import AutoAnime 1.0

Page {
    id: root
    objectName: "subjectsPage"
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

    function selectCollection(value) {
        collectionType = value
        backend.loadSubjects(collectionType, localOnly)
    }
    function jumpToGroup(index) {
        const item = groupRepeater.itemAt(index)
        if (item && contentColumn.height > scroll.availableHeight)
            scroll.ScrollBar.vertical.position = Math.min(1, item.y / (contentColumn.height - scroll.availableHeight))
    }

    background: Rectangle { color: Theme.canvas }
    header: Rectangle {
        implicitHeight: 128
        color: Theme.canvas
        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: Metrics.pageMargin(root.width)
            anchors.rightMargin: Metrics.pageMargin(root.width)
            spacing: Metrics.space2
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: Metrics.pageHeaderHeight
                Label { text: "我的条目"; color: Theme.textPrimary; font.pixelSize: Typography.pageTitle; font.weight: Typography.semibold }
                Item { Layout.fillWidth: true }
                Label { text: backend.subjects.length + " 部"; color: Theme.textTertiary; font.pixelSize: Typography.meta }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 0
                Repeater {
                    model: [
                        { name: "在看", value: "DOING" }, { name: "想看", value: "WISH" },
                        { name: "看过", value: "COLLECTED" }, { name: "搁置", value: "ON_HOLD" },
                        { name: "抛弃", value: "DROPPED" }
                    ]
                    delegate: AppTab {
                        required property var modelData
                        text: modelData.name
                        selected: root.collectionType === modelData.value
                        onClicked: root.selectCollection(modelData.value)
                    }
                }
                Item { Layout.fillWidth: true }
                AppButton {
                    text: "仅显示本地已匹配"
                    variant: "filter"
                    checkable: true
                    checked: root.localOnly
                    selected: checked
                    onToggled: {
                        root.localOnly = checked
                        backend.loadSubjects(root.collectionType, root.localOnly)
                    }
                }
                ComboBox {
                    Layout.preferredWidth: 144
                    model: root.timeGroups
                    textRole: "label"
                    displayText: "跳转到年份"
                    onActivated: root.jumpToGroup(currentIndex)
                }
            }
        }
    }

    ScrollView {
        id: scroll
        anchors.fill: parent
        anchors.leftMargin: Metrics.pageMargin(root.width)
        anchors.rightMargin: Metrics.pageMargin(root.width)
        anchors.topMargin: Metrics.space6
        contentWidth: availableWidth
        Column {
            id: contentColumn
            width: scroll.availableWidth
            spacing: Metrics.space8
            Repeater {
                id: groupRepeater
                model: root.timeGroups
                delegate: Column {
                    id: yearGroup
                    required property var modelData
                    width: contentColumn.width
                    spacing: Metrics.space3
                    SectionHeader { width: yearGroup.width; title: yearGroup.modelData.label; detail: yearGroup.modelData.items.length + " 部" }
                    Flow {
                        id: subjectFlow
                        width: parent.width
                        spacing: Metrics.space4
                        Repeater {
                            model: yearGroup.modelData.items
                            delegate: MediaCard { required property var modelData; itemData: modelData; onClicked: root.openSubject(modelData.id) }
                        }
                    }
                }
            }
            EmptyState {
                visible: root.timeGroups.length === 0 && !(backend.activities.subjectsLoading || false)
                width: contentColumn.width
                title: "当前分类没有条目"
                detail: root.localOnly ? "关闭本地筛选以查看全部收藏条目。" : "Bangumi 同步后，条目会按放送年份显示。"
                iconName: "library-big"
            }
            Item { width: 1; height: Metrics.space6 }
        }
    }
    BusyIndicator { anchors.centerIn: parent; running: (backend.activities.subjectsLoading || false) && backend.subjects.length === 0 }
    Component.onCompleted: backend.loadSubjects(collectionType, localOnly)
}
