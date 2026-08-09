import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: root
    required property int subjectId
    signal back()
    signal playEpisode(int id, bool fromStart, var episodes, string title)
    property var downloadEpisode: null
    property var searchEpisode: null

    function formatSize(bytes) {
        if (!bytes)
            return "大小未知"
        const units = ["B", "KiB", "MiB", "GiB", "TiB"]
        let value = Number(bytes)
        let unit = 0
        while (value >= 1024 && unit < units.length - 1) {
            value /= 1024
            unit += 1
        }
        return value.toFixed(value >= 10 || unit === 0 ? 0 : 1) + " " + units[unit]
    }
    function jobForEpisode(episodeId) {
        for (let i = 0; i < backend.downloads.length; ++i) {
            if ((backend.downloads[i].episode_ids || []).indexOf(episodeId) >= 0)
                return backend.downloads[i]
        }
        return null
    }
    background: Rectangle { color: "#0b1018" }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 22
            anchors.margins: 30

            Button { text: "‹ 返回条目"; flat: true; onClicked: root.back() }
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 300
                spacing: 28
                Image {
                    Layout.preferredWidth: 200; Layout.fillHeight: true
                    source: backend.subject.image_url || ""
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Label { Layout.fillWidth: true; text: backend.subject.display_name || "加载中…"; color: "#f2f5f8"; font.pixelSize: 32; font.weight: Font.Bold; wrapMode: Text.Wrap }
                    Label { text: (backend.subject.air_date || "日期未知") + "  ·  " + (backend.subject.platform || "平台未知"); color: "#93a1b2" }
                    Label { Layout.fillWidth: true; Layout.fillHeight: true; text: backend.subject.summary || "暂无简介"; color: "#c8d0da"; wrapMode: Text.Wrap; maximumLineCount: 8; elide: Text.ElideRight }
                    Button {
                        property var readyEpisode: {
                            for (let i = 0; i < backend.episodes.length; ++i)
                                if (backend.episodes[i].local_status === "READY" && !backend.episodes[i].watched) return backend.episodes[i]
                            for (let j = 0; j < backend.episodes.length; ++j)
                                if (backend.episodes[j].local_status === "READY") return backend.episodes[j]
                            return null
                        }
                        text: readyEpisode && readyEpisode.playback && readyEpisode.playback.position_seconds > 0 ? "继续观看" : "播放"
                        highlighted: true
                        enabled: readyEpisode !== null
                        onClicked: root.playEpisode(readyEpisode.id, false, backend.episodes, backend.subject.display_name)
                    }
                }
            }
            Label { text: "剧集"; color: "#f2f5f8"; font.pixelSize: 22; font.weight: Font.DemiBold }
            Label {
                visible: (backend.subject.relations || []).length > 0
                Layout.fillWidth: true
                text: "相关条目：" + (backend.subject.relations || []).map(item => (item.name_cn || item.name) + "（" + item.relation_type + "）").join(" · ")
                color: "#93a1b2"
                wrapMode: Text.Wrap
            }
            Repeater {
                model: backend.episodes
                delegate: Rectangle {
                    required property var modelData
                    property var downloadJob: root.jobForEpisode(modelData.id)
                    Layout.fillWidth: true
                    Layout.preferredHeight: 68
                    radius: 8
                    color: "#121a25"
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 12; spacing: 14
                        Label { text: modelData.episode_type + " " + modelData.display_number; color: "#72d5b4"; Layout.preferredWidth: 90 }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 3
                            Label { Layout.fillWidth: true; text: modelData.name_cn || modelData.name || "未命名"; color: "#f2f5f8"; elide: Text.ElideRight }
                            Label { text: (modelData.air_date || "日期未知") + "  ·  " + modelData.local_status; color: "#93a1b2"; font.pixelSize: 12 }
                        }
                        ProgressBar { Layout.preferredWidth: 110; visible: modelData.playback !== null && modelData.playback !== undefined; value: modelData.playback ? modelData.playback.progress_ratio : 0 }
                        Button { text: modelData.watched ? "设为未看" : "设为已看"; flat: true; onClicked: backend.markWatched(modelData.id, !modelData.watched) }
                        Label {
                            visible: downloadJob !== null && downloadJob.state !== "IMPORTED"
                            text: downloadJob ? downloadJob.state + " " + Math.round(downloadJob.progress * 100) + "%" : ""
                            color: downloadJob && downloadJob.state === "FAILED" ? "#ff9b9b" : "#72d5b4"
                            font.pixelSize: 12
                        }
                        Button {
                            text: "搜索"
                            visible: modelData.local_status !== "READY" && downloadJob === null
                            enabled: !backend.busy
                            onClicked: {
                                root.searchEpisode = modelData
                                candidateDialog.open()
                                backend.searchReleases(modelData.id)
                            }
                        }
                        Button {
                            text: "磁力"
                            visible: modelData.local_status !== "READY" && downloadJob === null
                            onClicked: {
                                root.downloadEpisode = modelData
                                magnetInput.text = ""
                                downloadDialog.open()
                            }
                        }
                        Button { text: modelData.playback && modelData.playback.position_seconds > 0 ? "继续" : "播放"; enabled: modelData.local_status === "READY"; onClicked: root.playEpisode(modelData.id, false, backend.episodes, backend.subject.display_name) }
                        Button { text: "从头"; enabled: modelData.local_status === "READY"; flat: true; onClicked: root.playEpisode(modelData.id, true, backend.episodes, backend.subject.display_name) }
                    }
                }
            }
            Label { visible: backend.episodes.length === 0 && !backend.busy; text: "暂无章节数据"; color: "#93a1b2" }
            Item { Layout.preferredHeight: 24 }
        }
    }
    Dialog {
        id: downloadDialog
        anchors.centerIn: parent
        width: Math.min(680, root.width - 60)
        title: root.downloadEpisode ? "下载 Episode " + root.downloadEpisode.display_number : "新建下载"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: {
            if (root.downloadEpisode) backend.addDownload(root.downloadEpisode.id, magnetInput.text)
        }
        contentItem: ColumnLayout {
            spacing: 10
            Label { Layout.fillWidth: true; text: "粘贴完整 magnet 或 BTIH 特征码，系统会直接下载到媒体库并关联此 Episode。"; wrapMode: Text.Wrap }
            TextArea {
                id: magnetInput
                Layout.fillWidth: true
                Layout.preferredHeight: 110
                placeholderText: "magnet:?xt=urn:btih:… 或 40 位特征码"
                wrapMode: TextEdit.WrapAnywhere
            }
        }
    }
    Dialog {
        id: candidateDialog
        anchors.centerIn: parent
        width: Math.min(900, root.width - 60)
        height: Math.min(720, root.height - 60)
        title: root.searchEpisode ? "Episode " + root.searchEpisode.display_number + " 资源候选" : "资源候选"
        modal: true
        standardButtons: Dialog.Close

        contentItem: ColumnLayout {
            spacing: 12
            Label {
                Layout.fillWidth: true
                text: backend.releaseSearch.id
                    ? "Provider：" + backend.releaseSearch.provider + " · "
                        + (backend.releaseSearch.candidates || []).length + " 个可选候选"
                    : "正在搜索配置的 RSS…"
                color: "#93a1b2"
            }
            BusyIndicator {
                Layout.alignment: Qt.AlignHCenter
                running: !backend.releaseSearch.id && backend.busy
                visible: running
            }
            Label {
                Layout.fillWidth: true
                visible: backend.releaseSearch.id && (backend.releaseSearch.candidates || []).length === 0
                text: "没有满足匹配条件的候选资源"
                color: "#93a1b2"
                horizontalAlignment: Text.AlignHCenter
            }
            ScrollView {
                id: candidateScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: candidateScroll.availableWidth
                    spacing: 10
                    Repeater {
                        model: backend.releaseSearch.candidates || []
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredHeight: candidateContent.implicitHeight + 24
                            radius: 8
                            color: "#121a25"
                            ColumnLayout {
                                id: candidateContent
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 8
                                RowLayout {
                                    Layout.fillWidth: true
                                    Label {
                                        Layout.fillWidth: true
                                        text: modelData.title
                                        color: "#f2f5f8"
                                        font.weight: Font.DemiBold
                                        wrapMode: Text.Wrap
                                    }
                                    Label {
                                        text: modelData.decision + " · " + Math.round(modelData.score)
                                        color: modelData.decision === "AUTO_ACCEPT" ? "#72d5b4"
                                            : "#ffd18a"
                                    }
                                }
                                Label {
                                    Layout.fillWidth: true
                                    property var parsed: modelData.parsed || ({})
                                    text: (parsed.release_group || "字幕组未知") + " · "
                                        + (parsed.resolution || "分辨率未知") + " · "
                                        + (parsed.codec || "编码未知") + " · "
                                        + (parsed.subtitle_language || "语言未知") + " · "
                                        + root.formatSize(parsed.size_bytes)
                                    color: "#93a1b2"
                                    wrapMode: Text.Wrap
                                }
                                Label {
                                    Layout.fillWidth: true
                                    visible: (modelData.match_reasons || []).length > 0
                                    text: "匹配：" + (modelData.match_reasons || []).join("；")
                                    color: "#72d5b4"
                                    wrapMode: Text.Wrap
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Item { Layout.fillWidth: true }
                                    Button {
                                        text: modelData.download_job_id ? "已创建下载" : "选择并下载"
                                        highlighted: true
                                        enabled: modelData.downloadable && !modelData.download_job_id && !backend.busy
                                        onClicked: backend.downloadReleaseCandidate(modelData.id)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    BusyIndicator { anchors.centerIn: parent; running: backend.busy && backend.subject.id !== subjectId }
    Component.onCompleted: { backend.loadSubject(subjectId); backend.setDownloadPolling(true) }
    onVisibleChanged: backend.setDownloadPolling(visible)
}
