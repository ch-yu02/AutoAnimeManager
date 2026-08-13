#include "qml/QmlBackend.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QUrlQuery>

#include <algorithm>
#include <utility>

namespace autoanime {

QmlBackend::QmlBackend(QUrl baseUrl, QObject *parent)
    : QObject(parent)
    , m_network(new QNetworkAccessManager(this))
    , m_baseUrl(std::move(baseUrl))
{
    m_scanTimer.setInterval(800);
    connect(&m_scanTimer, &QTimer::timeout, this, [this] {
        if (m_activityPending.value(QStringLiteral("libraryScanPolling")) > 0) {
            return;
        }
        send("GET", QStringLiteral("api/library/scan/status"), {}, [this](const QVariant &value) {
            m_scanStatus = value.toMap();
            emit libraryChanged();
            if (m_scanStatus.value(QStringLiteral("status")).toString() != QStringLiteral("RUNNING")) {
                m_scanTimer.stop();
                loadLibrary();
            }
        }, QStringLiteral("libraryScanPolling"));
    });
    m_downloadTimer.setInterval(1500);
    connect(&m_downloadTimer, &QTimer::timeout, this, [this] {
        if (m_activityPending.value(QStringLiteral("downloadsLoading")) == 0) {
            loadDownloads();
        }
    });
    m_schedulerTimer.setInterval(1500);
    connect(&m_schedulerTimer, &QTimer::timeout, this, [this] {
        if (m_activityPending.value(QStringLiteral("schedulerLoading")) == 0) {
            loadScheduler();
        }
    });
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

QVariantMap QmlBackend::activities() const
{
    QVariantMap result;
    for (auto it = m_activityPending.cbegin(); it != m_activityPending.cend(); ++it) {
        result.insert(it.key(), it.value() > 0);
    }
    return result;
}

void QmlBackend::beginActivity(const QString &activity)
{
    if (activity.isEmpty()) {
        return;
    }
    ++m_activityPending[activity];
    emit activitiesChanged();
}

void QmlBackend::endActivity(const QString &activity)
{
    if (activity.isEmpty()) {
        return;
    }
    auto it = m_activityPending.find(activity);
    if (it == m_activityPending.end()) {
        return;
    }
    if (--it.value() <= 0) {
        m_activityPending.erase(it);
    }
    emit activitiesChanged();
}

void QmlBackend::send(
    const QByteArray &method,
    const QString &path,
    const QJsonObject &body,
    Handler handler,
    const QString &activity,
    Completion completion
)
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
    beginActivity(activity);
    connect(reply, &QNetworkReply::finished, this, [this, reply, handler = std::move(handler), activity, completion = std::move(completion)] {
        const QByteArray payload = reply->readAll();
        --m_pending;
        emit busyChanged();
        endActivity(activity);
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
        if (completion) {
            completion();
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
    }, QStringLiteral("homeLoading"));
    send("GET", QStringLiteral("api/playback/continue"), {}, [this](const QVariant &value) {
        m_continueWatching = value.toList();
        emit homeChanged();
    }, QStringLiteral("homeLoading"));
    send("GET", QStringLiteral("api/subjects?collection_type=DOING"), {}, [this](const QVariant &value) {
        m_doingSubjects = value.toList();
        emit homeChanged();
    }, QStringLiteral("homeLoading"));
    send("GET", QStringLiteral("api/library/recent?limit=8"), {}, [this](const QVariant &value) {
        m_recentMedia = value.toList();
        emit homeChanged();
    }, QStringLiteral("homeLoading"));
    send("GET", QStringLiteral("api/library/review"), {}, [this](const QVariant &value) {
        m_review = value.toMap();
        emit homeChanged();
    }, QStringLiteral("homeLoading"));
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
    }, QStringLiteral("subjectsLoading"));
}

void QmlBackend::loadSubject(qint64 subjectId)
{
    clearMessage();
    send("GET", QStringLiteral("api/subjects/%1").arg(subjectId), {}, [this](const QVariant &value) {
        m_subject = value.toMap();
        emit subjectChanged();
    }, QStringLiteral("subjectLoading"));
    send("GET", QStringLiteral("api/subjects/%1/episodes").arg(subjectId), {}, [this](const QVariant &value) {
        m_episodes = value.toList();
        emit subjectChanged();
    }, QStringLiteral("subjectLoading"));
    loadDownloads();
}

void QmlBackend::setSubjectCollection(qint64 subjectId, const QString &collectionType)
{
    if (subjectId <= 0 || collectionType.isEmpty()
        || m_activityPending.value(QStringLiteral("subjectCollectionSaving")) > 0) {
        return;
    }
    send("PATCH", QStringLiteral("api/subjects/%1/collection").arg(subjectId), {
        {QStringLiteral("collection_type"), collectionType},
    }, [this, subjectId](const QVariant &) {
        loadSubject(subjectId);
        loadHome();
        setNotice(QStringLiteral("收藏状态已同步到 Bangumi"));
    }, QStringLiteral("subjectCollectionSaving"));
}

void QmlBackend::loadLibrary()
{
    clearMessage();
    send("GET", QStringLiteral("api/library/review"), {}, [this](const QVariant &value) {
        m_review = value.toMap();
        emit libraryChanged();
    }, QStringLiteral("libraryLoading"));
    send("GET", QStringLiteral("api/library/scan/status"), {}, [this](const QVariant &value) {
        m_scanStatus = value.toMap();
        if (m_scanStatus.value(QStringLiteral("status")).toString() == QStringLiteral("RUNNING")) {
            m_scanTimer.start();
        } else {
            m_scanTimer.stop();
        }
        emit libraryChanged();
    }, QStringLiteral("libraryLoading"));
}

void QmlBackend::searchLibrarySubjects(const QString &query)
{
    const QString normalized = query.trimmed();
    m_librarySubjectQuery = normalized;
    if (normalized.isEmpty()) {
        m_librarySubjectMatches.clear();
        emit librarySubjectMatchesChanged();
        return;
    }
    QUrlQuery params;
    params.addQueryItem(QStringLiteral("query"), normalized);
    params.addQueryItem(QStringLiteral("limit"), QStringLiteral("20"));
    send("GET", QStringLiteral("api/subjects/search?") + params.toString(), {},
        [this, normalized](const QVariant &value) {
            if (normalized != m_librarySubjectQuery) {
                return;
            }
            m_librarySubjectMatches = value.toList();
            emit librarySubjectMatchesChanged();
        }, QStringLiteral("librarySubjectSearching"));
}

void QmlBackend::loadSettings()
{
    clearMessage();
    send("GET", QStringLiteral("api/settings"), {}, [this](const QVariant &value) {
        m_settings = value.toMap();
        emit settingsChanged();
    }, QStringLiteral("settingsLoading"));
}

void QmlBackend::loadScheduler()
{
    send("GET", QStringLiteral("api/scheduler"), {}, [this](const QVariant &value) {
        m_scheduler = value.toMap();
        const QVariantList tasks = m_scheduler.value(QStringLiteral("tasks")).toList();
        const bool active = std::any_of(tasks.cbegin(), tasks.cend(), [](const QVariant &task) {
            return task.toMap().value(QStringLiteral("active")).toBool();
        });
        if (active) {
            m_schedulerTimer.start();
        } else {
            m_schedulerTimer.stop();
        }
        emit schedulerChanged();
    }, QStringLiteral("schedulerLoading"));
}

void QmlBackend::runSchedulerTask(const QString &taskName)
{
    if (taskName.isEmpty() || m_activityPending.value(QStringLiteral("schedulerTaskStarting")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/scheduler/tasks/%1/run").arg(taskName), {},
        [this, taskName](const QVariant &value) {
            const QVariantMap run = value.toMap();
            const QString status = run.value(QStringLiteral("status")).toString();
            setNotice(QStringLiteral("%1：%2").arg(taskName, status));
            loadScheduler();
            if (taskName == QStringLiteral("DownloadMonitor")) {
                loadDownloads();
            }
        }, QStringLiteral("schedulerTaskStarting"));
}

void QmlBackend::loadCleanup(qint64 subjectId)
{
    send("GET", QStringLiteral("api/cleanup/subjects/%1").arg(subjectId), {},
        [this](const QVariant &value) {
            m_cleanupEligibility = value.toMap();
            emit cleanupChanged();
        }, QStringLiteral("cleanupLoading"));
}

void QmlBackend::loadCleanupRecords()
{
    send("GET", QStringLiteral("api/cleanup/records"), {}, [this](const QVariant &value) {
        m_cleanupRecords = value.toList();
        emit cleanupChanged();
    }, QStringLiteral("cleanupRecordsLoading"));
}

void QmlBackend::setSubjectKeepForever(qint64 subjectId, bool keepForever)
{
    if (m_activityPending.value(QStringLiteral("subjectKeepSaving")) > 0) {
        return;
    }
    send("PATCH", QStringLiteral("api/cleanup/subjects/%1/keep").arg(subjectId), {
        {QStringLiteral("keep_forever"), keepForever},
    }, [this, subjectId, keepForever](const QVariant &) {
        setNotice(keepForever ? QStringLiteral("条目已设为永久保留") : QStringLiteral("已取消永久保留"));
        loadSubject(subjectId);
        loadCleanup(subjectId);
    }, QStringLiteral("subjectKeepSaving"));
}

void QmlBackend::quarantineSubject(qint64 subjectId)
{
    if (m_activityPending.value(QStringLiteral("cleanupMutating")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/cleanup/subjects/%1/quarantine").arg(subjectId), {},
        [this, subjectId](const QVariant &) {
            setNotice(QStringLiteral("媒体已移入隔离区，可在隔离区页恢复"));
            loadSubject(subjectId);
            loadCleanup(subjectId);
            loadCleanupRecords();
        }, QStringLiteral("cleanupMutating"));
}

void QmlBackend::restoreCleanup(const QString &recordId)
{
    if (m_activityPending.value(QStringLiteral("cleanupMutating")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/cleanup/records/%1/restore").arg(recordId), {},
        [this](const QVariant &) {
            setNotice(QStringLiteral("隔离媒体已恢复到原路径"));
            loadCleanupRecords();
        }, QStringLiteral("cleanupMutating"));
}

void QmlBackend::permanentlyDeleteCleanup(const QString &recordId)
{
    if (m_activityPending.value(QStringLiteral("cleanupMutating")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/cleanup/records/%1/permanent-delete").arg(recordId), {},
        [this](const QVariant &) {
            setNotice(QStringLiteral("隔离媒体已永久删除，历史记录仍保留"));
            loadCleanupRecords();
        }, QStringLiteral("cleanupMutating"));
}

void QmlBackend::loadDownloads()
{
    send("GET", QStringLiteral("api/downloads"), {}, [this](const QVariant &value) {
        m_downloads = value.toList();
        emit downloadsChanged();
    }, QStringLiteral("downloadsLoading"));
}

void QmlBackend::setDownloadPolling(const QString &owner, bool enabled)
{
    if (owner.isEmpty()) {
        return;
    }
    if (enabled) {
        const bool wasInactive = m_downloadPollingOwners.isEmpty();
        m_downloadPollingOwners.insert(owner);
        if (wasInactive) {
            loadDownloads();
            m_downloadTimer.start();
        }
    } else {
        m_downloadPollingOwners.remove(owner);
        if (m_downloadPollingOwners.isEmpty()) {
            m_downloadTimer.stop();
        }
    }
}

void QmlBackend::addDownload(qint64 episodeId, const QString &magnet)
{
    if (m_activityPending.value(QStringLiteral("downloadMutating")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/downloads"), {
        {QStringLiteral("episode_id"), episodeId},
        {QStringLiteral("magnet"), magnet.trimmed()},
    }, [this](const QVariant &) {
        setNotice(QStringLiteral("下载任务已创建"));
        loadDownloads();
        if (!m_subject.isEmpty()) {
            loadSubject(m_subject.value(QStringLiteral("id")).toLongLong());
        }
    }, QStringLiteral("downloadMutating"));
}

void QmlBackend::pauseDownload(const QString &jobId)
{
    if (m_activityPending.value(QStringLiteral("downloadMutating")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/downloads/%1/pause").arg(jobId), {}, [this](const QVariant &) {
        setNotice(QStringLiteral("下载已暂停"));
        loadDownloads();
    }, QStringLiteral("downloadMutating"));
}

void QmlBackend::resumeDownload(const QString &jobId)
{
    if (m_activityPending.value(QStringLiteral("downloadMutating")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/downloads/%1/resume").arg(jobId), {}, [this](const QVariant &) {
        setNotice(QStringLiteral("下载已恢复"));
        loadDownloads();
    }, QStringLiteral("downloadMutating"));
}

void QmlBackend::retryDownload(const QString &jobId)
{
    if (m_activityPending.value(QStringLiteral("downloadMutating")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/downloads/%1/retry").arg(jobId), {}, [this](const QVariant &) {
        setNotice(QStringLiteral("下载任务已重试"));
        loadDownloads();
    }, QStringLiteral("downloadMutating"));
}

void QmlBackend::deleteDownload(const QString &jobId, bool deleteFiles)
{
    if (m_activityPending.value(QStringLiteral("downloadMutating")) > 0) {
        return;
    }
    const QString suffix = deleteFiles ? QStringLiteral("?delete_files=true") : QString{};
    send("DELETE", QStringLiteral("api/downloads/%1").arg(jobId) + suffix, {}, [this](const QVariant &) {
        setNotice(QStringLiteral("qBittorrent 任务已删除"));
        loadDownloads();
    }, QStringLiteral("downloadMutating"));
}

void QmlBackend::searchReleases(qint64 episodeId)
{
    if (m_activityPending.value(QStringLiteral("releaseSearching")) > 0) {
        return;
    }
    m_releaseSearch.clear();
    emit releaseSearchChanged();
    send("POST", QStringLiteral("api/releases/search"), {
        {QStringLiteral("episode_id"), episodeId},
    }, [this](const QVariant &value) {
        m_releaseSearch = value.toMap();
        emit releaseSearchChanged();
    }, QStringLiteral("releaseSearching"));
}

void QmlBackend::debugSearchReleases(qint64 episodeId)
{
    if (m_activityPending.value(QStringLiteral("releaseSearching")) > 0) {
        return;
    }
    m_releaseSearch.clear();
    emit releaseSearchChanged();
    send("POST", QStringLiteral("api/releases/search"), {
        {QStringLiteral("episode_id"), episodeId},
    }, [this](const QVariant &value) {
        m_releaseSearch = value.toMap();
        emit releaseSearchChanged();
        debugAutoSelect(m_releaseSearch.value(QStringLiteral("id")).toString());
    }, QStringLiteral("releaseSearching"));
}

void QmlBackend::debugAutoSelect(const QString &searchId)
{
    if (searchId.isEmpty() || m_activityPending.value(QStringLiteral("releaseDebugSelecting")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/releases/search/%1/debug-auto-select").arg(searchId), {},
        [this](const QVariant &value) {
            m_releaseSearch = value.toMap();
            const QVariantList candidates = m_releaseSearch.value(QStringLiteral("candidates")).toList();
            const bool selected = std::any_of(
                candidates.cbegin(), candidates.cend(), [](const QVariant &candidate) {
                    return candidate.toMap().value(QStringLiteral("debug_selected_at")).isValid();
                }
            );
            setNotice(selected
                ? QStringLiteral("已标注自动选择候选；未创建下载任务")
                : QStringLiteral("没有满足 AUTO_ACCEPT 条件的候选；未创建下载任务"));
            emit releaseSearchChanged();
        }, QStringLiteral("releaseDebugSelecting"));
}

void QmlBackend::downloadReleaseCandidate(const QString &candidateId)
{
    if (m_activityPending.value(QStringLiteral("releaseDownloading")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/releases/candidates/%1/download").arg(candidateId), {},
        [this](const QVariant &) {
            setNotice(QStringLiteral("已从候选创建下载任务"));
            const QString searchId = m_releaseSearch.value(QStringLiteral("id")).toString();
            if (!searchId.isEmpty()) {
                send("GET", QStringLiteral("api/releases/search/%1").arg(searchId), {},
                    [this](const QVariant &value) {
                        m_releaseSearch = value.toMap();
                        emit releaseSearchChanged();
                    });
            }
            loadDownloads();
            if (!m_subject.isEmpty()) {
                loadSubject(m_subject.value(QStringLiteral("id")).toLongLong());
            }
        }, QStringLiteral("releaseDownloading"));
}

void QmlBackend::startLibraryScan()
{
    if (m_activityPending.value(QStringLiteral("libraryScanStarting")) > 0
        || m_activityPending.value(QStringLiteral("libraryRematching")) > 0
        || m_activityPending.value(QStringLiteral("libraryLoading")) > 0
        || m_scanStatus.value(QStringLiteral("status")).toString() == QStringLiteral("RUNNING")) {
        return;
    }
    send("POST", QStringLiteral("api/library/scan"), {}, [this](const QVariant &value) {
        m_scanStatus = value.toMap();
        m_scanTimer.start();
        setNotice(QStringLiteral("媒体库扫描已启动"));
        emit libraryChanged();
    }, QStringLiteral("libraryScanStarting"));
}

void QmlBackend::rematchReview()
{
    if (m_activityPending.value(QStringLiteral("libraryRematching")) > 0
        || m_activityPending.value(QStringLiteral("libraryScanStarting")) > 0
        || m_activityPending.value(QStringLiteral("libraryLoading")) > 0
        || m_scanStatus.value(QStringLiteral("status")).toString() == QStringLiteral("RUNNING")) {
        return;
    }
    send("POST", QStringLiteral("api/library/review/rematch"), {}, [this](const QVariant &value) {
        const QVariantMap result = value.toMap();
        setNotice(QStringLiteral("已处理 %1 个文件，匹配 %2 个，剩余 %3 个待审核")
            .arg(result.value(QStringLiteral("processed_count")).toInt())
            .arg(result.value(QStringLiteral("matched_count")).toInt())
            .arg(result.value(QStringLiteral("review_count")).toInt()));
        loadLibrary();
    }, QStringLiteral("libraryRematching"));
}

void QmlBackend::ignoreFile(qint64 fileId, bool ignored)
{
    if (m_activityPending.value(QStringLiteral("libraryMutating")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/library/files/%1/ignore").arg(fileId),
        {{QStringLiteral("ignored"), ignored}}, [this](const QVariant &) { loadLibrary(); },
        QStringLiteral("libraryMutating"));
}

void QmlBackend::unlinkFile(qint64 fileId)
{
    if (m_activityPending.value(QStringLiteral("libraryMutating")) > 0) {
        return;
    }
    send("DELETE", QStringLiteral("api/library/files/%1/match").arg(fileId), {},
        [this](const QVariant &) { loadLibrary(); }, QStringLiteral("libraryMutating"));
}

void QmlBackend::reparseFile(qint64 fileId)
{
    if (m_activityPending.value(QStringLiteral("libraryMutating")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/library/files/%1/reparse").arg(fileId), {}, [this](const QVariant &) {
        setNotice(QStringLiteral("已提交重新解析"));
        loadLibrary();
    }, QStringLiteral("libraryMutating"));
}

void QmlBackend::matchFile(qint64 fileId, qint64 subjectId, const QVariantList &episodeIds)
{
    if (m_activityPending.value(QStringLiteral("libraryMutating")) > 0) {
        return;
    }
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
        [this](const QVariant &) { setNotice(QStringLiteral("人工关联已保存")); loadLibrary(); },
        QStringLiteral("libraryMutating"));
}

void QmlBackend::markWatched(qint64 episodeId, bool watched)
{
    if (m_activityPending.value(QStringLiteral("episodeWatchedSaving")) > 0) {
        return;
    }
    const QString action = watched ? QStringLiteral("mark-watched") : QStringLiteral("mark-unwatched");
    send("POST", QStringLiteral("api/episodes/%1/%2").arg(episodeId).arg(action), {}, [this](const QVariant &) {
        if (!m_subject.isEmpty()) {
            loadSubject(m_subject.value(QStringLiteral("id")).toLongLong());
        }
    }, QStringLiteral("episodeWatchedSaving"));
}

void QmlBackend::saveSettings(
    const QString &username,
    const QString &token,
    const QString &libraryRoots,
    const QString &qbittorrentBaseUrl,
    const QString &qbittorrentUsername,
    const QString &qbittorrentPassword,
    bool autoPlayNext,
    bool bangumiWriteback,
    bool autoDownloadEnabled,
    bool cleanupEnabled,
    int cleanupRetentionDays,
    int cleanupQuarantineDays
)
{
    if (m_activityPending.value(QStringLiteral("settingsSaving")) > 0) {
        return;
    }
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
        {QStringLiteral("auto_download_enabled"), autoDownloadEnabled},
        {QStringLiteral("cleanup_enabled"), cleanupEnabled},
        {QStringLiteral("cleanup_retention_days"), cleanupRetentionDays},
        {QStringLiteral("cleanup_quarantine_days"), cleanupQuarantineDays},
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
    }, QStringLiteral("settingsSaving"));
}

void QmlBackend::testConnection(const QString &service)
{
    if (m_activityPending.value(QStringLiteral("connectionTesting")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/settings/test/%1").arg(service), {}, [this](const QVariant &value) {
        const QVariantMap result = value.toMap();
        setNotice(result.value(QStringLiteral("detail")).toString());
    }, QStringLiteral("connectionTesting"));
}

void QmlBackend::startBangumiSync()
{
    if (m_activityPending.value(QStringLiteral("bangumiSyncStarting")) > 0) {
        return;
    }
    send("POST", QStringLiteral("api/bangumi/sync"), {}, [this](const QVariant &) {
        setNotice(QStringLiteral("Bangumi 完整同步已启动"));
    }, QStringLiteral("bangumiSyncStarting"));
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
