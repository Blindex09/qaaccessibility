from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.src.security.rate_limiter import _request_log, check_rate_limit


def make_request(ip: str = "1.2.3.4"):
    req = MagicMock()
    req.headers = {}
    req.client.host = ip
    return req


class TestRateLimiter:
    def setup_method(self):
        _request_log.clear()

    def test_first_request_passes(self):
        req = make_request()
        check_rate_limit(req)  # não deve levantar

    def test_29_requests_pass(self):
        req = make_request("2.2.2.2")
        for _ in range(29):
            check_rate_limit(req)

    def test_30th_request_raises_429(self):
        req = make_request("3.3.3.3")
        for _ in range(30):
            check_rate_limit(req)
        with pytest.raises(HTTPException) as exc_info:
            check_rate_limit(req)
        assert exc_info.value.status_code == 429

    def test_different_ips_are_independent(self):
        req_a = make_request("10.0.0.1")
        req_b = make_request("10.0.0.2")
        for _ in range(30):
            check_rate_limit(req_a)
        # IP B não deve ser bloqueado
        check_rate_limit(req_b)

    def test_x_forwarded_for_header_used(self):
        req = MagicMock()
        req.headers = {"X-Forwarded-For": "5.5.5.5, 192.168.1.1"}
        req.client.host = "127.0.0.1"
        check_rate_limit(req)
        assert "5.5.5.5" in _request_log
