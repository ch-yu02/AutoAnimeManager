#pragma once

#include <QJsonObject>
#include <QHash>
#include <QObject>
#include <QSet>
#include <QUrl>
#include <QTimer>
#include <QVariantList>
#include <QVariantMap>

#include <functional>

class QNetworkAccessManager;
class QNetworkReply;

namespace autoanime {

class QmlBackend final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(QVariantMap activities READ activities NOTIFY activitiesChanged)
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
    Q_PROPERTY(QString notice READ notice NOTIFY noticeChanged)
    Q_PROPERTY(QVariantMap status READ status NOTIFY homeChanged)
    Q_PROPERTY(QVariantList continueWatching READ continueWatching NOTIFY homeChanged)
    Q_PROPERTY(QVariantList doingSubjects READ doingSubjects NOTIFY homeChanged)
    Q_PROPERTY(QVariantList recentMedia READ recentMedia NOTIFY homeChanged)
    Q_PROPERTY(QVariantList subjects READ subjects NOTIFY subjectsChanged)
    Q_PROPERTY(QVariantMap subject READ subject NOTIFY subjectChanged)
    Q_PROPERTY(QVariantList episodes READ episodes NOTIFY subjectChanged)
    Q_PROPERTY(QVariantMap review READ review NOTIFY libraryChanged)
    Q_PROPERTY(QVariantMap scanStatus READ scanStatus NOTIFY libraryChanged)
    Q_PROPERTY(QVariantList librarySubjectMatches READ librarySubjectMatches NOTIFY librarySubjectMatchesChanged)
    Q_PROPERTY(QVariantMap settings READ settings NOTIFY settingsChanged)
    Q_PROPERTY(QVariantList downloads READ downloads NOTIFY downloadsChanged)
    Q_PROPERTY(QVariantMap releaseSearch READ releaseSearch NOTIFY releaseSearchChanged)
    Q_PROPERTY(QVariantMap scheduler READ scheduler NOTIFY schedulerChanged)
    Q_PROPERTY(QVariantMap cleanupEligibility READ cleanupEligibility NOTIFY cleanupChanged)
    Q_PROPERTY(QVariantList cleanupRecords READ cleanupRecords NOTIFY cleanupChanged)

public:
    explicit QmlBackend(QUrl baseUrl, QObject *parent = nullptr);

    bool busy() const noexcept { return m_pending > 0; }
    QVariantMap activities() const;
    QString error() const { return m_error; }
    QString notice() const { return m_notice; }
    QVariantMap status() const { return m_status; }
    QVariantList continueWatching() const { return m_continueWatching; }
    QVariantList doingSubjects() const { return m_doingSubjects; }
    QVariantList recentMedia() const { return m_recentMedia; }
    QVariantList subjects() const { return m_subjects; }
    QVariantMap subject() const { return m_subject; }
    QVariantList episodes() const { return m_episodes; }
    QVariantMap review() const { return m_review; }
    QVariantMap scanStatus() const { return m_scanStatus; }
    QVariantList librarySubjectMatches() const { return m_librarySubjectMatches; }
    QVariantMap settings() const { return m_settings; }
    QVariantList downloads() const { return m_downloads; }
    QVariantMap releaseSearch() const { return m_releaseSearch; }
    QVariantMap scheduler() const { return m_scheduler; }
    QVariantMap cleanupEligibility() const { return m_cleanupEligibility; }
    QVariantList cleanupRecords() const { return m_cleanupRecords; }

    Q_INVOKABLE void loadHome();
    Q_INVOKABLE void loadSubjects(const QString &collectionType, bool localOnly);
    Q_INVOKABLE void loadSubject(qint64 subjectId);
    Q_INVOKABLE void setSubjectCollection(qint64 subjectId, const QString &collectionType);
    Q_INVOKABLE void loadLibrary();
    Q_INVOKABLE void searchLibrarySubjects(const QString &query);
    Q_INVOKABLE void loadSettings();
    Q_INVOKABLE void loadScheduler();
    Q_INVOKABLE void runSchedulerTask(const QString &taskName);
    Q_INVOKABLE void createBackup();
    Q_INVOKABLE void createDiagnostics();
    Q_INVOKABLE void loadCleanup(qint64 subjectId);
    Q_INVOKABLE void loadCleanupRecords();
    Q_INVOKABLE void setSubjectKeepForever(qint64 subjectId, bool keepForever);
    Q_INVOKABLE void quarantineSubject(qint64 subjectId);
    Q_INVOKABLE void restoreCleanup(const QString &recordId);
    Q_INVOKABLE void permanentlyDeleteCleanup(const QString &recordId);
    Q_INVOKABLE void loadDownloads();
    Q_INVOKABLE void setDownloadPolling(const QString &owner, bool enabled);
    Q_INVOKABLE void addDownload(qint64 episodeId, const QString &magnet);
    Q_INVOKABLE void pauseDownload(const QString &jobId);
    Q_INVOKABLE void resumeDownload(const QString &jobId);
    Q_INVOKABLE void retryDownload(const QString &jobId);
    Q_INVOKABLE void deleteDownload(const QString &jobId, bool deleteFiles);
    Q_INVOKABLE void searchReleases(qint64 episodeId);
    Q_INVOKABLE void debugSearchReleases(qint64 episodeId);
    Q_INVOKABLE void debugAutoSelect(const QString &searchId);
    Q_INVOKABLE void downloadReleaseCandidate(
        const QString &candidateId,
        const QString &replacementJobId = QString{}
    );
    Q_INVOKABLE void startLibraryScan();
    Q_INVOKABLE void rematchReview();
    Q_INVOKABLE void ignoreFile(qint64 fileId, bool ignored);
    Q_INVOKABLE void unlinkFile(qint64 fileId);
    Q_INVOKABLE void reparseFile(qint64 fileId);
    Q_INVOKABLE void matchFile(qint64 fileId, qint64 subjectId, const QVariantList &episodeIds);
    Q_INVOKABLE void markWatched(qint64 episodeId, bool watched);
    Q_INVOKABLE void saveSettings(
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
    );
    Q_INVOKABLE void testConnection(const QString &service);
    Q_INVOKABLE void startBangumiSync();
    Q_INVOKABLE void clearMessage();
    Q_INVOKABLE void dismissNotice();
    Q_INVOKABLE void dismissError();

signals:
    void busyChanged();
    void activitiesChanged();
    void errorChanged();
    void noticeChanged();
    void homeChanged();
    void subjectsChanged();
    void subjectChanged();
    void libraryChanged();
    void librarySubjectMatchesChanged();
    void settingsChanged();
    void downloadsChanged();
    void releaseSearchChanged();
    void schedulerChanged();
    void cleanupChanged();

private:
    using Handler = std::function<void(const QVariant &)>;
    using Completion = std::function<void()>;

    void send(
        const QByteArray &method,
        const QString &path,
        const QJsonObject &body,
        Handler handler,
        const QString &activity = {},
        Completion completion = {}
    );
    void beginActivity(const QString &activity);
    void endActivity(const QString &activity);
    void updateDownloadPollingTimer();
    QUrl url(const QString &path) const;
    void setError(const QString &message);
    void setNotice(const QString &message);

    QNetworkAccessManager *m_network;
    QTimer m_scanTimer;
    QTimer m_downloadTimer;
    QTimer m_schedulerTimer;
    QUrl m_baseUrl;
    int m_pending{0};
    QHash<QString, int> m_activityPending;
    QSet<QString> m_downloadPollingOwners;
    QString m_error;
    QString m_notice;
    QVariantMap m_status;
    QVariantList m_continueWatching;
    QVariantList m_doingSubjects;
    QVariantList m_recentMedia;
    QVariantList m_subjects;
    QVariantMap m_subject;
    QVariantList m_episodes;
    QVariantMap m_review;
    QVariantMap m_scanStatus;
    QVariantList m_librarySubjectMatches;
    QString m_librarySubjectQuery;
    QVariantMap m_settings;
    QVariantList m_downloads;
    QVariantMap m_releaseSearch;
    QVariantMap m_scheduler;
    QVariantMap m_cleanupEligibility;
    QVariantList m_cleanupRecords;
};

} // namespace autoanime
