#include "backend/BackendClient.h"
#include "player/MpvCore.h"
#include "player/PlayerController.h"

#include <mpv/client.h>

#include <QSignalSpy>
#include <QTest>
#include <QUrl>

namespace autoanime {

class PlayerControllerActivityTest final : public QObject {
    Q_OBJECT

private slots:
    void progressFailureDoesNotBecomeBlockingPlaybackError()
    {
        MpvCore core;
        BackendClient backend(QUrl(QStringLiteral("http://127.0.0.1:9/")));
        PlayerController controller(&core, &backend);
        QSignalSpy errorSpy(&controller, &PlayerController::playbackError);
        QSignalSpy warningSpy(&controller, &PlayerController::playbackWarning);

        controller.onBackendError(0, QStringLiteral("保存播放进度"), QStringLiteral("暂时不可用"));

        QCOMPARE(errorSpy.count(), 0);
        QCOMPARE(warningSpy.count(), 1);
    }

    void progressSavesAreCoalescedWhileARequestIsInFlight()
    {
        MpvCore core;
        BackendClient backend(QUrl(QStringLiteral("http://127.0.0.1:9/")));
        PlayerController controller(&core, &backend);
        controller.m_sessionId = QStringLiteral("session-1");
        controller.m_position = 10.0;
        controller.m_duration = 100.0;

        controller.queueProgressSave(false);
        const quint64 activeRequestId = controller.m_activeProgressRequestId;
        controller.m_position = 25.0;
        controller.queueProgressSave(false);

        QVERIFY(controller.m_progressSaveInFlight);
        QVERIFY(activeRequestId != 0);
        QCOMPARE(controller.m_activeProgressRequestId, activeRequestId);
        QVERIFY(controller.m_progressSavePending);
        QCOMPARE(controller.m_pendingProgressPosition, 25.0);
        controller.m_position = 30.0;
        controller.finishProgressSave(activeRequestId, QStringLiteral("session-1"));
        QCOMPARE(controller.m_position, 30.0);
        QVERIFY(controller.m_progressSaveInFlight);
        QVERIFY(!controller.m_progressSavePending);
        QVERIFY(controller.m_activeProgressRequestId != activeRequestId);
        controller.resetSession();
    }

    void playbackStateDrivesActivity()
    {
        MpvCore core;
        BackendClient backend(QUrl(QStringLiteral("http://127.0.0.1:9/")));
        PlayerController controller(&core, &backend);
        QSignalSpy activitySpy(&controller, &PlayerController::playbackActivityChanged);

        // Browsing or waiting for a file must not inhibit sleep.
        QCOMPARE(activitySpy.count(), 0);
        controller.updatePlaybackActivity();
        QCOMPARE(activitySpy.count(), 0);

        // A loaded, genuinely playing file acquires once.
        controller.m_fileLoaded = true;
        controller.updatePlaybackActivity();
        QCOMPARE(activitySpy.count(), 1);
        QCOMPARE(activitySpy.takeFirst().at(0).toBool(), true);
        controller.updatePlaybackActivity();
        QCOMPARE(activitySpy.count(), 0);

        // Pause releases; repeated pause is idempotent; resume reacquires.
        core.setPaused(true);
        QTRY_VERIFY(core.isPaused());
        QTRY_COMPARE(activitySpy.count(), 1);
        QCOMPARE(activitySpy.takeFirst().at(0).toBool(), false);
        controller.onPauseChanged(true);
        QCOMPARE(activitySpy.count(), 0);

        core.setPaused(false);
        QTRY_VERIFY(!core.isPaused());
        QTRY_COMPARE(activitySpy.count(), 1);
        QCOMPARE(activitySpy.takeFirst().at(0).toBool(), true);

        // Stop releases immediately, before any playback transition work.
        controller.m_episodeId = 1;
        controller.stop();
        QCOMPARE(activitySpy.count(), 1);
        QCOMPARE(activitySpy.takeFirst().at(0).toBool(), false);

        // EOF releases before the ended transition is processed.
        controller.m_episodeId = 2;
        controller.m_fileLoaded = true;
        controller.updatePlaybackActivity();
        QCOMPARE(activitySpy.takeFirst().at(0).toBool(), true);
        controller.onEndFile(MPV_END_FILE_REASON_EOF, QString());
        QCOMPARE(activitySpy.count(), 1);
        QCOMPARE(activitySpy.takeFirst().at(0).toBool(), false);

        // Direct application shutdown also releases immediately.
        controller.m_episodeId = 3;
        controller.m_fileLoaded = true;
        controller.updatePlaybackActivity();
        QCOMPARE(activitySpy.takeFirst().at(0).toBool(), true);
        controller.shutdown();
        QCOMPARE(activitySpy.count(), 1);
        QCOMPARE(activitySpy.takeFirst().at(0).toBool(), false);
    }
};

} // namespace autoanime

QTEST_GUILESS_MAIN(autoanime::PlayerControllerActivityTest)
#include "test_player_controller_activity.moc"
