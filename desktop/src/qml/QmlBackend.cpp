#include "qml/QmlBackend.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QUrlQuery>

#include <utility>

namespace autoanime {

QmlBackend::QmlBackend(QUrl baseUrl, QObject *parent)
    : QObject(parent)
    , m_network(new QNetworkAccessManager(this))
    , m_baseUrl(std::move(baseUrl))
{
    m_scanTimer.setInterval(800);
    connect(&m_scanTimer, &QTimer::timeout, this, [this] {
        send("GET", QStringLiteral("api/library/scan/status"), {}, [this](const QVariant &value) {
            m_scanStatus = value.toMap();
            emit libraryChanged();
            if (m_scanStatus.value(QStringLiteral("status")).toString() != QStringLiteral("RUNNING")) {
                m_scanTimer.stop();
                loadLibrary();
            }
        });
    });
    m_downloadTimer.setInterval(1500);
    connect(&m_downloadTimer, &QTimer::timeout, this, &QmlBackend::loadDownloads);
}

QUrl QmlBackend::url(const QString &path) const
{
    QUrl result = m_baseUrl;
    const QUrl relative(path);
    QString basePath = result.path();
    if (!basePath.endsWith(QLatin1Char('/'))) {
        basePath.append(QLatin1Char('/'));
    }
    QString relativePath = relative.path();
    if (relativePath.startsWith(QLatin1Char('/'))) {
        relativePath.remove(0, 1);
    }
    result.setPath(basePath + relativePath);
    result.setQuery(relative.query());
    return result;
}

void QmlBackend::send(const QByteArray &method, const QString &path, const QJsonObject &body, Handler handler)
{
    QNetworkRequest request(url(path));
    request.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json"));
    request.setRawHeader("Accept", "application/json");
    QNetworkReply *reply = m_network->sendCustomRequest(
        request,
        method,
        body.isEmpty() ? QByteArray{} : QJsonDocument(body).toJson(QJsonDocument::Compact)
    );
    ++m_pending;
    emit busyChanged();
    connect(reply, &QNetworkReply::finished, this, [this, reply, handler = std::move(handler)] {
        const QByteArray payload = reply->readAll();
        --m_pending;
        emit busyChanged();
        if (reply->error() != QNetworkReply::NoError) {
            QString message = reply->errorString();
            const QJsonValue detail = QJsonDocument::fromJson(payload).object().value(QStringLiteral("detail"));
            if (detail.isString()) {
                message = detail.toString();
            } else if (detail.isObject() && !detail.toObject().value(QStringLiteral("message")).toString().isEmpty()) {
                message = detail.toObject().value(QStringLiteral("message")).toString();
            }
            setError(message);
        } else {
            const QJsonDocument document = QJsonDocument::fromJson(payload);
            handler(document.isArray()
                ? QVariant(document.array().toVariantList())
                : QVariant(document.object().toVariantMap()));
        }
        reply->deleteLater();
    });
}

void QmlBackend::loadHome()
{
    clearMessage();
    send("GET", QStringLiteral("api/status"), {}, [this](const QVariant &value) {
        m_status = value.toMap();
        emit homeChanged();
    });
    send("GET", QStringLiteral("api/playback/continue"), {}, [this](const QVariant &value) {
        m_continueWatching = value.toList();
        emit homeChanged();
    });
    send("GET", QStringLiteral("api/subjects?collection_type=DOING"), {}, [this](const QVariant &value) {
        m_doingSubjects = value.toList();
        emit homeChanged();
    });
    send("GET", QStringLiteral("api/library/recent?limit=8"), {}, [this](const QVariant &value) {
        m_recentMedia = value.toList();
        emit homeChanged();
    });
    send("GET", QStringLiteral("api/library/review"), {}, [this](const QVariant &value) {
        m_review = value.toMap();
        emit homeChanged();
    });
}

void QmlBackend::loadSubjects(const QString &collectionType, bool localOnly)
{
    clearMessage();
    QUrlQuery query;
    if (!collectionType.isEmpty()) {
        query.addQueryItem(QStringLiteral("collection_type"), collectionType);
    }
    if (localOnly) {
        query.addQueryItem(QStringLiteral("local_only"), QStringLiteral("true"));
    }
    const QString suffix = query.isEmpty() ? QString{} : QStringLiteral("?") + query.toString();
    send("GET", QStringLiteral("api/subjects") + suffix, {}, [this](const QVariant &value) {
        m_subjects = value.toList();
        emit subjectsChanged();
    });
}

void QmlBackend::loadSubject(qint64 subjectId)
{
    clearMessage();
    send("GET", QStringLiteral("api/subjects/%1").arg(subjectId), {}, [this](const QVariant &value) {
        m_subject = value.toMap();
        emit subjectChanged();
    });
    send("GET", QStringLiteral("api/subjects/%1/episodes").arg(subjectId), {}, [this](const QVariant &value) {
        m_episodes = value.toList();
        emit subjectChanged();
    });
    loadDownloads();
}

void QmlBackend::loadLibrary()
{
    clearMessage();
    send("GET", QStringLiteral("api/library/review"), {}, [this](const QVariant &value) {
        m_review = value.toMap();
        emit libraryChanged();
    });
    send("GET", QStringLiteral("api/library/scan/status"), {}, [this](const QVariant &value) {
        m_scanStatus = value.toMap();
        if (m_scanStatus.value(QStringLiteral("status")).toString() == QStringLiteral("RUNNING")) {
            m_scanTimer.start();
        } else {
            m_scanTimer.stop();
        }
        emit libraryChanged();
    });
    send("GET", QStringLiteral("api/subjects"), {}, [this](const QVariant &value) {
        m_subjects = value.toList();
        emit subjectsChanged();
    });
}

void QmlBackend::loadSettings()
{
    clearMessage();
    send("GET", QStringLiteral("api/settings"), {}, [this](const QVariant &value) {
        m_settings = value.toMap();
        emit settingsChanged();
    });
}

void QmlBackend::loadDownloads()
{
    send("GET", QStringLiteral("api/downloads"), {}, [this](const QVariant &value) {
        m_downloads = value.toList();
        emit downloadsChanged();
    });
}

void QmlBackend::setDownloadPolling(bool enabled)
{
    if (enabled) {
        loadDownloads();
        m_downloadTimer.start();
    } else {
        m_downloadTimer.stop();
    }
}

void QmlBackend::addDownload(qint64 episodeId, const QString &magnet)
{
    send("POST", QStringLiteral("api/downloads"), {
        {QStringLiteral("episode_id"), episodeId},
        {QStringLiteral("magnet"), magnet.trimmed()},
    }, [this](const QVariant &) {
        setNotice(QStringLiteral("下载任务已创建"));
        loadDownloads();
        if (!m_subject.isEmpty()) {
            loadSubject(m_subject.value(QStringLiteral("id")).toLongLong());
        }
    });
}

void QmlBackend::pauseDownload(const QString &jobId)
{
    send("POST", QStringLiteral("api/downloads/%1/pause").arg(jobId), {}, [this](const QVariant &) {
        setNotice(QStringLiteral("下载已暂停"));
        loadDownloads();
    });
}

void QmlBackend::resumeDownload(const QString &jobId)
{
    send("POST", QStringLiteral("api/downloads/%1/resume").arg(jobId), {}, [this](const QVariant &) {
        setNotice(QStringLiteral("下载已恢复"));
        loadDownloads();
    });
}

void QmlBackend::retryDownload(const QString &jobId)
{
    send("POST", QStringLiteral("api/downloads/%1/retry").arg(jobId), {}, [this](const QVariant &) {
        setNotice(QStringLiteral("下载任务已重试"));
        loadDownloads();
    });
}

void QmlBackend::deleteDownload(const QString &jobId, bool deleteFiles)
{
    const QString suffix = deleteFiles ? QStringLiteral("?delete_files=true") : QString{};
    send("DELETE", QStringLiteral("api/downloads/%1").arg(jobId) + suffix, {}, [this](const QVariant &) {
        setNotice(QStringLiteral("qBittorrent 任务已删除"));
        loadDownloads();
    });
}

void QmlBackend::startLibraryScan()
{
    send("POST", QStringLiteral("api/library/scan"), {}, [this](const QVariant &value) {
        m_scanStatus = value.toMap();
        m_scanTimer.start();
        setNotice(QStringLiteral("媒体库扫描已启动"));
        emit libraryChanged();
    });
}

void QmlBackend::rematchReview()
{
    send("POST", QStringLiteral("api/library/review/rematch"), {}, [this](const QVariant &value) {
        const QVariantMap result = value.toMap();
        setNotice(QStringLiteral("已处理 %1 个文件，匹配 %2 个，剩余 %3 个待审核")
            .arg(result.value(QStringLiteral("processed_count")).toInt())
            .arg(result.value(QStringLiteral("matched_count")).toInt())
            .arg(result.value(QStringLiteral("review_count")).toInt()));
        loadLibrary();
    });
}

void QmlBackend::ignoreFile(qint64 fileId, bool ignored)
{
    send("POST", QStringLiteral("api/library/files/%1/ignore").arg(fileId),
        {{QStringLiteral("ignored"), ignored}}, [this](const QVariant &) { loadLibrary(); });
}

void QmlBackend::unlinkFile(qint64 fileId)
{
    send("DELETE", QStringLiteral("api/library/files/%1/match").arg(fileId), {},
        [this](const QVariant &) { loadLibrary(); });
}

void QmlBackend::reparseFile(qint64 fileId)
{
    send("POST", QStringLiteral("api/library/files/%1/reparse").arg(fileId), {}, [this](const QVariant &) {
        setNotice(QStringLiteral("已提交重新解析"));
        loadLibrary();
    });
}

void QmlBackend::matchFile(qint64 fileId, qint64 subjectId, const QVariantList &episodeIds)
{
    QJsonArray ids;
    for (const QVariant &id : episodeIds) {
        ids.append(id.toLongLong());
    }
    QJsonObject body{
        {QStringLiteral("subject_id"), subjectId},
        {QStringLiteral("episode_ids"), ids},
        {QStringLiteral("primary"), true},
        {QStringLiteral("lock"), true},
        {QStringLiteral("write_manifest"), true},
    };
    send("POST", QStringLiteral("api/library/files/%1/match").arg(fileId), body,
        [this](const QVariant &) { setNotice(QStringLiteral("人工关联已保存")); loadLibrary(); });
}

void QmlBackend::markWatched(qint64 episodeId, bool watched)
{
    const QString action = watched ? QStringLiteral("mark-watched") : QStringLiteral("mark-unwatched");
    send("POST", QStringLiteral("api/episodes/%1/%2").arg(episodeId).arg(action), {}, [this](const QVariant &) {
        if (!m_subject.isEmpty()) {
            loadSubject(m_subject.value(QStringLiteral("id")).toLongLong());
        }
    });
}

void QmlBackend::saveSettings(
    const QString &username,
    const QString &token,
    const QString &libraryRoots,
    const QString &qbittorrentBaseUrl,
    const QString &qbittorrentUsername,
    const QString &qbittorrentPassword,
    bool autoPlayNext,
    bool bangumiWriteback
)
{
    QJsonArray roots;
    for (const QString &line : libraryRoots.split(QLatin1Char('\n'), Qt::SkipEmptyParts)) {
        if (!line.trimmed().isEmpty()) {
            roots.append(line.trimmed());
        }
    }
    QJsonObject body{
        {QStringLiteral("bangumi_username"), username.trimmed()},
        {QStringLiteral("library_roots"), roots},
        {QStringLiteral("qbittorrent_base_url"), qbittorrentBaseUrl.trimmed()},
        {QStringLiteral("auto_play_next"), autoPlayNext},
        {QStringLiteral("bangumi_writeback_enabled"), bangumiWriteback},
    };
    if (!token.isEmpty()) {
        body.insert(QStringLiteral("bangumi_access_token"), token);
    }
    if (!qbittorrentPassword.isEmpty()) {
        body.insert(QStringLiteral("qbittorrent_password"), qbittorrentPassword);
    }
    if (!qbittorrentUsername.trimmed().isEmpty()) {
        body.insert(QStringLiteral("qbittorrent_username"), qbittorrentUsername.trimmed());
    }
    send("PATCH", QStringLiteral("api/settings"), body, [this](const QVariant &value) {
        m_settings = value.toMap();
        setNotice(QStringLiteral("设置已保存"));
        emit settingsChanged();
    });
}

void QmlBackend::testConnection(const QString &service)
{
    send("POST", QStringLiteral("api/settings/test/%1").arg(service), {}, [this](const QVariant &value) {
        const QVariantMap result = value.toMap();
        setNotice(result.value(QStringLiteral("detail")).toString());
    });
}

void QmlBackend::startBangumiSync()
{
    send("POST", QStringLiteral("api/bangumi/sync"), {}, [this](const QVariant &) {
        setNotice(QStringLiteral("Bangumi 同步已启动"));
    });
}

void QmlBackend::clearMessage()
{
    if (!m_error.isEmpty()) {
        m_error.clear();
        emit errorChanged();
    }
}

void QmlBackend::dismissNotice()
{
    if (!m_notice.isEmpty()) {
        m_notice.clear();
        emit noticeChanged();
    }
}

void QmlBackend::dismissError()
{
    if (!m_error.isEmpty()) {
        m_error.clear();
        emit errorChanged();
    }
}

void QmlBackend::setError(const QString &message)
{
    m_error = QStringLiteral("请求失败：%1").arg(message);
    emit errorChanged();
}

void QmlBackend::setNotice(const QString &message)
{
    m_notice = message;
    emit noticeChanged();
}

} // namespace autoanime
