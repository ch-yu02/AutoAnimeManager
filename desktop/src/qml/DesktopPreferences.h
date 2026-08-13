#pragma once

#include <QObject>
#include <QString>

namespace autoanime {

class DesktopPreferences final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString themeId READ themeId WRITE setThemeId NOTIFY themeIdChanged)

public:
    explicit DesktopPreferences(QObject *parent = nullptr);

    QString themeId() const;
    void setThemeId(const QString &themeId);

signals:
    void themeIdChanged();

private:
    QString m_themeId;
};

} // namespace autoanime
