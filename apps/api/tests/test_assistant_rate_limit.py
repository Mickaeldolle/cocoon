from uuid import uuid4

from app.modules.assistant.rate_limit import AssistantRateLimiter


def test_generation_limit_is_per_user_and_expires() -> None:
    limiter = AssistantRateLimiter()
    alice = uuid4()
    bob = uuid4()
    assert limiter.allow(alice, 2, now=100)
    assert limiter.allow(alice, 2, now=101)
    assert not limiter.allow(alice, 2, now=102)
    assert limiter.allow(bob, 2, now=102)
    assert limiter.allow(alice, 2, now=161)
