#include "qml/QmlBackend.h"

#include <QHash>
#include <QSignalSpy>
#include <QSet>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>
#include <QTimer>

#include <algorithm>

namespace autoanime {
namespace {

class FakeHttpServer final : public QTcpServer {
    Q_OBJECT

public:
    QHash<QString, int> delays;
    QSet<QString> failures;
    QStringList requests;
    QByteArray downloadsBody{"[]"};

    QUrl baseUrl() const
    {
        return QUrl(QStringLiteral("http://127.0.0.1:%1/").arg(serverPort()));
    }

protected:
    void incomingConnection(qintptr socketDescriptor) override
    {
        auto *socket = new QTcpSocket(this);
        socket->setSocketDescriptor(socketDescriptor);
        connect(socket, &QTcpSocket::readyRead, this, [this, socket] {
            const QByteArray request = socket->readAll();
            const QList<QByteArray> requestLine = request.split('\n').value(0).trimmed().split(' ');
            if (requestLine.size() < 2) {
                return;
            }
            const QString key = QString::fromUtf8(requestLine.at(0) + " " + requestLine.at(1));
            requests.append(key);
            const int delay = delays.value(key, 0);
            const bool fail = failures.contains(key);
            QTimer::singleShot(delay, socket, [this, socket, key, fail] {
                if (fail) {
                    socket->disconnectFromHost();
                    return;
                }
                QByteArray body = "{}";
                if (key == QStringLiteral("POST /api/library/review/rematch")) {
                    body = R"({"processed_count":1,"matched_count":1,"review_count":0})";
                } else if (key == QStringLiteral("POST /api/library/scan")) {
                    body = R"({"status":"RUNNING"})";
                } else if (key == QStringLiteral("GET /api/downloads")) {
                    body = downloadsBody;
                } else if (key.startsWith(QStringLiteral("GET /api/subjects/search?"))) {
                    body = "[]";
                }
                const QByteArray response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    "Connection: close\r\nContent-Length: " + QByteArray::number(body.size())
                    + "\r\n\r\n" + body;
                socket->write(response);
                socket->disconnectFromHost();
            });
        });
    }
};

class QmlBackendActivityTest final : public QObject {
    Q_OBJECT

private slots:
    void operationStateIsScopedAndDuplicateSafe()
    {
        FakeHttpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        server.delays.insert(QStringLiteral("POST /api/library/review/rematch"), 80);
        QmlBackend backend(server.baseUrl());

        backend.rematchReview();
        backend.rematchReview();
        QTRY_VERIFY(backend.activities().value(QStringLiteral("libraryRematching")).toBool());
        QTRY_COMPARE(server.requests.count(QStringLiteral("POST /api/library/review/rematch")), 1);
        QTRY_VERIFY(!backend.activities().value(QStringLiteral("libraryRematching")).toBool());
    }

    void unrelatedRequestsCanRunTogether()
    {
        FakeHttpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        QmlBackend backend(server.baseUrl());

        backend.searchLibrarySubjects(QStringLiteral("赛马娘"));
        backend.startLibraryScan();

        QTRY_VERIFY(server.requests.count() >= 2);
        QVERIFY(server.requests.contains(QStringLiteral("POST /api/library/scan")));
        QVERIFY(std::any_of(server.requests.cbegin(), server.requests.cend(), [](const QString &request) {
            return request.startsWith(QStringLiteral("GET /api/subjects/search?"));
        }));
    }

    void failedOperationRestoresItsState()
    {
        FakeHttpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        server.failures.insert(QStringLiteral("POST /api/library/scan"));
        server.delays.insert(QStringLiteral("POST /api/library/scan"), 50);
        QmlBackend backend(server.baseUrl());

        backend.startLibraryScan();
        QTRY_VERIFY(backend.activities().value(QStringLiteral("libraryScanStarting")).toBool());
        QTRY_VERIFY(!backend.activities().value(QStringLiteral("libraryScanStarting")).toBool());
        QVERIFY(!backend.error().isEmpty());

        backend.startLibraryScan();
        QTRY_COMPARE(server.requests.count(QStringLiteral("POST /api/library/scan")), 2);
    }

    void pollingHasOwnersAndDoesNotOverlap()
    {
        FakeHttpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        server.delays.insert(QStringLiteral("GET /api/downloads"), 1800);
        server.downloadsBody = R"([{"state":"DOWNLOADING"}])";
        QmlBackend backend(server.baseUrl());

        backend.setDownloadPolling(QStringLiteral("downloads"), true);
        backend.setDownloadPolling(QStringLiteral("subject"), true);
        QTRY_COMPARE(server.requests.count(QStringLiteral("GET /api/downloads")), 1);
        QTest::qWait(1650);
        QCOMPARE(server.requests.count(QStringLiteral("GET /api/downloads")), 1);

        backend.setDownloadPolling(QStringLiteral("downloads"), false);
        QTRY_VERIFY(!backend.activities().value(QStringLiteral("downloadsLoading")).toBool());
        QTRY_COMPARE(server.requests.count(QStringLiteral("GET /api/downloads")), 2);

        backend.setDownloadPolling(QStringLiteral("subject"), false);
        const int stoppedCount = server.requests.count(QStringLiteral("GET /api/downloads"));
        QTest::qWait(1650);
        QCOMPARE(server.requests.count(QStringLiteral("GET /api/downloads")), stoppedCount);
    }

    void idleDownloadPollingStopsAfterInitialRefresh()
    {
        FakeHttpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        QmlBackend backend(server.baseUrl());

        backend.setDownloadPolling(QStringLiteral("downloads"), true);
        QTRY_COMPARE(server.requests.count(QStringLiteral("GET /api/downloads")), 1);
        QTRY_VERIFY(!backend.activities().value(QStringLiteral("downloadsLoading")).toBool());
        QTest::qWait(1650);
        QCOMPARE(server.requests.count(QStringLiteral("GET /api/downloads")), 1);
    }
};

} // namespace
} // namespace autoanime

QTEST_GUILESS_MAIN(autoanime::QmlBackendActivityTest)
#include "test_qml_backend_activity.moc"
