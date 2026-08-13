#include "qml/DesktopPreferences.h"

#include <QSettings>
#include <QSet>

namespace autoanime {

namespace {
const QSet<QString> validThemes{
    QStringLiteral("cinema"),
    QStringLiteral("deepSea"),
    QStringLiteral("morningMist"),
    QStringLiteral("washi")
};
}

DesktopPreferences::DesktopPreferences(QObject *parent)
    : QObject(parent)
{
    const QSettings settings;
    const QString storedTheme = settings.value(QStringLiteral("appearance/theme"), QStringLiteral("cinema")).toString();
    m_themeId = validThemes.contains(storedTheme) ? storedTheme : QStringLiteral("cinema");
}

QString DesktopPreferences::themeId() const
{
    return m_themeId;
}

void DesktopPreferences::setThemeId(const QString &themeId)
{
    if (!validThemes.contains(themeId) || themeId == m_themeId) {
        return;
    }
    m_themeId = themeId;
    QSettings settings;
    settings.setValue(QStringLiteral("appearance/theme"), m_themeId);
    emit themeIdChanged();
}

} // namespace autoanime
