import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.Material
import AutoAnime 1.0

ApplicationWindow {
    id: window
    width: 1360
    height: 820
    minimumWidth: 900
    minimumHeight: 600
    visible: true
    title: "AutoAnime"
    color: playerOpen ? Theme.screenBlack : Theme.canvas
    font.family: Typography.family
    Material.theme: Theme.isLight ? Material.Light : Material.Dark
    Material.accent: Theme.accent
    Material.primary: Theme.surfaceRaised
    Material.background: Theme.canvas
    Material.foreground: Theme.textPrimary

    palette.window: Theme.canvas
    palette.windowText: Theme.textPrimary
    palette.base: Theme.controlInset
    palette.alternateBase: Theme.surface
    palette.text: Theme.textPrimary
    palette.button: Theme.surface
    palette.buttonText: Theme.textPrimary
    palette.brightText: Theme.textPrimary
    palette.highlight: Theme.accent
    palette.highlightedText: Theme.accentInk
    palette.placeholderText: Theme.textDisabled
    palette.toolTipBase: Theme.surfaceRaised
    palette.toolTipText: Theme.textPrimary

    property bool playerOpen: stack.currentItem && stack.currentItem.objectName === "playerPage"
    property string currentRoot: "home"
    property var cachedRoots: ({})

    function leavePlayer() {
        if (!playerOpen) return
        if (window.visibility === Window.FullScreen) window.showNormal()
        player.stop()
    }
    function cachedRoot(component, name) {
        let page = cachedRoots[name]
        if (!page) {
            page = component.createObject(stack)
            if (!page) {
                console.error("无法创建根页面：" + name)
                return null
            }
            cachedRoots[name] = page
        }
        return page
    }
    function openRoot(component, name) {
        leavePlayer()
        const page = cachedRoot(component, name)
        if (!page) return
        currentRoot = name
        if (stack.currentItem === page) return
        stack.clear()
        stack.push(page)
    }
    function openHome() { openRoot(homeComponent, "home") }
    function openSubjects() { openRoot(subjectsComponent, "subjects") }
    function openSubject(id) { leavePlayer(); stack.push(detailComponent, { subjectId: id }) }
    function openLibrary() { openRoot(libraryComponent, "library") }
    function openDownloads() { openRoot(downloadsComponent, "downloads") }
    function openQuarantine() { openRoot(quarantineComponent, "quarantine") }
    function openSettings() { openRoot(settingsComponent, "settings") }
    function openPlayer(episodeId, fromStart, episodes, title) {
        stack.push(playerComponent, {
            requestedEpisodeId: episodeId,
            fromStart: fromStart,
            episodeModel: episodes || [],
            subjectTitle: title || ""
        })
    }

    Shortcut { sequence: "Ctrl+1"; onActivated: window.openHome() }
    Shortcut { sequence: "Ctrl+2"; onActivated: window.openSubjects() }
    Shortcut { sequence: "Ctrl+3"; onActivated: window.openLibrary() }
    Shortcut { sequence: "Ctrl+4"; onActivated: window.openDownloads() }
    Shortcut { sequence: "Ctrl+5"; onActivated: window.openQuarantine() }
    Shortcut { sequence: "Ctrl+,"; onActivated: window.openSettings() }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.preferredWidth: window.playerOpen ? 0 : Metrics.sidebarWidth
            Layout.fillHeight: true
            color: Theme.canvas
            visible: !window.playerOpen
            clip: true
            border.width: 0

            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.borderSoft }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Metrics.space4
                spacing: Metrics.space2

                Label {
                    text: "AutoAnime"
                    color: Theme.textPrimary
                    font.family: Typography.family
                    font.pixelSize: Typography.sectionTitle
                    font.weight: Typography.bold
                    Layout.leftMargin: Metrics.space2
                    Layout.topMargin: Metrics.space2
                    Layout.bottomMargin: Metrics.space6
                }
                Label {
                    text: "观看"
                    color: Theme.textTertiary
                    font.pixelSize: Typography.micro
                    font.weight: Typography.medium
                    Layout.leftMargin: Metrics.space3
                    Layout.bottomMargin: Metrics.space1
                }
                AppButton { Layout.fillWidth: true; text: "首页"; iconName: "house"; variant: "ghost"; animateBackground: false; selected: window.currentRoot === "home"; onClicked: window.openHome() }
                AppButton { Layout.fillWidth: true; text: "条目"; iconName: "library-big"; variant: "ghost"; animateBackground: false; selected: window.currentRoot === "subjects"; onClicked: window.openSubjects() }
                Label {
                    text: "管理"
                    color: Theme.textTertiary
                    font.pixelSize: Typography.micro
                    font.weight: Typography.medium
                    Layout.leftMargin: Metrics.space3
                    Layout.topMargin: Metrics.space6
                    Layout.bottomMargin: Metrics.space1
                }
                AppButton { Layout.fillWidth: true; text: "媒体库"; iconName: "folder-search"; variant: "ghost"; animateBackground: false; selected: window.currentRoot === "library"; onClicked: window.openLibrary() }
                AppButton { Layout.fillWidth: true; text: "下载"; iconName: "download"; variant: "ghost"; animateBackground: false; selected: window.currentRoot === "downloads"; onClicked: window.openDownloads() }
                AppButton { Layout.fillWidth: true; text: "隔离区"; iconName: "archive-restore"; variant: "ghost"; animateBackground: false; selected: window.currentRoot === "quarantine"; onClicked: window.openQuarantine() }
                Item { Layout.fillHeight: true }
                AppButton { Layout.fillWidth: true; text: "设置"; iconName: "settings"; variant: "ghost"; animateBackground: false; selected: window.currentRoot === "settings"; onClicked: window.openSettings() }
                Label {
                    text: backend.status.version ? "版本 " + backend.status.version : "AutoAnime"
                    color: Theme.textDisabled
                    font.pixelSize: Typography.micro
                    Layout.leftMargin: Metrics.space3
                    Layout.bottomMargin: Metrics.space2
                }
            }
        }

        StackView {
            id: stack
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            pushEnter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 220; easing.type: Easing.OutCubic } }
            pushExit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0.84; duration: 120 } }
            popEnter: Transition { NumberAnimation { property: "opacity"; from: 0.84; to: 1; duration: 180; easing.type: Easing.OutCubic } }
            popExit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 120 } }
        }
    }

    Rectangle {
        id: toast
        visible: backend.error.length > 0 || backend.notice.length > 0
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: Metrics.space6
        width: Math.min(440, parent.width - Metrics.space12)
        implicitHeight: toastContent.implicitHeight + Metrics.space4 * 2
        radius: Metrics.radiusM
        color: Theme.surfaceRaised
        border.width: 1
        border.color: Theme.borderStrong
        z: 100
        RowLayout {
            id: toastContent
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: Metrics.space4
            anchors.rightMargin: Metrics.space2
            spacing: Metrics.space3
            Rectangle { Layout.preferredWidth: 3; Layout.preferredHeight: 28; radius: 2; color: backend.error.length > 0 ? Theme.danger : Theme.success }
            Label {
                Layout.fillWidth: true
                text: backend.error.length > 0 ? backend.error : backend.notice
                color: Theme.textPrimary
                font.pixelSize: Typography.body
                wrapMode: Text.Wrap
            }
            IconButton { iconName: "x"; tooltip: "关闭"; onClicked: backend.error.length > 0 ? backend.dismissError() : backend.dismissNotice() }
        }
        Behavior on opacity { NumberAnimation { duration: 160 } }
    }

    Timer { id: noticeTimer; interval: 4000; onTriggered: backend.dismissNotice() }
    Connections {
        target: backend
        function onNoticeChanged() {
            if (backend.notice.length > 0) noticeTimer.restart()
            else noticeTimer.stop()
        }
    }
    Connections {
        target: preferences
        function onThemeIdChanged() { Theme.themeId = preferences.themeId }
    }

    Component { id: homeComponent; HomePage { onOpenSubject: id => window.openSubject(id); onPlayEpisode: (id, title) => window.openPlayer(id, false, [], title); onOpenLibrary: window.openLibrary() } }
    Component { id: subjectsComponent; SubjectsPage { onOpenSubject: id => window.openSubject(id) } }
    Component { id: detailComponent; SubjectDetailPage { onBack: stack.pop(); onPlayEpisode: (id, fromStart, episodes, title) => window.openPlayer(id, fromStart, episodes, title) } }
    Component { id: playerComponent; PlayerPage { onBack: stack.pop() } }
    Component { id: libraryComponent; LibraryPage {} }
    Component { id: downloadsComponent; DownloadsPage { onOpenSubject: id => window.openSubject(id) } }
    Component { id: quarantineComponent; QuarantinePage { onOpenSubject: id => window.openSubject(id) } }
    Component { id: settingsComponent; SettingsPage {} }

    Component.onCompleted: {
        Theme.themeId = preferences.themeId
        backend.loadSettings()
        openHome()
        if (startupEpisodeId > 0) openPlayer(startupEpisodeId, false, [], "正在播放")
    }
}
