import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: root
    property string category: "needs_review"
    property int selectedSubjectId: -1
    property int selectedEpisodeId: -1
    property string selectedSubjectName: ""
    property var currentFiles: backend.review[category] || []
    background: Rectangle { color: "#0b1018" }

    header: ColumnLayout {
        anchors.leftMargin: 30; anchors.rightMargin: 30; spacing: 12
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                Label { text: "媒体库审核"; color: "#f2f5f8"; font.pixelSize: 30; font.weight: Font.DemiBold }
                Label { text: "扫描状态：" + (backend.scanStatus.status || "未知"); color: "#93a1b2" }
            }
            Item { Layout.fillWidth: true }
            Button { text: "重新匹配待审核"; enabled: !backend.busy; onClicked: backend.rematchReview() }
            Button { text: "扫描媒体库"; highlighted: true; enabled: !backend.busy; onClicked: backend.startLibraryScan() }
        }
        RowLayout {
            Repeater {
                model: [
                    { key: "needs_review", label: "待审核" }, { key: "automatic", label: "自动匹配" },
                    { key: "manually_linked", label: "人工关联" }, { key: "duplicates", label: "重复" },
                    { key: "missing", label: "缺失" }, { key: "ignored", label: "已忽略" }
                ]
                delegate: Button {
                    required property var modelData
                    text: modelData.label + " (" + ((backend.review[modelData.key] || []).length) + ")"
                    flat: root.category !== modelData.key
                    highlighted: root.category === modelData.key
                    onClicked: root.category = modelData.key
                }
            }
        }
        RowLayout {
            visible: root.category === "needs_review"
            Label { text: "人工关联："; color: "#c8d0da" }
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

    ScrollView {
        anchors.fill: parent
        anchors.margins: 28
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 10
            Repeater {
                model: root.currentFiles
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 96
                    radius: 8; color: "#121a25"
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 14; spacing: 12
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            Label { Layout.fillWidth: true; text: modelData.filename; color: "#f2f5f8"; font.weight: Font.DemiBold; elide: Text.ElideMiddle }
                            Label { Layout.fillWidth: true; text: modelData.subject ? modelData.subject.name : "未关联条目"; color: "#72d5b4"; elide: Text.ElideRight }
                            Label { Layout.fillWidth: true; text: (modelData.review_reason || modelData.subject_mapping_source || "-") + "  ·  " + modelData.path; color: "#93a1b2"; font.pixelSize: 12; elide: Text.ElideMiddle }
                        }
                        Button { visible: root.category === "needs_review"; text: "应用关联"; enabled: root.selectedSubjectId > 0 && root.selectedEpisodeId > 0; onClicked: backend.matchFile(modelData.id, root.selectedSubjectId, [root.selectedEpisodeId]) }
                        Button { visible: root.category === "needs_review"; text: "重新解析"; flat: true; onClicked: backend.reparseFile(modelData.id) }
                        Button { visible: root.category === "manually_linked"; text: "解除关联"; onClicked: backend.unlinkFile(modelData.id) }
                        Button { text: root.category === "ignored" ? "恢复" : "忽略"; flat: true; onClicked: backend.ignoreFile(modelData.id, root.category !== "ignored") }
                    }
                }
            }
            Label { visible: root.currentFiles.length === 0 && !backend.busy; text: "此分类暂无文件"; color: "#93a1b2" }
        }
    }
    BusyIndicator { anchors.centerIn: parent; running: backend.busy }
    Component.onCompleted: backend.loadLibrary()
}
