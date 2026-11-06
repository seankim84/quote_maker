"""환경 설정 읽기. 값은 .env 에서만 오고, 코드에 키를 적지 않습니다."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")


def is_mock(api_key: str | None, force_mock: bool = False) -> bool:
    """Claude API 를 호출할 수 없거나 강제 설정이면 Mock 모드."""
    return force_mock or not (api_key or "").strip()


def anthropic_key() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "").strip()


def sheet_id() -> str:
    return os.getenv("GOOGLE_SHEET_ID", "").strip()


def credentials_path() -> Path:
    return ROOT / os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")


def credentials_info() -> dict | None:
    """GOOGLE_CREDENTIALS_JSON 에 담긴 서비스 계정 정보. 배포 환경에서 파일 대신 씁니다.
    실패해도 내용(키)을 예외 메시지에 넣지 않습니다."""
    raw = (os.getenv("GOOGLE_CREDENTIALS_JSON") or "").strip()
    if not raw:
        return None

    # 가장 흔한 실수: 파일 '이름' 을 넣고 '내용' 을 넣지 않음
    stripped = raw.strip('"\'')
    if stripped.endswith(".json") and len(stripped) < 300:
        raise ValueError(
            f"GOOGLE_CREDENTIALS_JSON 에 파일 이름({stripped[:60]})이 들어 있습니다. "
            f"파일 이름이 아니라 그 파일의 내용 전체"
            f'({{"type":"service_account", ... }} 로 시작하는 JSON)를 넣어야 합니다. '
            f"배포 환경에는 파일을 올릴 수 없어 내용을 직접 넣습니다.")

    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("GOOGLE_CREDENTIALS_JSON 이 올바른 JSON 이 아닙니다. "
                         "값이 { 로 시작하고 } 로 끝나는지, 중간이 잘리지 않았는지 "
                         "확인하세요.") from None
    if not isinstance(info, dict) or "client_email" not in info:
        raise ValueError("GOOGLE_CREDENTIALS_JSON 에 서비스 계정 정보가 없습니다. "
                         'client_email 과 private_key 가 들어있는 JSON 이어야 합니다.')
    return info


def force_mock() -> bool:
    return os.getenv("FORCE_MOCK", "0").strip() in ("1", "true", "True", "yes")


def mock_mode() -> bool:
    return is_mock(anthropic_key(), force_mock())


def masked(secret: str) -> str:
    """키의 마지막 4자리만. 짧은 키는 전체가 드러나므로 아무것도 보여주지 않습니다."""
    return f"설정됨 (…{secret[-4:]})" if len(secret) >= 12 else "설정됨"


def status() -> dict[str, tuple[bool, str]]:
    """Settings 화면용 연결 상태. 키 값 자체는 절대 반환하지 않습니다."""
    key = anthropic_key()
    creds = credentials_path()
    return {
        "Claude API 키": (bool(key), masked(key) if key else "없음 → Mock 모드"),
        "Google Sheet ID": (bool(sheet_id()), "설정됨" if sheet_id() else "없음"),
        "서비스 계정 파일": (creds.is_file(), creds.name if creds.is_file() else f"{creds.name} 없음"),
        "실행 모드": (not mock_mode(), "실제 Claude API" if not mock_mode() else "Mock (가짜 응답)"),
    }
