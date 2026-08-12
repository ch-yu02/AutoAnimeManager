#pragma once

#include <QDBusObjectPath>
#include <QObject>
#include <QPointer>

class QDBusPendingCallWatcher;

namespace autoanime {

class SleepInhibitor final : public QObject {
    Q_OBJECT

public:
    explicit SleepInhibitor(QObject *parent = nullptr);
    ~SleepInhibitor() override;

    void setInhibited(bool inhibited);
    [[nodiscard]] bool isInhibited() const noexcept { return m_portalInhibited; }

private:
    void beginPortalAcquire();
    void beginScreenSaverAcquire();
    void closePortalRequest(const QDBusObjectPath &path);
    void closePortalRequestSynchronously(const QDBusObjectPath &path);
    void releaseScreenSaver(quint32 cookie);
    void releaseScreenSaverSynchronously(quint32 cookie);

    bool m_desired{false};
    bool m_portalInhibited{false};
    bool m_portalAcquirePending{false};
    bool m_portalAcquireFailed{false};
    bool m_screenSaverInhibited{false};
    bool m_screenSaverAcquirePending{false};
    bool m_screenSaverAcquireFailed{false};
    quint64 m_generation{0};
    QPointer<QDBusPendingCallWatcher> m_portalAcquireWatcher;
    QPointer<QDBusPendingCallWatcher> m_screenSaverAcquireWatcher;
    QDBusObjectPath m_portalRequestPath;
    quint32 m_screenSaverCookie{0};
};

} // namespace autoanime
