#pragma once

#include <QWebEnginePage>

namespace autoanime {

class AppWebPage final : public QWebEnginePage {
    Q_OBJECT

public:
    explicit AppWebPage(QUrl trustedFrontendUrl, QObject *parent = nullptr);

protected:
    bool acceptNavigationRequest(
        const QUrl &url,
        NavigationType type,
        bool isMainFrame
    ) override;

private:
    bool isTrustedOrigin(const QUrl &url) const;

    QUrl m_trustedFrontendUrl;
};

} // namespace autoanime
