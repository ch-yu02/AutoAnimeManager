from __future__ import annotations


class BangumiError(Exception):
    """A safe, classified Bangumi API error.

    Error messages deliberately contain only status and endpoint category; they never
    include request headers, access tokens, or the raw response body.
    """

    code = "bangumi_error"

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class BangumiAuthError(BangumiError):
    code = "authentication_failed"


class BangumiRateLimitError(BangumiError):
    code = "rate_limited"


class BangumiTemporaryError(BangumiError):
    code = "temporary_failure"


class BangumiResponseError(BangumiError):
    code = "invalid_response"
