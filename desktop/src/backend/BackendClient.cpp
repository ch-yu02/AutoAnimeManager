#include "backend/BackendClient.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QUrl>

#include <utility>

namespace autoanime {

BackendClient::BackendClient(QUrl baseUrl, QObject *parent)
    : QObject(parent)
    , m_network(new QNetworkAccessManager(this))
    , m_baseUrl(std::move(baseUrl))
{
    if (!m_baseUrl.path().endsWith(QLatin1Char('/'))) {
        m_baseUrl.setPath(m_baseUrl.path() + QLatin1Char('/'));
    }
}

QNetworkRequest BackendClient::request(const QString &path) const
{
    QUrl url = m_baseUrl;
    QString relativePath = path;
    if (relativePath.startsWith(QLatin1Char('/'))) {
        relativePath.remove(0, 1);
    }
    url.setPath(m_baseUrl.path() + relativePath);
    QNetworkRequest result(url);
    result.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json"));
    result.setRawHeader("Accept", "application/json");
    return result;
}

void BackendClient::createPlaybackSession(qint64 episodeId, bool fromStart, quint64 requestId)
{
    QJsonObject body{
        {QStringLiteral("episode_id"), episodeId},
        {QStringLiteral("from_start"), fromStart},
    };
    QNetworkReply *reply = m_network->post(
        request(QStringLiteral("/api/playback/sessions")),
        QJsonDocument(body).toJson(QJsonDocument::Compact)
    );
    connect(reply, &QNetworkReply::finished, this, [this, reply, requestId] {
        const QByteArray payload = reply->readAll();
        if (reply->error() != QNetworkReply::NoError) {
            handleError(requestId, QStringLiteral("创建播放会话"), reply, payload);
            reply->deleteLater();
            return;
        }
        const QJsonObject object = QJsonDocument::fromJson(payload).object();
        if (!object.contains(QStringLiteral("session_id")) || !object.contains(QStringLiteral("media_path"))) {
            emit requestFailed(requestId, QStringLiteral("创建播放会话"), QStringLiteral("后端返回的播放会话不完整"));
        } else {
            const QJsonValue duration = object.value(QStringLiteral("duration_seconds"));
            emit sessionCreated(
                requestId,
                object.value(QStringLiteral("session_id")).toString(),
                object.value(QStringLiteral("episode_id")).toInteger(),
                object.value(QStringLiteral("media_file_id")).toInteger(),
                object.value(QStringLiteral("media_path")).toString(),
                object.value(QStringLiteral("subject_title")).toString(),
                object.value(QStringLiteral("episode_display_number")).toString(),
                object.value(QStringLiteral("episode_title")).toString(),
                object.value(QStringLiteral("initial_position_seconds")).toDouble(),
                duration.toDouble(),
                !duration.isNull() && !duration.isUndefined()
            );
        }
        reply->deleteLater();
    });
}

void BackendClient::savePlaybackProgress(
    const QString &sessionId,
    double positionSeconds,
    double durationSeconds,
    bool ended,
    quint64 requestId
)
{
    QJsonObject body{
        {QStringLiteral("position_seconds"), qMax(0.0, positionSeconds)},
        {QStringLiteral("ended"), ended},
    };
    if (durationSeconds > 0.0) {
        body.insert(QStringLiteral("duration_seconds"), durationSeconds);
    }
    QNetworkReply *reply = m_network->post(
        request(QStringLiteral("/api/playback/sessions/%1/progress").arg(sessionId)),
        QJsonDocument(body).toJson(QJsonDocument::Compact)
    );
    connect(reply, &QNetworkReply::finished, this, [this, reply, sessionId, requestId] {
        const QByteArray payload = reply->readAll();
        if (reply->error() != QNetworkReply::NoError) {
            handleError(requestId, QStringLiteral("保存播放进度"), reply, payload);
        } else {
            const QJsonObject object = QJsonDocument::fromJson(payload).object();
            const QJsonValue nextEpisode = object.value(QStringLiteral("next_episode_id"));
            emit progressSaved(
                requestId,
                sessionId,
                object.value(QStringLiteral("watched")).toBool(false),
                nextEpisode.isNull() || nextEpisode.isUndefined() ? -1 : nextEpisode.toInteger(-1)
            );
        }
        reply->deleteLater();
    });
}

void BackendClient::closePlaybackSession(const QString &sessionId)
{
    QNetworkReply *reply = m_network->deleteResource(
        request(QStringLiteral("/api/playback/sessions/%1").arg(sessionId))
    );
    connect(reply, &QNetworkReply::finished, this, [this, reply] {
        if (reply->error() != QNetworkReply::NoError && reply->error() != QNetworkReply::ContentNotFoundError) {
            handleError(0, QStringLiteral("关闭播放会话"), reply, reply->readAll());
        }
        reply->deleteLater();
    });
}

void BackendClient::handleError(
    quint64 requestId,
    const QString &operation,
    QNetworkReply *reply,
    const QByteArray &payload
)
{
    QString message = reply->errorString();
    const QJsonObject body = QJsonDocument::fromJson(payload).object();
    const QJsonObject detail = body.value(QStringLiteral("detail")).toObject();
    if (!detail.value(QStringLiteral("message")).toString().isEmpty()) {
        message = detail.value(QStringLiteral("message")).toString();
    }
    emit requestFailed(requestId, operation, message);
}

} // namespace autoanime
