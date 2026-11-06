"""테스트 전체에 적용되는 안전장치.

테스트가 실수로 실제 Claude API 를 호출하면 요금이 나가고, 결과도 매번 달라져
테스트가 불안정해집니다. 그래서 테스트 중에는 Mock 모드를 강제합니다.
실제 API 호출은 scratchpad 의 수동 확인 스크립트에서만 합니다.
"""

import pytest


@pytest.fixture(autouse=True, scope="session")
def _force_mock_mode():
    import os
    os.environ["FORCE_MOCK"] = "1"
    yield


@pytest.fixture(autouse=True)
def _no_accidental_api_calls(monkeypatch):
    """그래도 API 경로를 타면 테스트를 실패시킵니다."""
    def explode(*args, **kwargs):
        raise AssertionError("테스트가 실제 Claude API 를 호출하려 했습니다. "
                            "Mock 경로를 쓰거나 monkeypatch 하세요.")

    import anthropic
    monkeypatch.setattr(anthropic.resources.messages.Messages, "create", explode)
