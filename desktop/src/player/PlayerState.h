#pragma once

#include <QMetaType>
#include <QString>
#include <QStringList>
#include <QtMath>

namespace autoanime {

struct MediaTrack {
    int id{-1};
    QString type;
    QString title;
    QString language;
    QString codec;
    bool selected{false};
    bool external{false};

    [[nodiscard]] QString displayName() const
    {
        QStringList details;
        if (!language.isEmpty()) {
            details.append(language);
        }
        if (!codec.isEmpty()) {
            details.append(codec);
        }
        if (external) {
            details.append(QStringLiteral("外挂"));
        }
        const QString name = title.isEmpty()
            ? QStringLiteral("轨道 %1").arg(id)
            : title;
        return details.isEmpty()
            ? name
            : QStringLiteral("%1 · %2").arg(name, details.join(QStringLiteral(" / ")));
    }
};

inline QString formatTime(double seconds)
{
    const qint64 total = qMax<qint64>(0, qRound64(seconds));
    const qint64 hours = total / 3600;
    const qint64 minutes = (total % 3600) / 60;
    const qint64 remainder = total % 60;
    if (hours > 0) {
        return QStringLiteral("%1:%2:%3")
            .arg(hours)
            .arg(minutes, 2, 10, QLatin1Char('0'))
            .arg(remainder, 2, 10, QLatin1Char('0'));
    }
    return QStringLiteral("%1:%2")
        .arg(minutes)
        .arg(remainder, 2, 10, QLatin1Char('0'));
}

} // namespace autoanime

Q_DECLARE_METATYPE(autoanime::MediaTrack)
