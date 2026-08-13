pragma Singleton
import QtQuick

QtObject {
    property string themeId: "cinema"

    readonly property var availableThemes: [
        { id: "cinema", label: "放映室", description: "中性影院黑 · 薄荷绿", light: false, swatch: "#70D7B8" },
        { id: "deepSea", label: "深海蓝", description: "冷调深蓝 · 天光蓝", light: false, swatch: "#69C6F2" },
        { id: "morningMist", label: "晨雾", description: "清冷浅灰 · 松石绿", light: true, swatch: "#087D68" },
        { id: "washi", label: "和纸", description: "暖白纸色 · 朱砂红", light: true, swatch: "#A94F3D" }
    ]
    readonly property bool isLight: themeId === "morningMist" || themeId === "washi"

    readonly property color canvas: themeId === "deepSea" ? "#07111A"
        : themeId === "morningMist" ? "#F3F5F7"
        : themeId === "washi" ? "#F4F0E7" : "#080B10"
    readonly property color screenBlack: "#030405"
    readonly property color surfaceLow: themeId === "deepSea" ? "#0B1823"
        : themeId === "morningMist" ? "#EAEDF0"
        : themeId === "washi" ? "#ECE6DA" : "#0D1117"
    readonly property color surface: themeId === "deepSea" ? "#10202D"
        : themeId === "morningMist" ? "#FCFDFE"
        : themeId === "washi" ? "#FFFCF5" : "#121820"
    readonly property color surfaceRaised: themeId === "deepSea" ? "#172A39"
        : themeId === "morningMist" ? "#FFFFFF"
        : themeId === "washi" ? "#FFFDF8" : "#18212B"
    readonly property color surfaceHover: themeId === "deepSea" ? "#183246"
        : themeId === "morningMist" ? "#E1E6EA"
        : themeId === "washi" ? "#E5DED0" : "#1B2632"
    readonly property color controlInset: themeId === "deepSea" ? "#061019"
        : themeId === "morningMist" ? "#E7EBEE"
        : themeId === "washi" ? "#E9E2D5" : "#0A0F15"

    readonly property color textPrimary: isLight ? "#182027" : "#F3F6F8"
    readonly property color textSecondary: themeId === "washi" ? "#4C4740"
        : isLight ? "#3C4650" : themeId === "deepSea" ? "#C1D1DE" : "#C1CAD3"
    readonly property color textTertiary: themeId === "washi" ? "#746D63"
        : isLight ? "#697581" : themeId === "deepSea" ? "#89A0B2" : "#8C98A7"
    readonly property color textDisabled: themeId === "washi" ? "#A59D91"
        : isLight ? "#9AA4AD" : themeId === "deepSea" ? "#587083" : "#5F6976"

    readonly property color accent: themeId === "deepSea" ? "#69C6F2"
        : themeId === "morningMist" ? "#087D68"
        : themeId === "washi" ? "#A94F3D" : "#70D7B8"
    readonly property color accentHover: themeId === "deepSea" ? "#86D6FA"
        : themeId === "morningMist" ? "#066A59"
        : themeId === "washi" ? "#913E30" : "#83E2C5"
    readonly property color accentInk: isLight ? "#FFFFFF" : themeId === "deepSea" ? "#05141D" : "#07130F"

    readonly property color success: isLight ? "#187653" : "#68CFA0"
    readonly property color warning: isLight ? "#956515" : "#E2B765"
    readonly property color danger: isLight ? "#B33F49" : "#EB7D83"
    readonly property color info: isLight ? "#376FA8" : "#7FAFE5"

    readonly property color borderSoft: isLight ? Qt.rgba(0.06, 0.09, 0.12, 0.07) : Qt.rgba(1, 1, 1, 0.06)
    readonly property color border: isLight ? Qt.rgba(0.06, 0.09, 0.12, 0.12) : Qt.rgba(1, 1, 1, 0.10)
    readonly property color borderStrong: isLight ? Qt.rgba(0.06, 0.09, 0.12, 0.19) : Qt.rgba(1, 1, 1, 0.16)
    readonly property color progressTrack: isLight ? Qt.rgba(0.06, 0.09, 0.12, 0.14) : Qt.rgba(1, 1, 1, 0.18)
    readonly property color focusRing: themeId === "deepSea" ? "#9BDEFA"
        : themeId === "morningMist" ? "#0B806C"
        : themeId === "washi" ? "#A94F3D" : "#8BE6CB"
    readonly property color scrim: Qt.rgba(0, 0, 0, 0.72)

    function themeIndex(id) {
        for (let index = 0; index < availableThemes.length; ++index)
            if (availableThemes[index].id === id) return index
        return 0
    }

    function statusColor(status) {
        const value = String(status || "").toUpperCase()
        if (value === "READY" || value === "IMPORTED" || value === "COMPLETED"
                || value === "SUCCESS" || value === "RESTORED")
            return success
        if (value === "FAILED" || value === "ERROR" || value === "DELETED")
            return danger
        if (value === "QUARANTINED" || value === "NEEDS_REVIEW"
                || value === "MISSING" || value === "WARNING")
            return warning
        if (value === "DOWNLOADING" || value === "IMPORTING" || value === "RUNNING" || value === "SYNCING")
            return info
        return textTertiary
    }
}
