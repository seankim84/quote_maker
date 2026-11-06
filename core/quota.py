"""공개 배포용 Claude API 호출 상한.

공개 URL 은 누구나 열 수 있습니다. 상한이 없으면 모르는 사람이 내 API 키로
요금을 무제한 발생시킬 수 있습니다. 상한을 넘으면 거부하지 않고 Mock 으로
내려가므로, 수강생은 흐름 학습을 계속할 수 있습니다.

streamlit 을 import 하지 않습니다 — 카운터 보관은 UI 가 담당합니다.
"""

from __future__ import annotations

import os
from datetime import date
from typing import NamedTuple

DEFAULT_PER_SESSION = 10
DEFAULT_PER_DAY = 200


class Limits(NamedTuple):
    per_session: int
    per_day: int


class Verdict(NamedTuple):
    allowed: bool
    reason: str   # 거부 사유 (허용이면 빈 문자열)


def limits_from_env() -> Limits:
    """배포 환경에서 secrets/환경변수로 조절합니다. 0 이면 해당 상한 없음."""
    def read(name: str, default: int) -> int:
        raw = (os.getenv(name) or "").strip()
        try:
            value = int(raw) if raw else default
        except ValueError:
            return default
        return max(value, 0)

    return Limits(read("QUOTA_PER_SESSION", DEFAULT_PER_SESSION),
                  read("QUOTA_PER_DAY", DEFAULT_PER_DAY))


def check(session_used: int, day_used: int, limits: Limits) -> Verdict:
    """상한 초과 여부. 0 인 상한은 '제한 없음' 으로 봅니다."""
    if limits.per_day and day_used >= limits.per_day:
        return Verdict(False, f"오늘 이 데모의 AI 호출 한도({limits.per_day}회)를 모두 썼습니다. "
                              f"한국 시간 자정에 초기화됩니다.")
    if limits.per_session and session_used >= limits.per_session:
        return Verdict(False, f"이 세션의 AI 호출 한도({limits.per_session}회)를 모두 썼습니다. "
                              f"브라우저를 새로 열면 다시 쓸 수 있습니다.")
    return Verdict(True, "")


class DayCounter:
    """프로세스 전체의 하루 호출 수. 날짜가 바뀌면 0 으로 돌아갑니다.

    shortcut: 서버 프로세스 안에만 존재해서 앱이 재시작되면 0 이 됩니다.
    정확한 과금 상한이 필요해지면 외부 저장소(DB/Redis)로 옮기세요.
    """

    def __init__(self) -> None:
        self.day = date.today()
        self.used = 0

    def current(self, today: date | None = None) -> int:
        today = today or date.today()
        if today != self.day:
            self.day, self.used = today, 0
        return self.used

    def record(self, today: date | None = None) -> int:
        self.used = self.current(today) + 1
        return self.used
