from core.config import is_mock


def test_no_key_is_mock():
    assert is_mock(None) is True
    assert is_mock("") is True
    assert is_mock("   ") is True


def test_key_is_real():
    assert is_mock("sk-ant-xxx") is False


def test_force_mock_wins():
    assert is_mock("sk-ant-xxx", force_mock=True) is True
