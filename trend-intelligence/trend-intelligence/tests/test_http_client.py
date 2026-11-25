import pytest
import requests

from trendintel.http_client import HttpError, PoliteHttpClient


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code, self.payload = status, payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        if self.payload is None:
            raise ValueError("no json")
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Clock:
    def __init__(self):
        self.t = 100.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds


def make_client(responses, min_interval=1.0):
    clock = Clock()
    session = FakeSession(responses)
    client = PoliteHttpClient("test-agent", min_interval=min_interval, session=session, clock=clock.now, sleep=clock.sleep)
    return client, session, clock


def test_user_agent_and_timeout_applied():
    client, session, _ = make_client([FakeResponse(payload={"ok": 1})])
    assert client.get_json("https://a.com/x") == {"ok": 1}
    assert session.headers["User-Agent"] == "test-agent"
    assert session.calls[0][2]["timeout"] == 15.0


def test_same_host_requests_are_throttled():
    client, _, clock = make_client([FakeResponse(), FakeResponse(), FakeResponse()])
    client.get("https://a.com/1")
    client.get("https://a.com/2")
    client.get("https://b.com/1")  # different host: no wait
    assert len(clock.slept) == 1 and clock.slept[0] == pytest.approx(1.0)


def test_http_error_status_wrapped():
    client, _, _ = make_client([FakeResponse(status=500)])
    with pytest.raises(HttpError):
        client.get("https://a.com/x")


def test_network_error_wrapped():
    client, _, _ = make_client([requests.ConnectionError("boom")])
    with pytest.raises(HttpError):
        client.get("https://a.com/x")


def test_invalid_json_wrapped():
    client, _, _ = make_client([FakeResponse(payload=None)])
    with pytest.raises(HttpError):
        client.get_json("https://a.com/x")
