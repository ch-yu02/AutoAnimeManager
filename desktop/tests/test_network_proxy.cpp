#include "system/NetworkProxy.h"

#include <QNetworkProxy>
#include <QTest>

namespace {

class NetworkProxyTest final : public QObject
{
    Q_OBJECT

private slots:
    void init();
    void cleanup();
    void noEnvironmentUsesDirectConnection();
    void httpsProxyIsParsedWithCredentials();
    void allProxySupportsSocks5();
    void invalidProxyFallsBackToDirectConnection();

private:
    QHash<QByteArray, QByteArray> m_original;
};

constexpr const char *proxyVariables[] = {
    "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy",
};

void NetworkProxyTest::init()
{
    for (const char *name : proxyVariables) {
        const QByteArray key(name);
        m_original.insert(key, qgetenv(name));
        qunsetenv(name);
    }
}

void NetworkProxyTest::cleanup()
{
    for (auto it = m_original.cbegin(); it != m_original.cend(); ++it) {
        if (it.value().isNull()) {
            qunsetenv(it.key().constData());
        } else {
            qputenv(it.key().constData(), it.value());
        }
    }
    m_original.clear();
}

void NetworkProxyTest::noEnvironmentUsesDirectConnection()
{
    QCOMPARE(autoanime::networkProxyFromEnvironment().type(), QNetworkProxy::NoProxy);
}

void NetworkProxyTest::httpsProxyIsParsedWithCredentials()
{
    qputenv("HTTPS_PROXY", "http://proxy-user:p%40ss@127.0.0.1:7890");

    const QNetworkProxy proxy = autoanime::networkProxyFromEnvironment();

    QCOMPARE(proxy.type(), QNetworkProxy::HttpProxy);
    QCOMPARE(proxy.hostName(), QStringLiteral("127.0.0.1"));
    QCOMPARE(proxy.port(), quint16(7890));
    QCOMPARE(proxy.user(), QStringLiteral("proxy-user"));
    QCOMPARE(proxy.password(), QStringLiteral("p@ss"));
}

void NetworkProxyTest::allProxySupportsSocks5()
{
    qputenv("ALL_PROXY", "socks5h://127.0.0.1:1080");

    const QNetworkProxy proxy = autoanime::networkProxyFromEnvironment();

    QCOMPARE(proxy.type(), QNetworkProxy::Socks5Proxy);
    QCOMPARE(proxy.hostName(), QStringLiteral("127.0.0.1"));
    QCOMPARE(proxy.port(), quint16(1080));
}

void NetworkProxyTest::invalidProxyFallsBackToDirectConnection()
{
    qputenv("HTTPS_PROXY", "file:///tmp/not-a-proxy");
    QCOMPARE(autoanime::networkProxyFromEnvironment().type(), QNetworkProxy::NoProxy);
}

} // namespace

QTEST_GUILESS_MAIN(NetworkProxyTest)
#include "test_network_proxy.moc"
