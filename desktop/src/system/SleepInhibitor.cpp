#include "system/SleepInhibitor.h"

#include <QDBusConnection>
#include <QDBusInterface>
#include <QDBusMessage>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDebug>
#include <QVariantMap>

namespace autoanime {
namespace {

constexpr quint32 kInhibitFlags = 4U | 8U;
constexpr auto kPortalService = "org.freedesktop.portal.Desktop";
constexpr auto kPortalPath = "/org/freedesktop/portal/desktop";
constexpr auto kPortalInterface = "org.freedesktop.portal.Inhibit";
constexpr auto kRequestInterface = "org.freedesktop.portal.Request";
constexpr auto kScreenSaverService = "org.freedesktop.ScreenSaver";
constexpr auto kScreenSaverPath = "/org/freedesktop/ScreenSaver";
constexpr auto kScreenSaverInterface = "org.freedesktop.ScreenSaver";
constexpr auto kReason = "AutoAnime is playing video";

QDBusMessage makeCloseMessage(const QDBusObjectPath &path)
{
    return QDBusMessage::createMethodCall(
        QString::fromLatin1(kPortalService),
        path.path(),
        QString::fromLatin1(kRequestInterface),
        QStringLiteral("Close")
    );
}

} // namespace

SleepInhibitor::SleepInhibitor(QObject *parent)
    : QObject(parent)
{
}

SleepInhibitor::~SleepInhibitor()
{
    m_desired = false;
    ++m_generation;
    if (m_portalAcquirePending && m_portalAcquireWatcher) {
        // A portal request may still produce a handle after the application
        // starts shutting down. Wait for that one reply so the handle can be
        // closed before this object disappears.
        auto *watcher = m_portalAcquireWatcher.data();
        QObject::disconnect(watcher, nullptr, this, nullptr);
        watcher->waitForFinished();
        const QDBusPendingReply<QDBusObjectPath> reply(*watcher);
        if (!reply.isError()) {
            closePortalRequestSynchronously(reply.value());
        }
        m_portalAcquirePending = false;
        m_portalAcquireWatcher = nullptr;
    }
    if (m_portalInhibited && !m_portalRequestPath.path().isEmpty()) {
        closePortalRequestSynchronously(m_portalRequestPath);
    }
    m_portalRequestPath = QDBusObjectPath();
    m_portalInhibited = false;

    if (m_screenSaverAcquirePending && m_screenSaverAcquireWatcher) {
        auto *watcher = m_screenSaverAcquireWatcher.data();
        QObject::disconnect(watcher, nullptr, this, nullptr);
        watcher->waitForFinished();
        const QDBusPendingReply<quint32> reply(*watcher);
        if (!reply.isError() && reply.value() != 0) {
            releaseScreenSaverSynchronously(reply.value());
        }
        m_screenSaverAcquirePending = false;
        m_screenSaverAcquireWatcher = nullptr;
    }
    if (m_screenSaverInhibited && m_screenSaverCookie != 0) {
        releaseScreenSaverSynchronously(m_screenSaverCookie);
    }
    m_screenSaverCookie = 0;
    m_screenSaverInhibited = false;
}

void SleepInhibitor::setInhibited(bool inhibited)
{
    if (inhibited == m_desired) {
        return;
    }
    m_desired = inhibited;
    ++m_generation;
    if (!inhibited) {
        m_portalAcquireFailed = false;
        m_screenSaverAcquireFailed = false;
        if (m_portalInhibited && !m_portalRequestPath.path().isEmpty()) {
            closePortalRequest(m_portalRequestPath);
        }
        m_portalRequestPath = QDBusObjectPath();
        m_portalInhibited = false;
        if (m_screenSaverInhibited && m_screenSaverCookie != 0) {
            releaseScreenSaver(m_screenSaverCookie);
        }
        m_screenSaverCookie = 0;
        m_screenSaverInhibited = false;
        return;
    }

    m_portalAcquireFailed = false;
    m_screenSaverAcquireFailed = false;
    beginPortalAcquire();
    beginScreenSaverAcquire();
}

void SleepInhibitor::beginPortalAcquire()
{
    if (!m_desired || m_portalInhibited || m_portalAcquirePending || m_portalAcquireFailed) {
        return;
    }
    const QDBusConnection bus = QDBusConnection::sessionBus();
    if (!bus.isConnected()) {
        qWarning() << "Sleep inhibition unavailable: session D-Bus is not connected";
        m_portalAcquireFailed = true;
        return;
    }

    QVariantMap options;
    options.insert(QStringLiteral("reason"), QString::fromLatin1(kReason));
    const QVariantList arguments{
        QString(),
        QVariant::fromValue(kInhibitFlags),
        QVariant::fromValue(options)
    };
    QDBusInterface portal(
        QString::fromLatin1(kPortalService),
        QString::fromLatin1(kPortalPath),
        QString::fromLatin1(kPortalInterface),
        bus
    );
    if (!portal.isValid()) {
        qWarning() << "Sleep inhibition unavailable:" << portal.lastError().message();
        m_portalAcquireFailed = true;
        return;
    }

    const quint64 generation = m_generation;
    auto *watcher = new QDBusPendingCallWatcher(
        portal.asyncCallWithArgumentList(QStringLiteral("Inhibit"), arguments),
        this
    );
    m_portalAcquireWatcher = watcher;
    m_portalAcquirePending = true;
    connect(watcher, &QDBusPendingCallWatcher::finished, this, [this, watcher, generation] {
        const QDBusPendingReply<QDBusObjectPath> reply(*watcher);
        const bool stale = generation != m_generation || !m_desired;
        m_portalAcquirePending = false;
        m_portalAcquireWatcher = nullptr;
        if (reply.isError()) {
            qWarning() << "Sleep inhibition unavailable:" << reply.error().message();
            m_portalAcquireFailed = !stale;
        } else if (stale) {
            closePortalRequest(reply.value());
        } else {
            m_portalRequestPath = reply.value();
            m_portalInhibited = true;
            m_portalAcquireFailed = false;
        }

        if (stale && m_desired && !m_portalInhibited) {
            beginPortalAcquire();
        }
        watcher->deleteLater();
    });
}

void SleepInhibitor::beginScreenSaverAcquire()
{
    if (!m_desired || m_screenSaverInhibited || m_screenSaverAcquirePending || m_screenSaverAcquireFailed) {
        return;
    }
    const QDBusConnection bus = QDBusConnection::sessionBus();
    if (!bus.isConnected()) {
        qWarning() << "Screen blanking inhibition unavailable: session D-Bus is not connected";
        m_screenSaverAcquireFailed = true;
        return;
    }
    QDBusInterface screenSaver(
        QString::fromLatin1(kScreenSaverService),
        QString::fromLatin1(kScreenSaverPath),
        QString::fromLatin1(kScreenSaverInterface),
        bus
    );
    if (!screenSaver.isValid()) {
        qWarning() << "Screen blanking inhibition unavailable:" << screenSaver.lastError().message();
        m_screenSaverAcquireFailed = true;
        return;
    }

    const quint64 generation = m_generation;
    auto *watcher = new QDBusPendingCallWatcher(
        screenSaver.asyncCall(
            QStringLiteral("Inhibit"),
            QStringLiteral("AutoAnime"),
            QString::fromLatin1(kReason)
        ),
        this
    );
    m_screenSaverAcquireWatcher = watcher;
    m_screenSaverAcquirePending = true;
    connect(watcher, &QDBusPendingCallWatcher::finished, this, [this, watcher, generation] {
        const QDBusPendingReply<quint32> reply(*watcher);
        const bool stale = generation != m_generation || !m_desired;
        m_screenSaverAcquirePending = false;
        m_screenSaverAcquireWatcher = nullptr;
        if (reply.isError()) {
            qWarning() << "Screen blanking inhibition unavailable:" << reply.error().message();
            m_screenSaverAcquireFailed = !stale;
        } else if (stale) {
            releaseScreenSaver(reply.value());
        } else {
            m_screenSaverCookie = reply.value();
            m_screenSaverInhibited = m_screenSaverCookie != 0;
            m_screenSaverAcquireFailed = !m_screenSaverInhibited;
        }

        if (stale && m_desired && !m_screenSaverInhibited) {
            beginScreenSaverAcquire();
        }
        watcher->deleteLater();
    });
}

void SleepInhibitor::closePortalRequest(const QDBusObjectPath &path)
{
    if (path.path().isEmpty()) {
        return;
    }
    const QDBusConnection bus = QDBusConnection::sessionBus();
    if (!bus.isConnected()) {
        qWarning() << "Sleep inhibition release unavailable: session D-Bus is not connected";
        return;
    }
    auto *watcher = new QDBusPendingCallWatcher(bus.asyncCall(makeCloseMessage(path)), this);
    connect(watcher, &QDBusPendingCallWatcher::finished, this, [watcher] {
        const QDBusPendingReply<> reply(*watcher);
        if (reply.isError()) {
            qWarning() << "Sleep inhibition release failed:" << reply.error().message();
        }
        watcher->deleteLater();
    });
}

void SleepInhibitor::closePortalRequestSynchronously(const QDBusObjectPath &path)
{
    if (path.path().isEmpty()) {
        return;
    }
    const QDBusConnection bus = QDBusConnection::sessionBus();
    if (!bus.isConnected()) {
        qWarning() << "Sleep inhibition release unavailable: session D-Bus is not connected";
        return;
    }
    const QDBusMessage reply = bus.call(makeCloseMessage(path), QDBus::Block, 1000);
    if (reply.type() == QDBusMessage::ErrorMessage) {
        qWarning() << "Sleep inhibition release failed:" << reply.errorMessage();
    }
}

void SleepInhibitor::releaseScreenSaver(quint32 cookie)
{
    if (cookie == 0) {
        return;
    }
    const QDBusConnection bus = QDBusConnection::sessionBus();
    if (!bus.isConnected()) {
        qWarning() << "Screen blanking inhibition release unavailable: session D-Bus is not connected";
        return;
    }
    QDBusMessage message = QDBusMessage::createMethodCall(
        QString::fromLatin1(kScreenSaverService),
        QString::fromLatin1(kScreenSaverPath),
        QString::fromLatin1(kScreenSaverInterface),
        QStringLiteral("UnInhibit")
    );
    message << cookie;
    auto *watcher = new QDBusPendingCallWatcher(bus.asyncCall(message), this);
    connect(watcher, &QDBusPendingCallWatcher::finished, this, [watcher] {
        const QDBusPendingReply<> reply(*watcher);
        if (reply.isError()) {
            qWarning() << "Screen blanking inhibition release failed:" << reply.error().message();
        }
        watcher->deleteLater();
    });
}

void SleepInhibitor::releaseScreenSaverSynchronously(quint32 cookie)
{
    if (cookie == 0) {
        return;
    }
    const QDBusConnection bus = QDBusConnection::sessionBus();
    if (!bus.isConnected()) {
        qWarning() << "Screen blanking inhibition release unavailable: session D-Bus is not connected";
        return;
    }
    QDBusMessage message = QDBusMessage::createMethodCall(
        QString::fromLatin1(kScreenSaverService),
        QString::fromLatin1(kScreenSaverPath),
        QString::fromLatin1(kScreenSaverInterface),
        QStringLiteral("UnInhibit")
    );
    message << cookie;
    const QDBusMessage reply = bus.call(message, QDBus::Block, 1000);
    if (reply.type() == QDBusMessage::ErrorMessage) {
        qWarning() << "Screen blanking inhibition release failed:" << reply.errorMessage();
    }
}

} // namespace autoanime
