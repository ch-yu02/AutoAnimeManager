import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import AutoAnime 1.0

Page {
    id: root
    property var config: backend.settings

    function taskNameText(name) {
        const labels = {
            "BangumiSync": "同步 Bangumi",
            "LibraryScan": "扫描媒体库",
            "DemandRefresh": "更新待下载剧集",
            "ReleaseSearch": "搜索可用资源",
            "DownloadMonitor": "更新下载进度",
            "Cleanup": "清理媒体文件",
            "Backup": "备份数据"
        }
        return labels[name] || "后台任务"
    }
    function taskStatusText(status) {
        const labels = {
            "RUNNING": "运行中", "SUCCESS": "已完成", "FAILED": "执行失败",
            "SKIPPED": "已跳过", "CANCELLED": "已取消"
        }
        return labels[status] || "等待执行"
    }
    background: Rectangle { color: Theme.canvas }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        ColumnLayout {
            width: Math.min(parent.width - Metrics.pageMargin(root.width) * 2, 760)
            x: Metrics.pageMargin(root.width)
            spacing: Metrics.space4

            Label { text: "设置"; color: Theme.textPrimary; font.pixelSize: Typography.pageTitle; font.weight: Typography.semibold; Layout.topMargin: Metrics.space6; Layout.bottomMargin: Metrics.space2 }

            SettingsSection {
                title: "外观"
                Label { text: "配色主题"; color: Theme.textSecondary; font.pixelSize: Typography.label }
                ComboBox {
                    id: themePicker
                    Layout.fillWidth: true
                    model: Theme.availableThemes
                    textRole: "label"
                    valueRole: "id"
                    currentIndex: Theme.themeIndex(preferences.themeId)
                    onActivated: preferences.themeId = currentValue
                    delegate: ItemDelegate {
                        required property var modelData
                        width: themePicker.width
                        contentItem: RowLayout {
                            spacing: Metrics.space3
                            Rectangle { Layout.preferredWidth: 20; Layout.preferredHeight: 20; radius: Metrics.radiusS; color: modelData.swatch; border.width: 1; border.color: Theme.border }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: Metrics.space1
                                Label { text: modelData.label; color: Theme.textPrimary; font.weight: Typography.medium }
                                Label { text: modelData.description; color: Theme.textTertiary; font.pixelSize: Typography.meta }
                            }
                        }
                    }
                }
            }

            SettingsSection {
                title: "Bangumi"
                description: "同步收藏和观看记录。"
                Label { text: "用户名"; color: Theme.textSecondary; font.pixelSize: Typography.label }
                TextField { id: username; Layout.fillWidth: true; placeholderText: "Bangumi 用户名" }
                Label { text: "访问令牌（Access Token）"; color: Theme.textSecondary; font.pixelSize: Typography.label }
                TextField { id: token; Layout.fillWidth: true; placeholderText: "留空表示不修改"; echoMode: TextInput.Password }
                RowLayout {
                    AppButton { text: "测试连接"; enabled: !(backend.activities.connectionTesting || false); onClicked: backend.testConnection("bangumi") }
                    AppButton { text: "完整同步"; iconName: "refresh-cw"; enabled: !(backend.activities.bangumiSyncStarting || false); onClicked: backend.startBangumiSync() }
                }
            }

            SettingsSection {
                title: "qBittorrent"
                description: "用于下载动画资源，文件会直接保存到媒体目录。"
                Label { text: "WebUI 地址"; color: Theme.textSecondary; font.pixelSize: Typography.label }
                TextField { id: qbBaseUrl; Layout.fillWidth: true; placeholderText: "http://127.0.0.1:8080" }
                Label { text: "用户名"; color: Theme.textSecondary; font.pixelSize: Typography.label }
                TextField { id: qbUsername; Layout.fillWidth: true; placeholderText: "WebUI 用户名" }
                Label { text: "密码"; color: Theme.textSecondary; font.pixelSize: Typography.label }
                TextField { id: qbPassword; Layout.fillWidth: true; placeholderText: "留空表示不修改"; echoMode: TextInput.Password }
                AppButton { text: "测试连接"; enabled: !(backend.activities.connectionTesting || false); onClicked: backend.testConnection("qbittorrent") }
            }

            SettingsSection {
                title: "自动下载"
                description: "自动下载“在看”条目中已放送、未观看且尚无本地文件的正片。"
                CheckBox { id: autoDownload; text: "启用自动下载" }
            }

            SettingsSection {
                title: "文件清理"
                description: "看完后先移入隔离区，保留期结束后自动删除文件。"
                CheckBox { id: cleanupEnabled; text: "启用自动隔离和到期永久删除" }
                RowLayout {
                    Label { text: "看完后保留天数"; color: Theme.textSecondary; Layout.preferredWidth: 160 }
                    SpinBox { id: retentionDays; from: 0; to: 3650; value: 14 }
                }
                RowLayout {
                    Label { text: "隔离区保留天数"; color: Theme.textSecondary; Layout.preferredWidth: 160 }
                    SpinBox { id: quarantineDays; from: 1; to: 365; value: 7 }
                }
            }

            SettingsSection {
                title: "自动任务"
                description: "在后台定时同步、扫描和整理媒体。"
                Repeater {
                    model: backend.scheduler.tasks || []
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: 56
                        radius: Metrics.radiusS
                        color: Theme.surfaceLow
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: Metrics.space3
                            anchors.rightMargin: Metrics.space2
                            Label { Layout.preferredWidth: 160; text: root.taskNameText(modelData.name); color: Theme.textPrimary; font.weight: Typography.medium }
                            Label {
                                Layout.fillWidth: true
                                text: modelData.latest ? root.taskStatusText(modelData.latest.status) + (modelData.latest.error ? " · " + modelData.latest.error : "") : "尚未执行"
                                color: modelData.latest && modelData.latest.status === "FAILED" ? Theme.danger : Theme.textTertiary
                                font.pixelSize: Typography.meta
                                elide: Text.ElideRight
                            }
                            AppButton { text: modelData.active ? "运行中" : "立即执行"; enabled: !modelData.active && !(backend.activities.schedulerTaskStarting || false); onClicked: backend.runSchedulerTask(modelData.name) }
                        }
                    }
                }
            }

            SettingsSection {
                title: "备份与诊断"
                description: "自动保留最近 "
                    + ((root.config.maintenance || {}).backup_keep_count || 7)
                    + " 份备份；遇到问题时可生成诊断包。"
                RowLayout {
                    AppButton {
                        text: "立即备份"
                        enabled: !(backend.activities.maintenanceRunning || false)
                        onClicked: backend.createBackup()
                    }
                    AppButton {
                        text: "生成诊断包"
                        enabled: !(backend.activities.maintenanceRunning || false)
                        onClicked: backend.createDiagnostics()
                    }
                }
            }

            SettingsSection {
                title: "媒体目录"
                description: "每行填写一个需要扫描的本地目录。"
                TextArea { id: roots; Layout.fillWidth: true; Layout.preferredHeight: 104; placeholderText: "/media/…"; wrapMode: TextEdit.NoWrap }
                AppButton { text: "检查媒体工具"; enabled: !(backend.activities.connectionTesting || false); onClicked: backend.testConnection("ffprobe") }
            }

            SettingsSection {
                title: "播放"
                CheckBox { id: autoPlay; text: "播放完成后自动播放下一集" }
                CheckBox { id: writeback; text: "将观看状态同步到 Bangumi" }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 72
                color: Theme.canvas
                AppButton {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: "保存设置"
                    variant: "primary"
                    enabled: !(backend.activities.settingsSaving || false)
                    onClicked: backend.saveSettings(
                        username.text, token.text, roots.text,
                        qbBaseUrl.text, qbUsername.text, qbPassword.text,
                        autoPlay.checked, writeback.checked, autoDownload.checked,
                        cleanupEnabled.checked, retentionDays.value, quarantineDays.value
                    )
                }
            }
            Item { Layout.preferredHeight: Metrics.space6 }
        }
    }

    Connections {
        target: backend
        function onSettingsChanged() {
            const bangumi = backend.settings.bangumi || {}
            const storage = backend.settings.storage || {}
            const playerSettings = backend.settings.player || {}
            const qbittorrent = backend.settings.qbittorrent || {}
            const cleanup = backend.settings.cleanup || {}
            username.text = bangumi.username || ""
            const values = storage.library_roots || (storage.library_path ? [storage.library_path] : ["data/library"])
            roots.text = values.join("\n")
            autoPlay.checked = playerSettings.auto_play_next || false
            writeback.checked = playerSettings.bangumi_writeback_enabled || false
            autoDownload.checked = (backend.settings.scheduler || {}).auto_download_enabled || false
            cleanupEnabled.checked = cleanup.enabled || false
            retentionDays.value = cleanup.retention_days === undefined ? 14 : cleanup.retention_days
            quarantineDays.value = cleanup.quarantine_days === undefined ? 7 : cleanup.quarantine_days
            qbBaseUrl.text = qbittorrent.base_url || "http://127.0.0.1:8080"
            qbUsername.text = qbittorrent.username || ""
            qbPassword.text = ""
            token.text = ""
        }
    }
    BusyIndicator { anchors.centerIn: parent; running: backend.activities.settingsLoading || false }
    Component.onCompleted: { backend.loadSettings(); backend.loadScheduler() }
}
