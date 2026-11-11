"""SessionState connects where REDIS_URL points, like the rest of the backend."""

from memory.session_state import SessionState


class FakeRedis:
    async def ping(self):
        return True


def test_redis_url_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6393/0")

    assert SessionState(redis_host="redis").redis_url == "redis://localhost:6393/0"


def test_without_redis_url_the_compose_host_is_used(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)

    state = SessionState(redis_host="redis", redis_port=6379)

    assert state.redis_url is None
    assert (state.redis_host, state.redis_port) == ("redis", 6379)


async def test_initialize_connects_to_the_url(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6393/0")
    seen = {}

    def from_url(url, **kwargs):
        seen["url"] = url
        return FakeRedis()

    monkeypatch.setattr("memory.session_state.redis.from_url", from_url)

    state = SessionState(redis_host="redis")
    await state.initialize()

    assert seen["url"] == "redis://localhost:6393/0"
    assert state._initialized
