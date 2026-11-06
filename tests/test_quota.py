"""공개 배포용 호출 상한. 돈이 걸린 로직이라 경계값을 모두 확인합니다."""

from datetime import date, timedelta

import pytest

from core.quota import (DayCounter, Limits, check, limits_from_env)

L = Limits(per_session=3, per_day=10)


def test_allowed_below_both_limits():
    assert check(0, 0, L).allowed
    assert check(2, 9, L).allowed          # 둘 다 한 번 남음


@pytest.mark.parametrize("used", [3, 4, 100])
def test_session_limit_blocks(used):
    v = check(used, 0, L)
    assert not v.allowed and "세션" in v.reason


@pytest.mark.parametrize("used", [10, 11, 500])
def test_day_limit_blocks(used):
    v = check(0, used, L)
    assert not v.allowed and "오늘" in v.reason


def test_day_limit_wins_over_session_limit():
    """하루 한도가 먼저 안내돼야 합니다 — 브라우저를 새로 열어도 안 풀리니까."""
    assert "오늘" in check(99, 99, L).reason


def test_zero_means_no_limit():
    unlimited = Limits(per_session=0, per_day=0)
    assert check(10_000, 10_000, unlimited).allowed


def test_zero_on_one_axis_only():
    assert check(10_000, 0, Limits(0, 10)).allowed        # 세션 제한 없음
    assert not check(0, 10, Limits(0, 10)).allowed        # 하루 제한은 유효


# --- 환경변수 ---
def test_limits_default(monkeypatch):
    monkeypatch.delenv("QUOTA_PER_SESSION", raising=False)
    monkeypatch.delenv("QUOTA_PER_DAY", raising=False)
    assert limits_from_env() == Limits(10, 200)


def test_limits_from_env(monkeypatch):
    monkeypatch.setenv("QUOTA_PER_SESSION", "5")
    monkeypatch.setenv("QUOTA_PER_DAY", "50")
    assert limits_from_env() == Limits(5, 50)


@pytest.mark.parametrize("bad", ["", "   ", "abc", "5.5", "-"])
def test_broken_env_falls_back_to_default(monkeypatch, bad):
    """설정이 깨졌을 때 '제한 없음' 으로 열리면 안 됩니다."""
    monkeypatch.setenv("QUOTA_PER_DAY", bad)
    assert limits_from_env().per_day == 200


def test_negative_env_becomes_zero(monkeypatch):
    monkeypatch.setenv("QUOTA_PER_DAY", "-10")
    assert limits_from_env().per_day == 0


# --- 하루 카운터 ---
def test_counter_counts_up():
    c = DayCounter()
    assert c.current() == 0
    assert c.record() == 1 and c.record() == 2
    assert c.current() == 2


def test_counter_resets_on_a_new_day():
    c = DayCounter()
    today = date(2026, 11, 6)
    c.day = today
    c.record(today); c.record(today)
    assert c.current(today) == 2
    assert c.current(today + timedelta(days=1)) == 0


def test_counter_does_not_reset_within_the_same_day():
    c = DayCounter()
    today = date(2026, 11, 6)
    c.day = today
    c.record(today)
    assert c.current(today) == 1
