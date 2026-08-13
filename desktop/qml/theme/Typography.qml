pragma Singleton
import QtQuick

QtObject {
    readonly property string family: "Noto Sans CJK SC"
    readonly property string japaneseFamily: "Noto Sans CJK JP"
    readonly property string monoFamily: "Noto Sans Mono CJK SC"

    readonly property int display: 36
    readonly property int pageTitle: 28
    readonly property int sectionTitle: 20
    readonly property int itemTitle: 16
    readonly property int body: 14
    readonly property int label: 13
    readonly property int meta: 12
    readonly property int micro: 11

    readonly property int regular: Font.Normal
    readonly property int medium: Font.Medium
    readonly property int semibold: Font.DemiBold
    readonly property int bold: Font.Bold
}
