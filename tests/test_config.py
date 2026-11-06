import pytest

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


# --- 배포 설정 실수 안내 ---
def test_credentials_json_rejects_a_filename_with_a_helpful_message(monkeypatch):
    """파일 '이름' 을 넣는 실수가 가장 흔합니다. 무엇을 넣어야 하는지 알려줘야 합니다."""
    import core.config as cfg
    for value in ("credentials.json", '"credentials.json"', "./secrets/sa.json"):
        monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", value)
        with pytest.raises(ValueError) as e:
            cfg.credentials_info()
        assert "내용 전체" in str(e.value)


def test_credentials_json_rejects_truncated_json(monkeypatch):
    import core.config as cfg
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", '{"type":"service_account","proj')
    with pytest.raises(ValueError, match="잘리지 않았는지"):
        cfg.credentials_info()


def test_credentials_json_accepts_real_content(monkeypatch):
    import json

    import core.config as cfg
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", json.dumps(
        {"type": "service_account", "client_email": "a@b.iam.gserviceaccount.com",
         "private_key": "-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----\n"}))
    assert cfg.credentials_info()["client_email"].endswith("gserviceaccount.com")


def test_credentials_json_rejects_json_without_a_service_account(monkeypatch):
    import core.config as cfg
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", '{"hello":"world"}')
    with pytest.raises(ValueError, match="서비스 계정 정보가 없습니다"):
        cfg.credentials_info()


def test_empty_credentials_json_is_not_an_error(monkeypatch):
    """로컬에서는 이 설정을 안 쓰고 파일을 씁니다."""
    import core.config as cfg
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", "   ")
    assert cfg.credentials_info() is None
