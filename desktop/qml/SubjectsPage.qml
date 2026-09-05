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
        subjectList.positionViewAtIndex(index, ListView.Beginning)
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
                    text: "只看本地可播放"
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

    ListView {
        id: subjectList
        anchors.fill: parent
        anchors.leftMargin: Metrics.pageMargin(root.width)
        anchors.rightMargin: Metrics.pageMargin(root.width)
        anchors.topMargin: Metrics.space6
        bottomMargin: Metrics.space6
        spacing: Metrics.space8
        clip: true
        reuseItems: true
        cacheBuffer: Metrics.mediaCardHeight
        model: root.timeGroups
        delegate: Item {
            id: yearGroup
            required property var modelData
            width: subjectList.width
            height: sectionHeader.implicitHeight + Metrics.space3 + subjectFlow.height
            SectionHeader {
                id: sectionHeader
                width: parent.width
                title: yearGroup.modelData.label
                detail: yearGroup.modelData.items.length + " 部"
            }
            Flow {
                id: subjectFlow
                anchors.top: sectionHeader.bottom
                anchors.topMargin: Metrics.space3
                width: parent.width
                height: childrenRect.height
                spacing: Metrics.space4
                Repeater {
                    model: yearGroup.modelData.items
                    delegate: MediaCard {
                        required property var modelData
                        itemData: modelData
                        onClicked: root.openSubject(modelData.id)
                    }
                }
            }
        }
    }
    EmptyState {
        visible: root.timeGroups.length === 0 && !(backend.activities.subjectsLoading || false)
        anchors.centerIn: parent
        width: Math.min(520, parent.width - Metrics.space12)
        title: "当前分类没有条目"
        detail: root.localOnly ? "关闭筛选即可查看此分类的全部条目。" : "同步 Bangumi 后，这里会按放送年份整理收藏。"
        iconName: "library-big"
    }
    BusyIndicator { anchors.centerIn: parent; running: (backend.activities.subjectsLoading || false) && backend.subjects.length === 0 }
    Component.onCompleted: backend.loadSubjects(collectionType, localOnly)
}
