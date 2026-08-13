import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import AutoAnime 1.0

Page {
    id: root
    objectName: "subjectDetailPage"
    required property int subjectId
    signal back()
    signal playEpisode(int id, bool fromStart, var episodes, string title)
    property var downloadEpisode: null
    property var searchEpisode: null
    property bool showAutoSelectionDebug:
        !!(backend.settings.release_search || {}).debug_auto_selection_enabled
    property var collectionOptions: [
        { text: "想看", value: "WISH" },
        { text: "在看", value: "DOING" },
        { text: "看过", value: "COLLECTED" },
        { text: "搁置", value: "ON_HOLD" },
        { text: "抛弃", value: "DROPPED" }
    ]

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
    function collectionIndex(value) {
        for (let i = 0; i < collectionOptions.length; ++i)
            if (collectionOptions[i].value === value) return i
        return -1
    }
    function collectionText(value) {
        const index = collectionIndex(value)
        return index >= 0 ? collectionOptions[index].text : "未收藏"
    }
    background: Rectangle { color: Theme.canvas }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        ColumnLayout {
            x: Metrics.pageMargin(root.width)
            width: Math.max(0, root.width - Metrics.pageMargin(root.width) * 2)
            spacing: Metrics.space8

            AppButton { text: "返回条目"; iconName: "arrow-left"; variant: "ghost"; onClicked: root.back() }
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 283
                spacing: Metrics.space8
                RoundedImage {
                    Layout.preferredWidth: 200; Layout.preferredHeight: 283
                    source: backend.subject.image_url || ""
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    radius: Metrics.radiusM
                    cornerColor: Theme.canvas
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Metrics.space3
                    Label { Layout.fillWidth: true; text: backend.subject.display_name || "加载中…"; color: Theme.textPrimary; font.pixelSize: Typography.display; font.weight: Typography.bold; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight }
                    Label { text: (backend.subject.air_date || "日期未知") + "  ·  " + (backend.subject.platform || "平台未知"); color: Theme.textTertiary; font.pixelSize: Typography.meta }
                    RowLayout {
                        Label { text: "收藏状态"; color: Theme.textTertiary; font.pixelSize: Typography.meta }
                        ComboBox {
                            Layout.preferredWidth: 144
                            model: root.collectionOptions
                            textRole: "text"
                            valueRole: "value"
                            currentIndex: root.collectionIndex(backend.subject.collection_type)
                            displayText: root.collectionText(backend.subject.collection_type)
                            enabled: backend.subject.id === root.subjectId
                                && !(backend.activities.subjectCollectionSaving || false)
                            onActivated: {
                                const selected = root.collectionOptions[currentIndex].value
                                if (selected !== backend.subject.collection_type)
                                    backend.setSubjectCollection(root.subjectId, selected)
                            }
                        }
                    }
                    Label { Layout.fillWidth: true; Layout.fillHeight: true; text: backend.subject.summary || "暂无简介"; color: Theme.textSecondary; font.pixelSize: Typography.body; wrapMode: Text.Wrap; maximumLineCount: 6; elide: Text.ElideRight }
                    AppButton {
                        property var readyEpisode: {
                            for (let i = 0; i < backend.episodes.length; ++i)
                                if (backend.episodes[i].local_status === "READY" && !backend.episodes[i].watched) return backend.episodes[i]
                            for (let j = 0; j < backend.episodes.length; ++j)
                                if (backend.episodes[j].local_status === "READY") return backend.episodes[j]
                            return null
                        }
                        text: readyEpisode && readyEpisode.playback && readyEpisode.playback.position_seconds > 0 ? "继续观看" : "播放"
                        variant: "primary"
                        iconName: "play"
                        enabled: readyEpisode !== null
                        onClicked: root.playEpisode(readyEpisode.id, false, backend.episodes, backend.subject.display_name)
                    }
                }
            }
            SectionHeader { Layout.fillWidth: true; title: "剧集"; detail: backend.episodes.length + " 集" }
            Label {
                visible: (backend.subject.relations || []).length > 0
                Layout.fillWidth: true
                text: "相关条目：" + (backend.subject.relations || []).map(item => (item.name_cn || item.name) + "（" + item.relation_type + "）").join(" · ")
                color: Theme.textTertiary
                font.pixelSize: Typography.meta
                wrapMode: Text.Wrap
            }
            Repeater {
                model: backend.episodes
                delegate: EpisodeRow {
                    required property var modelData
                    property var downloadJob: root.jobForEpisode(modelData.id)
                    numberText: modelData.episode_type + " " + modelData.display_number
                    title: modelData.name_cn || modelData.name || "未命名"
                    metadata: modelData.air_date || "日期未知"
                    statusText: downloadJob && downloadJob.state !== "IMPORTED"
                        ? downloadJob.state + " " + Math.round(downloadJob.progress * 100) + "%"
                        : (modelData.watched ? "已看" : modelData.local_status)
                    status: downloadJob && downloadJob.state !== "IMPORTED" ? downloadJob.state : modelData.local_status
                    progress: modelData.playback ? modelData.playback.progress_ratio : 0
                    watched: modelData.watched
                    watchedBusy: backend.activities.episodeWatchedSaving || false
                    playable: modelData.local_status === "READY"
                    searchable: modelData.local_status !== "READY" && downloadJob === null
                    debugVisible: root.showAutoSelectionDebug
                    onPlayClicked: root.playEpisode(modelData.id, false, backend.episodes, backend.subject.display_name)
                    onFromStartClicked: root.playEpisode(modelData.id, true, backend.episodes, backend.subject.display_name)
                    onToggleWatchedClicked: backend.markWatched(modelData.id, !modelData.watched)
                    onSearchClicked: {
                        root.searchEpisode = modelData
                        candidateDialog.open()
                        backend.searchReleases(modelData.id)
                    }
                    onDebugClicked: {
                        root.searchEpisode = modelData
                        candidateDialog.open()
                        backend.debugSearchReleases(modelData.id)
                    }
                    onMagnetClicked: {
                        root.downloadEpisode = modelData
                        magnetInput.text = ""
                        downloadDialog.open()
                    }
                }
            }
            EmptyState { visible: backend.episodes.length === 0 && !(backend.activities.subjectLoading || false); Layout.fillWidth: true; title: "暂无章节数据"; detail: "完成 Bangumi 同步后再查看。"; iconName: "inbox" }

            SettingsSection {
                title: "媒体维护"
                description: backend.cleanupEligibility.eligible
                    ? "本条目可移入隔离区，预计释放 " + root.formatSize(backend.cleanupEligibility.bytes_total)
                    : "暂不可清理：" + (backend.cleanupEligibility.blockers || []).join("；")
                CheckBox {
                    text: "永久保留本条目，不参与自动清理"
                    checked: backend.subject.keep_forever || false
                    enabled: backend.subject.id === root.subjectId && !(backend.activities.subjectKeepSaving || false)
                    onClicked: backend.setSubjectKeepForever(root.subjectId, checked)
                }
                AppButton {
                    text: "手动移入隔离区"
                    iconName: "archive-restore"
                    visible: backend.cleanupEligibility.eligible || false
                    enabled: !(backend.activities.cleanupMutating || false)
                    onClicked: backend.quarantineSubject(root.subjectId)
                }
            }
            Item { Layout.preferredHeight: Metrics.space6 }
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
            spacing: Metrics.space3
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
            spacing: Metrics.space3
            Label {
                Layout.fillWidth: true
                text: backend.releaseSearch.id
                    ? "Provider：" + backend.releaseSearch.provider + " · "
                        + (backend.releaseSearch.candidates || []).length + " 个可选候选"
                    : "正在搜索配置的 RSS…"
                color: Theme.textTertiary
            }
            RowLayout {
                Layout.fillWidth: true
                visible: root.showAutoSelectionDebug
                Label {
                    Layout.fillWidth: true
                    text: "调试只标注正式自动流程会选择的候选，不会创建下载任务。"
                    color: Theme.textTertiary
                    wrapMode: Text.Wrap
                }
                AppButton {
                    text: "调试自动选择"
                    enabled: backend.releaseSearch.id && !(backend.activities.releaseDebugSelecting || false)
                    onClicked: backend.debugAutoSelect(backend.releaseSearch.id)
                }
            }
            BusyIndicator {
                Layout.alignment: Qt.AlignHCenter
                running: !backend.releaseSearch.id && (backend.activities.releaseSearching || false)
                visible: running
            }
            Label {
                Layout.fillWidth: true
                visible: backend.releaseSearch.id && (backend.releaseSearch.candidates || []).length === 0
                text: "没有满足匹配条件的候选资源"
                color: Theme.textTertiary
                horizontalAlignment: Text.AlignHCenter
            }
            ScrollView {
                id: candidateScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: candidateScroll.availableWidth
                    spacing: Metrics.space3
                    Repeater {
                        model: backend.releaseSearch.candidates || []
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredHeight: candidateContent.implicitHeight + 24
                            radius: Metrics.radiusS
                            color: candidateHover.hovered ? Theme.surfaceHover : Theme.surface
                            border.width: 1
                            border.color: candidateHover.hovered ? Theme.border : Theme.borderSoft
                            HoverHandler { id: candidateHover }
                            ColumnLayout {
                                id: candidateContent
                                anchors.fill: parent
                                anchors.margins: Metrics.space3
                                spacing: Metrics.space2
                                RowLayout {
                                    Layout.fillWidth: true
                                    Label {
                                        Layout.fillWidth: true
                                        text: modelData.title
                                        color: Theme.textPrimary
                                        font.weight: Font.DemiBold
                                        wrapMode: Text.Wrap
                                    }
                                    Label {
                                        text: modelData.decision + " · " + Math.round(modelData.score)
                                        color: modelData.decision === "AUTO_ACCEPT" ? Theme.accent
                                            : Theme.warning
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
                                    color: Theme.textTertiary
                                    wrapMode: Text.Wrap
                                }
                                Label {
                                    Layout.fillWidth: true
                                    visible: root.showAutoSelectionDebug && !!modelData.debug_selected_at
                                    text: "自动选择调试命中（未下载）"
                                    color: Theme.warning
                                    font.weight: Font.Bold
                                }
                                Label {
                                    Layout.fillWidth: true
                                    visible: (modelData.match_reasons || []).length > 0
                                    text: "匹配：" + (modelData.match_reasons || []).join("；")
                                    color: Theme.accent
                                    wrapMode: Text.Wrap
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Item { Layout.fillWidth: true }
                                    AppButton {
                                        text: modelData.download_job_id ? "已创建下载" : "选择并下载"
                                        variant: "primary"
                                        enabled: modelData.downloadable && !modelData.download_job_id
                                            && !(backend.activities.releaseDownloading || false)
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
    BusyIndicator { anchors.centerIn: parent; running: (backend.activities.subjectLoading || false) && backend.subject.id !== subjectId }
    Component.onCompleted: {
        backend.loadSubject(subjectId)
        backend.loadCleanup(subjectId)
        backend.setDownloadPolling("subjectDetail", visible)
    }
    onVisibleChanged: backend.setDownloadPolling("subjectDetail", visible)
    Component.onDestruction: backend.setDownloadPolling("subjectDetail", false)
}
