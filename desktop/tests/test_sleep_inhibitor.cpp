#include "system/SleepInhibitor.h"

#include <QDBusConnection>
#include <QDBusError>
#include <QCoreApplication>
#include <QElapsedTimer>
#include <QDBusObjectPath>
#include <QList>
#include <QThread>
#include <QTimer>
#include <QVariantMap>
#include <QTest>

#include <functional>

namespace {

bool waitFor(const std::function<bool()> &condition, int timeoutMs)
{
    QElapsedTimer timer;
    timer.start();
    while (!condition() && timer.elapsed() < timeoutMs) {
        QCoreApplication::processEvents(QEventLoop::AllEvents, 50);
        QThread::msleep(10);
    }
    return condition();
}

class FakeRequest final : public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.freedesktop.portal.Request")

public:
    explicit FakeRequest(int *closeCount, QObject *parent)
        : QObject(parent)
        , m_closeCount(closeCount)
    {
    }

public slots:
    void Close()
    {
        ++(*m_closeCount);
    }

private:
    int *m_closeCount;
};

class FakePortal final : public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.freedesktop.portal.Inhibit")

public:
    int inhibitCount{0};
    int closeCount{0};
    quint32 lastFlags{0};
    QString lastWindow;
    QVariantMap lastOptions;
    int inhibitDelayMs{0};
    QList<FakeRequest *> requests;

public slots:
    QDBusObjectPath Inhibit(
        const QString &window,
        quint32 flags,
        const QVariantMap &options
    )
    {
        if (inhibitDelayMs > 0) {
            QThread::msleep(static_cast<unsigned long>(inhibitDelayMs));
        }
        ++inhibitCount;
        lastWindow = window;
        lastFlags = flags;
        lastOptions = options;
        const QString path = QStringLiteral(
            "/org/freedesktop/portal/desktop/request/%1"
        ).arg(inhibitCount);
        auto *request = new FakeRequest(&closeCount, this);
        requests.append(request);
        QDBusConnection::sessionBus().registerObject(
            path,
            request,
            QDBusConnection::ExportAllSlots
        );
        return QDBusObjectPath(path);
    }
};

class FakeScreenSaver final : public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.freedesktop.ScreenSaver")

public:
    int inhibitCount{0};
    int releaseCount{0};
    int inhibitDelayMs{0};
    QString lastApplication;
    QString lastReason;

public slots:
    quint32 Inhibit(const QString &application, const QString &reason)
    {
        if (inhibitDelayMs > 0) {
            QThread::msleep(static_cast<unsigned long>(inhibitDelayMs));
        }
        ++inhibitCount;
        lastApplication = application;
        lastReason = reason;
        return static_cast<quint32>(inhibitCount);
    }

    void UnInhibit(quint32)
    {
        ++releaseCount;
    }
};

class SleepInhibitorTest final : public QObject {
    Q_OBJECT

private slots:
    void initTestCase()
    {
        QDBusConnection bus = QDBusConnection::sessionBus();
        QVERIFY2(bus.isConnected(), "test must run with a session D-Bus");
        QVERIFY2(
            bus.registerService(QStringLiteral("org.freedesktop.portal.Desktop")),
            qPrintable(bus.lastError().message())
        );
        QVERIFY(bus.registerObject(
            QStringLiteral("/org/freedesktop/portal/desktop"),
            &m_portal,
            QDBusConnection::ExportAllSlots
        ));
        QVERIFY2(
            bus.registerService(QStringLiteral("org.freedesktop.ScreenSaver")),
            qPrintable(bus.lastError().message())
        );
        QVERIFY(bus.registerObject(
            QStringLiteral("/org/freedesktop/ScreenSaver"),
            &m_screenSaver,
            QDBusConnection::ExportAllSlots
        ));
    }

    void cleanup()
    {
        m_portal.inhibitDelayMs = 0;
        m_screenSaver.inhibitDelayMs = 0;
    }

    void cleanupTestCase()
    {
        QDBusConnection bus = QDBusConnection::sessionBus();
        for (int index = 1; index <= m_portal.inhibitCount; ++index) {
            bus.unregisterObject(QStringLiteral(
                "/org/freedesktop/portal/desktop/request/%1"
            ).arg(index));
        }
        bus.unregisterObject(QStringLiteral("/org/freedesktop/portal/desktop"));
        bus.unregisterService(QStringLiteral("org.freedesktop.portal.Desktop"));
        bus.unregisterObject(QStringLiteral("/org/freedesktop/ScreenSaver"));
        bus.unregisterService(QStringLiteral("org.freedesktop.ScreenSaver"));
    }

    void acquiresOnceAndReleasesIdempotently()
    {
        autoanime::SleepInhibitor inhibitor;

        inhibitor.setInhibited(false);
        QTest::qWait(30);
        QCOMPARE(m_portal.inhibitCount, 0);

        inhibitor.setInhibited(true);
        QVERIFY(waitFor([&inhibitor] { return inhibitor.isInhibited(); }, 1000));
        QCOMPARE(m_portal.inhibitCount, 1);
        QVERIFY(waitFor([this] { return m_screenSaver.inhibitCount == 1; }, 1000));
        QCOMPARE(m_portal.lastWindow, QString());
        QCOMPARE(m_portal.lastFlags, quint32(12));
        QCOMPARE(
            m_portal.lastOptions.value(QStringLiteral("reason")).toString(),
            QStringLiteral("AutoAnime is playing video")
        );
        QCOMPARE(m_screenSaver.lastApplication, QStringLiteral("AutoAnime"));
        QCOMPARE(m_screenSaver.lastReason, QStringLiteral("AutoAnime is playing video"));

        inhibitor.setInhibited(true);
        QTest::qWait(30);
        QCOMPARE(m_portal.inhibitCount, 1);
        QCOMPARE(m_screenSaver.inhibitCount, 1);

        inhibitor.setInhibited(false);
        QVERIFY(waitFor([&inhibitor] { return !inhibitor.isInhibited(); }, 1000));
        QVERIFY(waitFor([this] { return m_portal.closeCount == 1; }, 1000));
        QVERIFY(waitFor([this] { return m_screenSaver.releaseCount == 1; }, 1000));
        inhibitor.setInhibited(false);
        QTest::qWait(30);
        QCOMPARE(m_portal.closeCount, 1);
        QCOMPARE(m_screenSaver.releaseCount, 1);
    }

    void resumeAcquiresAgain()
    {
        autoanime::SleepInhibitor inhibitor;

        inhibitor.setInhibited(true);
        QVERIFY(waitFor([&inhibitor] { return inhibitor.isInhibited(); }, 1000));
        QVERIFY(waitFor([this] { return m_screenSaver.inhibitCount == 2; }, 1000));
        inhibitor.setInhibited(false);
        QVERIFY(waitFor([this] { return m_portal.closeCount == 2; }, 1000));
        QVERIFY(waitFor([this] { return m_screenSaver.releaseCount == 2; }, 1000));

        inhibitor.setInhibited(true);
        QVERIFY(waitFor([&inhibitor] { return inhibitor.isInhibited(); }, 1000));
        QCOMPARE(m_portal.inhibitCount, 3);
        QVERIFY(waitFor([this] { return m_screenSaver.inhibitCount == 3; }, 1000));
        inhibitor.setInhibited(false);
        QVERIFY(waitFor([this] { return m_portal.closeCount == 3; }, 1000));
        QVERIFY(waitFor([this] { return m_screenSaver.releaseCount == 3; }, 1000));
    }

    void lateAcquireIsClosedAfterPause()
    {
        m_portal.inhibitDelayMs = 100;
        m_screenSaver.inhibitDelayMs = 100;
        autoanime::SleepInhibitor inhibitor;
        inhibitor.setInhibited(true);
        QTimer::singleShot(10, &inhibitor, [&inhibitor] {
            inhibitor.setInhibited(false);
        });

        QVERIFY(waitFor([&inhibitor] { return !inhibitor.isInhibited(); }, 1500));
        QVERIFY(waitFor([this] { return m_portal.closeCount == 4; }, 1500));
        QVERIFY(waitFor([this] { return m_screenSaver.releaseCount == 4; }, 1500));
        m_portal.inhibitDelayMs = 0;
        m_screenSaver.inhibitDelayMs = 0;
    }

    void destructorReleases()
    {
        {
            auto *inhibitor = new autoanime::SleepInhibitor;
            inhibitor->setInhibited(true);
            QVERIFY(waitFor([inhibitor] { return inhibitor->isInhibited(); }, 1000));
            delete inhibitor;
        }
        QVERIFY(waitFor([this] { return m_portal.closeCount == 5; }, 1000));
        QVERIFY(waitFor([this] { return m_screenSaver.releaseCount == 5; }, 1000));
    }

private:
    FakePortal m_portal;
    FakeScreenSaver m_screenSaver;
};

} // namespace

QTEST_GUILESS_MAIN(SleepInhibitorTest)
#include "test_sleep_inhibitor.moc"
