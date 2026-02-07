from pathlib import Path

from app.services.usage_limiter import UsageLimiter


def test_usage_limiter_respects_max_uses(tmp_path: Path) -> None:
    limiter = UsageLimiter(db_path=tmp_path / "usage.db", max_uses=2)
    user_id = "test-user"

    usage_1, remaining_1 = limiter.consume(user_id)
    usage_2, remaining_2 = limiter.consume(user_id)
    usage_3, remaining_3 = limiter.consume(user_id)

    assert usage_1 == 1
    assert remaining_1 == 1
    assert usage_2 == 2
    assert remaining_2 == 0
    assert usage_3 == 2
    assert remaining_3 == 0
    assert limiter.can_consume(user_id) is False
