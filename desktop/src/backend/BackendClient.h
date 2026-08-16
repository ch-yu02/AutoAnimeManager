#pragma once

#include <QObject>
#include <QByteArray>
#include <QString>
#include <QUrl>
#include <QNetworkRequest>

class QNetworkAccessManager;
class QNetworkReply;

namespace autoanime {

class BackendClient final : public QObject {
    Q_OBJECT

public:
    explicit BackendClient(QUrl baseUrl, QObject *parent = nullptr);

    void createPlaybackSession(qint64 episodeId, bool fromStart, quint64 requestId = 0);
    void savePlaybackProgress(
        const QString &sessionId,
        double positionSeconds,
        double durationSeconds,
        bool ended,
        quint64 requestId = 0
    );
    void closePlaybackSession(const QString &sessionId);

signals:
    void sessionCreated(
        quint64 requestId,
        const QString &sessionId,
        qint64 episodeId,
        qint64 mediaFileId,
        const QString &mediaPath,
        const QString &subjectTitle,
        const QString &episodeDisplayNumber,
        const QString &episodeTitle,
        double initialPositionSeconds,
        double durationSeconds,
        bool hasDuration
    );
    void progressSaved(quint64 requestId, const QString &sessionId, bool watched, qint64 nextEpisodeId);
    void requestFailed(quint64 requestId, const QString &operation, const QString &message);

private:
    QNetworkAccessManager *m_network;
    QUrl m_baseUrl;

    QNetworkRequest request(const QString &path) const;
    void handleError(quint64 requestId, const QString &operation, QNetworkReply *reply, const QByteArray &payload);
};

} // namespace autoanime
