#include "backend/BackendSupervisor.h"

#include <QCoreApplication>
#include <QDir>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QStandardPaths>
#include <QThread>
#include <QTimer>

namespace autoanime {
namespace {

QString errorSummary(const QByteArray &output)
{
    const QString text = QString::fromUtf8(output).trimmed();
    const QStringList lines = text.split(QLatin1Char('\n'), Qt::SkipEmptyParts);
    for (auto it = lines.crbegin(); it != lines.crend(); ++it) {
        const QString line = it->trimmed();
        if (line.contains(QStringLiteral("Error:"), Qt::CaseInsensitive)
            || line.contains(QStringLiteral("Exception:"), Qt::CaseInsensitive)
            || line.contains(QStringLiteral("failure:"), Qt::CaseInsensitive)) {
            return line.left(1200);
        }
    }
    return lines.isEmpty() ? QStringLiteral("迁移进程未返回错误信息") : lines.constLast().left(1200);
}

} // namespace

BackendSupervisor::BackendSupervisor(QUrl backendUrl, bool launchAllowed, QObject *parent)
    : QObject(parent)
    , m_backendUrl(std::move(backendUrl))
    , m_launchAllowed(launchAllowed)
{
    m_process.setProcessChannelMode(QProcess::MergedChannels);
    connect(&m_process, &QProcess::readyReadStandardOutput, this, [this] {
        m_processOutput.append(m_process.readAllStandardOutput());
        constexpr qsizetype maximumCapturedBytes = 64 * 1024;
        if (m_processOutput.size() > maximumCapturedBytes) {
            m_processOutput.remove(0, m_processOutput.size() - maximumCapturedBytes);
        }
    });
}

BackendSupervisor::~BackendSupervisor()
{
    stop();
}

bool BackendSupervisor::ensureReady(QString *errorMessage, int timeoutMs)
{
    QString detail;
    const ProbeResult initial = probeHealth(&detail);
    if (initial == ProbeResult::Ready) {
        return true;
    }
    if (initial == ProbeResult::Degraded) {
        if (errorMessage) {
            *errorMessage = QStringLiteral("已有后端未就绪：%1").arg(detail);
        }
        return false;
    }
    if (!m_launchAllowed || !isLocalBackend()) {
        if (errorMessage) {
            *errorMessage = QStringLiteral("无法连接后端：%1").arg(m_backendUrl.toString());
        }
        return false;
    }
    if (!prepareRuntime(errorMessage) || !runMigration(errorMessage)) {
        return false;
    }

    QStringList arguments{
        QStringLiteral("-m"), QStringLiteral("uvicorn"),
        QStringLiteral("backend.app.main:app"),
        QStringLiteral("--host"), m_backendUrl.host(),
        QStringLiteral("--port"), QString::number(m_backendUrl.port(8765)),
    };
    m_process.setWorkingDirectory(m_workingDirectory);
    m_process.setProcessEnvironment(m_environment);
    m_processOutput.clear();
    m_process.start(m_python, arguments);
    if (!m_process.waitForStarted(5000)) {
        if (errorMessage) {
            *errorMessage = QStringLiteral("FastAPI 启动失败：%1").arg(m_process.errorString());
        }
        return false;
    }
    m_ownsBackend = true;
    if (waitForReady(timeoutMs, errorMessage)) {
        return true;
    }
    stop();
    return false;
}

void BackendSupervisor::stop()
{
    if (!m_ownsBackend) {
        return;
    }
    m_ownsBackend = false;
    if (m_process.state() == QProcess::NotRunning) {
        return;
    }
    m_process.terminate();
    if (!m_process.waitForFinished(5000)) {
        m_process.kill();
        m_process.waitForFinished(2000);
    }
}

BackendSupervisor::ProbeResult BackendSupervisor::probeHealth(QString *detail) const
{
    QUrl healthUrl = m_backendUrl.resolved(QUrl(QStringLiteral("api/health")));
    QNetworkAccessManager network;
    QNetworkReply *reply = network.get(QNetworkRequest(healthUrl));
    QEventLoop loop;
    QTimer timer;
    timer.setSingleShot(true);
    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timer, &QTimer::timeout, &loop, &QEventLoop::quit);
    timer.start(700);
    loop.exec();
    if (!reply->isFinished()) {
        reply->abort();
        reply->deleteLater();
        return ProbeResult::Unreachable;
    }
    if (reply->error() != QNetworkReply::NoError) {
        reply->deleteLater();
        return ProbeResult::Unreachable;
    }
    const QJsonObject object = QJsonDocument::fromJson(reply->readAll()).object();
    reply->deleteLater();
    const QJsonObject database = object.value(QStringLiteral("database")).toObject();
    if (database.value(QStringLiteral("status")).toString() == QStringLiteral("ok")) {
        return ProbeResult::Ready;
    }
    if (detail) {
        *detail = database.value(QStringLiteral("detail")).toString(
            object.value(QStringLiteral("status")).toString(QStringLiteral("unknown"))
        );
    }
    return ProbeResult::Degraded;
}

bool BackendSupervisor::waitForReady(int timeoutMs, QString *errorMessage)
{
    QElapsedTimer elapsed;
    elapsed.start();
    QString detail;
    while (elapsed.elapsed() < timeoutMs) {
        QCoreApplication::processEvents(QEventLoop::AllEvents, 50);
        if (m_process.state() == QProcess::NotRunning) {
            if (errorMessage) {
                *errorMessage = QStringLiteral("FastAPI 提前退出（%1）：%2")
                    .arg(m_process.exitCode())
                    .arg(errorSummary(m_processOutput + m_process.readAllStandardOutput()));
            }
            return false;
        }
        const ProbeResult result = probeHealth(&detail);
        if (result == ProbeResult::Ready) {
            return true;
        }
        if (result == ProbeResult::Degraded) {
            if (errorMessage) {
                *errorMessage = QStringLiteral("FastAPI 数据库未就绪：%1").arg(detail);
            }
            return false;
        }
        QThread::msleep(100);
    }
    if (errorMessage) {
        *errorMessage = QStringLiteral("等待 FastAPI 就绪超时");
    }
    return false;
}

bool BackendSupervisor::prepareRuntime(QString *errorMessage)
{
    m_runtimeRoot = findRuntimeRoot();
    if (m_runtimeRoot.isEmpty()) {
        if (errorMessage) {
            *errorMessage = QStringLiteral("找不到随程序安装的 Python backend");
        }
        return false;
    }
    m_python = findPython(m_runtimeRoot);
    if (m_python.isEmpty()) {
        if (errorMessage) {
            *errorMessage = QStringLiteral("找不到 AutoAnime Python runtime");
        }
        return false;
    }

    const bool developmentTree = QFileInfo::exists(QDir(m_runtimeRoot).filePath(QStringLiteral(".git")));
    if (developmentTree) {
        m_workingDirectory = m_runtimeRoot;
        m_configPath = qEnvironmentVariable("AUTOANIME_CONFIG",
            QDir(m_runtimeRoot).filePath(QStringLiteral("config.yaml")));
    } else {
        m_workingDirectory = QDir(
            QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation)
        ).filePath(QStringLiteral("AutoAnime"));
        const QString configDirectory = QDir(
            QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation)
        ).filePath(QStringLiteral("AutoAnime"));
        m_configPath = qEnvironmentVariable("AUTOANIME_CONFIG",
            QDir(configDirectory).filePath(QStringLiteral("config.yaml")));
        if (!QDir().mkpath(m_workingDirectory) || !QDir().mkpath(configDirectory)) {
            if (errorMessage) {
                *errorMessage = QStringLiteral("无法创建用户数据目录");
            }
            return false;
        }
        if (!QFileInfo::exists(m_configPath)) {
            const QString example = QDir(m_runtimeRoot).filePath(QStringLiteral("config.example.yaml"));
            if (!QFile::copy(example, m_configPath)) {
                if (errorMessage) {
                    *errorMessage = QStringLiteral("无法初始化用户配置：%1").arg(m_configPath);
                }
                return false;
            }
            QFile::setPermissions(m_configPath, QFileDevice::ReadOwner | QFileDevice::WriteOwner);
        }
    }

    m_environment = QProcessEnvironment::systemEnvironment();
    const QString oldPythonPath = m_environment.value(QStringLiteral("PYTHONPATH"));
    m_environment.insert(
        QStringLiteral("PYTHONPATH"),
        oldPythonPath.isEmpty() ? m_runtimeRoot : m_runtimeRoot + QDir::listSeparator() + oldPythonPath
    );
    m_environment.insert(QStringLiteral("AUTOANIME_CONFIG"), m_configPath);
    m_environment.insert(QStringLiteral("PYTHONUNBUFFERED"), QStringLiteral("1"));
    return true;
}

bool BackendSupervisor::runMigration(QString *errorMessage)
{
    QProcess migration;
    migration.setProcessChannelMode(QProcess::MergedChannels);
    migration.setWorkingDirectory(m_workingDirectory);
    migration.setProcessEnvironment(m_environment);
    migration.start(m_python, {
        QStringLiteral("-m"), QStringLiteral("scripts.migrate"),
    });
    if (!migration.waitForStarted(5000) || !migration.waitForFinished(60000)
        || migration.exitStatus() != QProcess::NormalExit || migration.exitCode() != 0) {
        if (migration.state() != QProcess::NotRunning) {
            migration.kill();
            migration.waitForFinished(2000);
        }
        const QByteArray output = migration.readAll();
        if (!output.isEmpty()) {
            qWarning().noquote() << "[migration]" << QString::fromUtf8(output).trimmed();
        }
        if (errorMessage) {
            *errorMessage = QStringLiteral("SQLite migration failure：%1").arg(errorSummary(output));
        }
        return false;
    }
    return true;
}

QString BackendSupervisor::findRuntimeRoot() const
{
    const QString configured = qEnvironmentVariable("AUTOANIME_RUNTIME_ROOT");
    const QString applicationDirectory = QCoreApplication::applicationDirPath();
    const QStringList candidates{
        configured,
        QDir(applicationDirectory).absoluteFilePath(QStringLiteral("../../")),
        QDir(applicationDirectory).absoluteFilePath(QStringLiteral("../share/autoanime")),
        QDir(applicationDirectory).absoluteFilePath(QStringLiteral("../../share/autoanime")),
        QDir::currentPath(),
    };
    for (const QString &candidate : candidates) {
        if (candidate.isEmpty()) {
            continue;
        }
        const QDir directory(candidate);
        if (QFileInfo::exists(directory.filePath(QStringLiteral("backend/app/main.py")))
            && QFileInfo::exists(directory.filePath(QStringLiteral("alembic.ini")))) {
            return directory.absolutePath();
        }
    }
    return {};
}

QString BackendSupervisor::findPython(const QString &runtimeRoot) const
{
    const QString configured = qEnvironmentVariable("AUTOANIME_PYTHON");
    const QStringList candidates{
        configured,
        QDir(runtimeRoot).filePath(QStringLiteral(".venv/bin/python")),
        QDir(runtimeRoot).absoluteFilePath(QStringLiteral("../../lib/autoanime/venv/bin/python3")),
        QStandardPaths::findExecutable(QStringLiteral("python3")),
    };
    for (const QString &candidate : candidates) {
        const QFileInfo info(candidate);
        if (!candidate.isEmpty() && info.isFile() && info.isExecutable()) {
            return info.absoluteFilePath();
        }
    }
    return {};
}

bool BackendSupervisor::isLocalBackend() const
{
    const QString host = m_backendUrl.host().toLower();
    return host == QStringLiteral("127.0.0.1")
        || host == QStringLiteral("localhost")
        || host == QStringLiteral("::1");
}

} // namespace autoanime
