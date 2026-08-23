#pragma once

#include <QObject>
#include <QProcess>
#include <QUrl>

namespace autoanime {

class BackendSupervisor final : public QObject {
    Q_OBJECT

public:
    explicit BackendSupervisor(QUrl backendUrl, bool launchAllowed = true, QObject *parent = nullptr);
    ~BackendSupervisor() override;

    bool ensureReady(QString *errorMessage = nullptr, int timeoutMs = 30000);
    bool ownsBackend() const noexcept { return m_ownsBackend; }

public slots:
    void stop();

private:
    enum class ProbeResult { Unreachable, Ready, Degraded };

    ProbeResult probeHealth(QString *detail = nullptr) const;
    bool waitForReady(int timeoutMs, QString *errorMessage);
    bool prepareRuntime(QString *errorMessage);
    bool runMigration(QString *errorMessage);
    QString findRuntimeRoot() const;
    QString findPython(const QString &runtimeRoot) const;
    bool isLocalBackend() const;

    QUrl m_backendUrl;
    bool m_launchAllowed{true};
    bool m_ownsBackend{false};
    QString m_runtimeRoot;
    QString m_workingDirectory;
    QString m_python;
    QString m_configPath;
    QProcessEnvironment m_environment;
    QProcess m_process;
    QByteArray m_processOutput;
};

} // namespace autoanime
