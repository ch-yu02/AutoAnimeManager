import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import AutoAnime 1.0

Page {
    id: root
    objectName: "subjectDetailPage"
    required property int subjectId
    property int correctionEpisodeId: -1
    property string correctionEpisodeDisplayNumber: ""
    property string correctionDownloadJobId: ""
    signal back()
    signal playEpisode(int id, bool fromStart, var episodes, string title)
    property var downloadEpisode: null
    property var searchEpisode: null
    property string replacementDownloadJobId: ""
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
    function episodeNumberText(type, number) {
        if (type === "MAIN") return "第 " + number + " 集"
        const labels = {
            "SPECIAL": "特别篇", "SP": "特别篇", "OP": "片头",
            "ED": "片尾", "PV": "预告", "OTHER": "其他"
        }
        return (labels[type] || "附加内容") + (number ? " " + number : "")
    }
    function downloadStateText(state) {
        const labels = {
            "CREATED": "等待下载", "QUEUED": "等待下载", "DOWNLOADING": "下载中",
            "STALLED": "已暂停", "COMPLETED": "正在整理", "IMPORTING": "正在整理",
            "IMPORTED": "已完成", "FAILED": "下载失败"
        }
        return labels[state] || "处理中"
    }
    function localStatusText(status) {
        if (status === "READY") return "可播放"
        if (status === "MISSING") return "暂无文件"
        return "正在处理"
    }
    function cleanupBlockerText(value) {
        let text = String(value || "")
        if (text === "Subject 尚未确认完结") return "条目尚未完结"
        if (text === "没有 MAIN Episode") return "没有正片剧集"
        if (text === "部分 MAIN Episode 缺少完成时间") return "部分正片缺少观看完成时间"
        if (text === "存在 active download") return "此条目仍有下载任务"
        if (text === "存在 unresolved mapping") return "部分媒体文件尚未完成匹配"
        return text.replace(" 个 MAIN Episode 未看", " 集正片未看")
    }
    function relationText(value) {
        const labels = {
            "PREQUEL": "前传", "SEQUEL": "续集", "SIDE_STORY": "番外篇",
            "SAME_SETTING": "相同世界观", "ALTERNATIVE": "不同演绎",
            "SUMMARY": "总集篇", "SPIN_OFF": "衍生", "OTHER": "相关"
        }
        return labels[value] || value || "相关"
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
                text: "相关条目：" + (backend.subject.relations || []).map(item => (item.name_cn || item.name) + "（" + root.relationText(item.relation_type) + "）").join(" · ")
                color: Theme.textTertiary
                font.pixelSize: Typography.meta
                wrapMode: Text.Wrap
            }
            Repeater {
                model: backend.episodes
                delegate: EpisodeRow {
                    required property var modelData
                    property var downloadJob: root.jobForEpisode(modelData.id)
                    numberText: root.episodeNumberText(modelData.episode_type, modelData.display_number)
                    title: modelData.name_cn || modelData.name || "未命名"
                    metadata: modelData.air_date || "日期未知"
                    statusText: downloadJob && downloadJob.state !== "IMPORTED"
                        ? root.downloadStateText(downloadJob.state) + " " + Math.round(downloadJob.progress * 100) + "%"
                        : (modelData.watched ? "已看" : root.localStatusText(modelData.local_status))
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
                        root.replacementDownloadJobId = ""
                        candidateDialog.open()
                        backend.searchReleases(modelData.id)
                    }
                    onDebugClicked: {
                        root.searchEpisode = modelData
                        root.replacementDownloadJobId = ""
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
            EmptyState { visible: backend.episodes.length === 0 && !(backend.activities.subjectLoading || false); Layout.fillWidth: true; title: "暂无剧集信息"; detail: "同步 Bangumi 后，这里会显示剧集列表。"; iconName: "inbox" }

            SettingsSection {
                title: "文件管理"
                description: backend.cleanupEligibility.eligible
                    ? "本条目可移入隔离区，预计释放 " + root.formatSize(backend.cleanupEligibility.bytes_total)
                    : "暂不可清理：" + (backend.cleanupEligibility.blockers || []).map(item => root.cleanupBlockerText(item)).join("；")
                CheckBox {
                    text: "始终保留本条目的媒体文件"
                    checked: backend.subject.keep_forever || false
                    enabled: backend.subject.id === root.subjectId && !(backend.activities.subjectKeepSaving || false)
                    onClicked: backend.setSubjectKeepForever(root.subjectId, checked)
                }
                AppButton {
                    text: "移入隔离区"
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
        title: root.downloadEpisode ? "下载第 " + root.downloadEpisode.display_number + " 集" : "新建下载"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: {
            if (root.downloadEpisode) backend.addDownload(root.downloadEpisode.id, magnetInput.text)
        }
        contentItem: ColumnLayout {
            spacing: Metrics.space3
            Label { Layout.fillWidth: true; text: "粘贴磁力链接或 BTIH 特征码，文件会直接保存到媒体库。"; wrapMode: Text.Wrap }
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
        title: root.searchEpisode ? "第 " + root.searchEpisode.display_number + " 集的可用资源" : "可用资源"
        modal: true
        standardButtons: Dialog.Close

        contentItem: ColumnLayout {
            spacing: Metrics.space3
            Label {
                Layout.fillWidth: true
                visible: root.replacementDownloadJobId.length > 0
                text: "选择新片源后，旧文件会保留到新文件成功入库，再由系统自动删除。"
                color: Theme.textSecondary
                wrapMode: Text.Wrap
            }
            Label {
                Layout.fillWidth: true
                text: backend.releaseSearch.id
                    ? "找到 " + (backend.releaseSearch.candidates || []).length + " 个可下载资源"
                    : "正在搜索资源…"
                color: Theme.textTertiary
            }
            RowLayout {
                Layout.fillWidth: true
                visible: root.showAutoSelectionDebug
                Label {
                    Layout.fillWidth: true
                    text: "预览自动下载会选择的资源，不会开始下载。"
                    color: Theme.textTertiary
                    wrapMode: Text.Wrap
                }
                AppButton {
                    text: "预览自动选择"
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
                text: "没有找到合适的资源"
                color: Theme.textTertiary
                horizontalAlignment: Text.AlignHCenter
            }
            ListView {
                id: candidateScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: Metrics.space3
                clip: true
                reuseItems: true
                cacheBuffer: 320
                model: backend.releaseSearch.candidates || []
                delegate: Rectangle {
                            required property var modelData
                            width: candidateScroll.width
                            height: candidateContent.implicitHeight + 24
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
                                    text: "自动下载会优先选择此资源"
                                    color: Theme.warning
                                    font.weight: Font.Bold
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Item { Layout.fillWidth: true }
                                    AppButton {
                                        text: modelData.download_job_id ? "已加入下载"
                                            : (root.replacementDownloadJobId.length > 0 ? "选择为新片源" : "选择并下载")
                                        variant: "primary"
                                        enabled: modelData.downloadable && !modelData.download_job_id
                                            && !(backend.activities.releaseDownloading || false)
                                        onClicked: backend.downloadReleaseCandidate(
                                            modelData.id, root.replacementDownloadJobId
                                        )
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
        if (root.correctionEpisodeId > 0 && root.correctionDownloadJobId.length > 0) {
            root.searchEpisode = {
                id: root.correctionEpisodeId,
                display_number: root.correctionEpisodeDisplayNumber
            }
            root.replacementDownloadJobId = root.correctionDownloadJobId
            candidateDialog.open()
            backend.searchReleases(root.correctionEpisodeId)
        }
    }
    onVisibleChanged: backend.setDownloadPolling("subjectDetail", visible)
    Component.onDestruction: backend.setDownloadPolling("subjectDetail", false)
}
