from core.config import is_mock


def test_no_key_is_mock():
    assert is_mock(None) is True
    assert is_mock("") is True
    assert is_mock("   ") is True


def test_key_is_real():
    assert is_mock("sk-ant-xxx") is False


def test_force_mock_wins():
    assert is_mock("sk-ant-xxx", force_mock=True) is True


# --- 키 노출 방지 ---
def test_masked_shows_only_the_last_four():
    from core.config import masked
    assert masked("sk-ant-api03-abcdefghijkl") == "설정됨 (…ijkl)"


def test_masked_hides_short_keys_entirely():
    """짧은 키는 마지막 4자리만 보여줘도 사실상 전체가 드러납니다."""
    from core.config import masked
    for short in ("ab", "abcd", "abcdefghijk"):
        assert masked(short) == "설정됨"
        assert short not in masked(short)


def test_status_never_contains_the_whole_key(monkeypatch):
    import core.config as cfg
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-SECRETVALUE1234")
    rendered = " ".join(detail for _, detail in cfg.status().values())
    assert "SECRETVALUE" not in rendered
    assert "1234" in rendered          # 마지막 4자리는 확인용으로 보여줍니다
