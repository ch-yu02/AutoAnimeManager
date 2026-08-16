import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import AutoAnime 1.0

Page {
    id: root
    property string category: "needs_review"
    property int selectedSubjectId: -1
    property int selectedEpisodeId: -1
    property string selectedSubjectName: ""
    property var currentFiles: backend.review[category] || []
    property bool scanRunning: backend.scanStatus.status === "RUNNING"
    property bool scanStarting: backend.activities.libraryScanStarting || false
    property bool rematching: backend.activities.libraryRematching || false
    property bool libraryLoading: backend.activities.libraryLoading || false
    background: Rectangle { color: Theme.canvas }

    header: ColumnLayout {
        anchors.leftMargin: Metrics.pageMargin(root.width); anchors.rightMargin: Metrics.pageMargin(root.width); spacing: Metrics.space2
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                Label { text: "媒体库审核"; color: Theme.textPrimary; font.pixelSize: Typography.pageTitle; font.weight: Typography.semibold }
                StatusBadge { text: "扫描 · " + (backend.scanStatus.status || "未知"); status: backend.scanStatus.status || "" }
            }
            Item { Layout.fillWidth: true }
            AppButton {
                text: root.rematching ? "正在重新匹配…" : "重新匹配待审核"
                iconName: "refresh-cw"
                enabled: !root.rematching && !root.scanStarting && !root.scanRunning && !root.libraryLoading
                onClicked: backend.rematchReview()
            }
            AppButton {
                text: root.scanStarting || root.scanRunning ? "正在扫描…" : "扫描媒体库"
                iconName: "scan-search"
                variant: "primary"
                enabled: !root.scanStarting && !root.rematching && !root.scanRunning && !root.libraryLoading
                onClicked: backend.startLibraryScan()
            }
        }
        RowLayout {
            Repeater {
                model: [
                    { key: "needs_review", label: "待审核" }, { key: "automatic", label: "自动匹配" },
                    { key: "manually_linked", label: "人工关联" }, { key: "duplicates", label: "重复" },
                    { key: "missing", label: "缺失" }, { key: "ignored", label: "已忽略" }
                ]
                delegate: AppTab {
                    required property var modelData
                    text: modelData.label + " (" + ((backend.review[modelData.key] || []).length) + ")"
                    selected: root.category === modelData.key
                    onClicked: root.category = modelData.key
                }
            }
        }
        RowLayout {
            visible: root.category === "needs_review"
            Label { text: "人工关联"; color: Theme.textSecondary; font.pixelSize: Typography.label; font.weight: Typography.medium }
            TextField {
                id: subjectSearch
                Layout.preferredWidth: 260
                placeholderText: "输入 Subject 中文名、原名或别名"
                onTextEdited: {
                    root.selectedSubjectId = -1
                    root.selectedSubjectName = ""
                    root.selectedEpisodeId = -1
                    subjectSearchTimer.restart()
                }
            }
            Timer {
                id: subjectSearchTimer
                interval: 300
                repeat: false
                onTriggered: backend.searchLibrarySubjects(subjectSearch.text)
            }
            ComboBox {
                id: subjectPicker
                Layout.preferredWidth: 360
                model: backend.librarySubjectMatches
                textRole: "display_label"
                enabled: backend.librarySubjectMatches.length > 0
                displayText: root.selectedSubjectId > 0
                    ? root.selectedSubjectName
                    : (subjectSearch.text.trim().length === 0
                        ? "先输入标题"
                        : (backend.librarySubjectMatches.length > 0
                            ? "选择匹配结果（" + backend.librarySubjectMatches.length + "）"
                            : "没有匹配结果"))
                onActivated: {
                    const selected = backend.librarySubjectMatches[currentIndex]
                    root.selectedSubjectId = selected.id
                    root.selectedSubjectName = selected.display_name
                    subjectSearch.text = selected.display_name
                    backend.loadSubject(root.selectedSubjectId)
                    root.selectedEpisodeId = -1
                }
            }
            ComboBox {
                id: episodePicker
                Layout.preferredWidth: 260
                model: backend.episodes
                textRole: "display_number"
                enabled: root.selectedSubjectId > 0 && backend.episodes.length > 0
                displayText: root.selectedEpisodeId > 0 && currentIndex >= 0 && backend.episodes[currentIndex]
                    ? "第 " + backend.episodes[currentIndex].display_number + " 集 · "
                        + (backend.episodes[currentIndex].name_cn || backend.episodes[currentIndex].name)
                    : (root.selectedSubjectId > 0 ? "选择章节" : "先选择 Subject")
                onActivated: root.selectedEpisodeId = backend.episodes[currentIndex].id
            }
        }
    }

    ListView {
        id: fileList
        anchors.fill: parent
        anchors.leftMargin: Metrics.pageMargin(root.width); anchors.rightMargin: Metrics.pageMargin(root.width); anchors.topMargin: Metrics.space6
        bottomMargin: Metrics.space6
        spacing: Metrics.space2
        clip: true
        reuseItems: true
        cacheBuffer: 192
        model: root.currentFiles
        delegate: Rectangle {
                    required property var modelData
                    width: fileList.width
                    height: 96
                    radius: Metrics.radiusS; color: fileHover.hovered ? Theme.surfaceHover : Theme.surface
                    border.width: 1; border.color: fileHover.hovered ? Theme.border : Theme.borderSoft
                    HoverHandler { id: fileHover }
                    RowLayout {
                        anchors.fill: parent; anchors.margins: Metrics.space4; spacing: Metrics.space3
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: Metrics.space1
                            Label { Layout.fillWidth: true; text: modelData.filename; color: Theme.textPrimary; font.weight: Typography.semibold; elide: Text.ElideMiddle }
                            Label { Layout.fillWidth: true; text: modelData.subject ? modelData.subject.name : "未关联条目"; color: modelData.subject ? Theme.accent : Theme.warning; elide: Text.ElideRight }
                            Label { Layout.fillWidth: true; text: (modelData.review_reason || modelData.subject_mapping_source || "-") + "  ·  " + modelData.path; color: Theme.textTertiary; font.pixelSize: Typography.meta; elide: Text.ElideMiddle }
                        }
                        AppButton { visible: root.category === "needs_review"; text: "应用关联"; variant: "primary"; enabled: root.selectedSubjectId > 0 && root.selectedEpisodeId > 0 && !(backend.activities.libraryMutating || false); onClicked: backend.matchFile(modelData.id, root.selectedSubjectId, [root.selectedEpisodeId]) }
                        IconButton { iconName: "more-horizontal"; tooltip: "更多操作"; enabled: !(backend.activities.libraryMutating || false); onClicked: fileMenu.open(); Menu { id: fileMenu; MenuItem { visible: root.category === "needs_review"; text: "重新解析"; onTriggered: backend.reparseFile(modelData.id) } MenuItem { visible: root.category === "manually_linked"; text: "解除关联"; onTriggered: backend.unlinkFile(modelData.id) } MenuItem { text: root.category === "ignored" ? "恢复" : "忽略"; onTriggered: backend.ignoreFile(modelData.id, root.category !== "ignored") } } }
                    }
        }
    }
    EmptyState { visible: root.currentFiles.length === 0 && !root.libraryLoading; anchors.centerIn: parent; width: Math.min(520, parent.width - Metrics.space12); title: "此分类暂无文件"; detail: root.category === "needs_review" ? "扫描后未能自动匹配的文件会出现在这里。" : "切换其他分类查看媒体记录。"; iconName: "folder-search" }
    BusyIndicator { anchors.centerIn: parent; running: root.libraryLoading && Object.keys(backend.review).length === 0 }
    Component.onCompleted: backend.loadLibrary()
}
