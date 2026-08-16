import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import AutoAnime 1.0

ScrollView {
    id: root
    objectName: "homePage"
    signal openSubject(int id)
    signal playEpisode(int id, string title)
    signal openLibrary()
    contentWidth: availableWidth

    ColumnLayout {
        x: Metrics.pageMargin(root.width)
        width: root.availableWidth - Metrics.pageMargin(root.width) * 2
        spacing: Metrics.space8

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Metrics.space6
            Label {
                text: "晚上好"
                color: Theme.textSecondary
                font.family: Typography.family
                font.pixelSize: Typography.body
                font.weight: Typography.medium
            }
            Item { Layout.fillWidth: true }
            BusyIndicator { running: backend.activities.homeLoading || false; visible: running; implicitWidth: 28; implicitHeight: 28 }
            IconButton { iconName: "refresh-cw"; tooltip: "刷新首页"; enabled: !(backend.activities.homeLoading || false); onClicked: backend.loadHome() }
        }

        SectionHeader { title: "继续观看"; detail: backend.continueWatching.length + " 项" }
        Flickable {
            Layout.fillWidth: true
            Layout.preferredHeight: Metrics.continueCardHeight
            contentWidth: continueRow.implicitWidth
            contentHeight: height
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            Row {
                id: continueRow
                spacing: Metrics.space4
                Repeater {
                    model: backend.continueWatching
                    delegate: Rectangle {
                        required property var modelData
                        width: Metrics.continueCardWidth
                        height: Metrics.continueCardHeight
                        radius: Metrics.radiusM
                        color: continueHover.hovered ? Theme.surfaceHover : Theme.surface
                        border.width: 1
                        border.color: continueHover.hovered ? Theme.border : Theme.borderSoft
                        HoverHandler { id: continueHover }
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: Metrics.space3
                            spacing: Metrics.space4
                            RoundedImage {
                                Layout.preferredWidth: Metrics.continuePosterWidth
                                Layout.preferredHeight: Metrics.continuePosterHeight
                                source: modelData.subject.image_url || ""
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                radius: Metrics.radiusS
                                cornerColor: continueHover.hovered ? Theme.surfaceHover : Theme.surface
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: Metrics.space2
                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.subject.name
                                    color: Theme.textPrimary
                                    font.pixelSize: Typography.itemTitle
                                    font.weight: Typography.semibold
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: "第 " + modelData.episode.display_number + " 集"
                                    color: Theme.textSecondary
                                    font.pixelSize: Typography.body
                                    elide: Text.ElideRight
                                }
                                Item { Layout.fillHeight: true }
                                AppProgressBar { Layout.fillWidth: true; value: modelData.progress_ratio || 0 }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Label {
                                        Layout.fillWidth: true
                                        text: Math.round((modelData.progress_ratio || 0) * 100) + "%"
                                        color: Theme.textTertiary
                                        font.family: Typography.monoFamily
                                        font.pixelSize: Typography.meta
                                    }
                                    AppButton {
                                        text: modelData.playable ? "继续观看" : "文件缺失"
                                        iconName: modelData.playable ? "play" : "shield-alert"
                                        variant: "primary"
                                        enabled: modelData.playable
                                        onClicked: root.playEpisode(modelData.episode_id, modelData.subject.name)
                                    }
                                }
                            }
                        }
                    }
                }
                EmptyState {
                    visible: backend.continueWatching.length === 0
                    width: Math.max(Metrics.continueCardWidth, root.availableWidth - Metrics.pageMargin(root.width) * 2)
                    anchors.verticalCenter: parent.verticalCenter
                    title: "暂无续播内容"
                    detail: "开始播放本地 Episode 后，进度会出现在这里。"
                    iconName: "play"
                }
            }
        }

        SectionHeader { title: "正在追"; detail: backend.doingSubjects.length + " 部" }
        Flow {
            Layout.fillWidth: true
            spacing: Metrics.space4
            Repeater {
                model: backend.doingSubjects.slice(0, 12)
                delegate: MediaCard {
                    required property var modelData
                    itemData: modelData
                    onClicked: root.openSubject(modelData.id)
                }
            }
        }

        SectionHeader { title: "最近入库"; detail: backend.recentMedia.length + " 项" }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Metrics.space2
            Repeater {
                model: backend.recentMedia
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 64
                    radius: Metrics.radiusS
                    color: recentHover.hovered ? Theme.surfaceHover : Theme.surfaceLow
                    border.width: 1
                    border.color: recentHover.hovered ? Theme.border : Theme.borderSoft
                    HoverHandler { id: recentHover }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Metrics.space4
                        anchors.rightMargin: Metrics.space4
                        spacing: Metrics.space3
                        RoundedImage { Layout.preferredWidth: 32; Layout.preferredHeight: 45; source: modelData.subject ? modelData.subject.image_url : ""; fillMode: Image.PreserveAspectCrop; radius: Metrics.radiusS; cornerColor: recentHover.hovered ? Theme.surfaceHover : Theme.surfaceLow }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Metrics.space1
                            Label { Layout.fillWidth: true; text: modelData.subject ? modelData.subject.name : modelData.filename; color: Theme.textPrimary; font.weight: Typography.medium; elide: Text.ElideRight }
                            Label { Layout.fillWidth: true; text: modelData.filename || "已入库"; color: Theme.textTertiary; font.pixelSize: Typography.meta; elide: Text.ElideMiddle }
                        }
                        AppButton { text: "查看"; variant: "ghost"; enabled: !!modelData.subject; onClicked: if (modelData.subject) root.openSubject(modelData.subject.id) }
                    }
                }
            }
            EmptyState { visible: backend.recentMedia.length === 0; Layout.fillWidth: true; Layout.preferredWidth: root.availableWidth - Metrics.pageMargin(root.width) * 2; Layout.topMargin: Metrics.space6; title: "暂无最近入库"; iconName: "folder-search" }
        }

        Rectangle {
            property int count: backend.review.needs_review_count !== undefined
                ? backend.review.needs_review_count
                : (backend.review.needs_review || []).length
            visible: count > 0
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            radius: Metrics.radiusS
            color: Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, 0.08)
            border.width: 1
            border.color: Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, 0.20)
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Metrics.space4
                anchors.rightMargin: Metrics.space2
                Label { Layout.fillWidth: true; text: "媒体库有 " + parent.parent.count + " 个文件待审核"; color: Theme.warning; font.weight: Typography.medium }
                AppButton { text: "去处理"; variant: "ghost"; onClicked: root.openLibrary() }
            }
        }
        Item { Layout.preferredHeight: Metrics.space6 }
    }

    Component.onCompleted: backend.loadHome()
}
