pragma Singleton
import QtQuick

QtObject {
    readonly property int space1: 4
    readonly property int space2: 8
    readonly property int space3: 12
    readonly property int space4: 16
    readonly property int space6: 24
    readonly property int space8: 32
    readonly property int space12: 48
    readonly property int space16: 64

    readonly property int radiusS: 6
    readonly property int radiusM: 10
    readonly property int radiusL: 14
    readonly property int controlHeight: 40
    readonly property int playerControlSize: 44
    readonly property int sidebarWidth: 192
    readonly property int pageHeaderHeight: 72
    readonly property int pageMarginWide: 40
    readonly property int pageMarginCompact: 24
    readonly property int posterWidth: 156
    readonly property int posterHeight: 221
    readonly property int mediaCardHeight: 269
    readonly property int continueCardWidth: 360
    readonly property int continueCardHeight: 160
    readonly property int continuePosterWidth: 92
    readonly property int continuePosterHeight: 130

    function pageMargin(width) { return width >= 1200 ? pageMarginWide : pageMarginCompact }
}
