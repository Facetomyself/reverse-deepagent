from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from urllib.parse import quote

DEFAULT_SAMPLE_KEYWORD = "sign"
DEFAULT_SAMPLE_TIMESTAMP = 1700000000000
FIXTURE_SEED = "reverse-agent-fixture"
HMAC_SECRET = "fixture-secret"


@dataclass(frozen=True, slots=True)
class StrategySample:
    """Deterministic sample for strategy detector / rebuild validation."""

    sample_id: str
    strategy_id: str
    source_context: str
    expected_sign: str
    keyword: str = DEFAULT_SAMPLE_KEYWORD
    timestamp: int = DEFAULT_SAMPLE_TIMESTAMP
    description: str = ""


def _fixture_sign(keyword: str = DEFAULT_SAMPLE_KEYWORD, timestamp: int = DEFAULT_SAMPLE_TIMESTAMP) -> str:
    raw = f"{keyword}:{timestamp}:{FIXTURE_SEED}"
    hash_value = sum(ord(char) for char in raw) % 100000
    return f"sig_{hash_value:x}_{timestamp}"


def _message(keyword: str = DEFAULT_SAMPLE_KEYWORD, timestamp: int = DEFAULT_SAMPLE_TIMESTAMP) -> str:
    return f"{keyword}:{timestamp}"


STRATEGY_SAMPLE_CORPUS: tuple[StrategySample, ...] = (
    StrategySample(
        sample_id="fixture_seed_mod100000_basic",
        strategy_id="fixture_seed_mod100000",
        source_context="""function buildSign(keyword, timestamp) {
  const FIXTURE_SEED = 'reverse-agent-fixture';
  const raw = `${keyword}:${timestamp}:${FIXTURE_SEED}`;
  const hash = Array.from(raw).reduce((acc, char) => (acc + char.charCodeAt(0)) % 100000, 0);
  return `sig_${hash.toString(16)}_${timestamp}`;
}""",
        expected_sign=_fixture_sign(),
        description="Bundled deterministic fixture reducer.",
    ),
    StrategySample(
        sample_id="md5_keyword_timestamp_cryptojs",
        strategy_id="md5_keyword_timestamp",
        source_context="""function buildSign(keyword, timestamp) {
  return CryptoJS.MD5(`${keyword}:${timestamp}`).toString();
}""",
        expected_sign=hashlib.md5(_message().encode("utf-8")).hexdigest(),
        description="MD5 over keyword:timestamp.",
    ),
    StrategySample(
        sample_id="sha1_keyword_timestamp_subtle",
        strategy_id="sha1_keyword_timestamp",
        source_context="""async function buildSign(keyword, timestamp) {
  const raw = `${keyword}:${timestamp}`;
  const digest = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(raw));
  return Array.from(new Uint8Array(digest)).map((item) => item.toString(16).padStart(2, '0')).join('');
}""",
        expected_sign=hashlib.sha1(_message().encode("utf-8")).hexdigest(),
        description="SHA-1 over keyword:timestamp via Web Crypto marker.",
    ),
    StrategySample(
        sample_id="sha256_keyword_timestamp_subtle",
        strategy_id="sha256_keyword_timestamp",
        source_context="""async function buildSign(keyword, timestamp) {
  const raw = `${keyword}:${timestamp}`;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
  return Array.from(new Uint8Array(digest)).map((item) => item.toString(16).padStart(2, '0')).join('');
}""",
        expected_sign=hashlib.sha256(_message().encode("utf-8")).hexdigest(),
        description="SHA-256 over keyword:timestamp via Web Crypto marker.",
    ),
    StrategySample(
        sample_id="sha512_keyword_timestamp_subtle",
        strategy_id="sha512_keyword_timestamp",
        source_context="""async function buildSign(keyword, timestamp) {
  const raw = `${keyword}:${timestamp}`;
  const digest = await crypto.subtle.digest('SHA-512', new TextEncoder().encode(raw));
  return Array.from(new Uint8Array(digest)).map((item) => item.toString(16).padStart(2, '0')).join('');
}""",
        expected_sign=hashlib.sha512(_message().encode("utf-8")).hexdigest(),
        description="SHA-512 over keyword:timestamp via Web Crypto marker.",
    ),
    StrategySample(
        sample_id="hmac_md5_keyword_timestamp_literal_secret",
        strategy_id="hmac_md5_keyword_timestamp",
        source_context="""function buildSign(keyword, timestamp) {
  const secret = 'fixture-secret';
  return CryptoJS.HmacMD5(`${keyword}:${timestamp}`, secret).toString();
}""",
        expected_sign=hmac.new(HMAC_SECRET.encode("utf-8"), _message().encode("utf-8"), hashlib.md5).hexdigest(),
        description="HMAC-MD5 with literal secret.",
    ),
    StrategySample(
        sample_id="hmac_sha1_keyword_timestamp_literal_secret",
        strategy_id="hmac_sha1_keyword_timestamp",
        source_context="""function buildSign(keyword, timestamp) {
  const secret = 'fixture-secret';
  return CryptoJS.HmacSHA1(`${keyword}:${timestamp}`, secret).toString();
}""",
        expected_sign=hmac.new(HMAC_SECRET.encode("utf-8"), _message().encode("utf-8"), hashlib.sha1).hexdigest(),
        description="HMAC-SHA1 with literal secret.",
    ),
    StrategySample(
        sample_id="hmac_sha256_keyword_timestamp_literal_secret",
        strategy_id="hmac_sha256_keyword_timestamp",
        source_context="""function buildSign(keyword, timestamp) {
  const secret = 'fixture-secret';
  return hmacSha256(`${keyword}:${timestamp}`, secret);
}""",
        expected_sign=hmac.new(HMAC_SECRET.encode("utf-8"), _message().encode("utf-8"), hashlib.sha256).hexdigest(),
        description="HMAC-SHA256 with literal secret.",
    ),
    StrategySample(
        sample_id="hmac_sha512_keyword_timestamp_literal_secret",
        strategy_id="hmac_sha512_keyword_timestamp",
        source_context="""function buildSign(keyword, timestamp) {
  const secret = 'fixture-secret';
  return CryptoJS.HmacSHA512(`${keyword}:${timestamp}`, secret).toString();
}""",
        expected_sign=hmac.new(HMAC_SECRET.encode("utf-8"), _message().encode("utf-8"), hashlib.sha512).hexdigest(),
        description="HMAC-SHA512 with literal secret.",
    ),
    StrategySample(
        sample_id="base64_keyword_timestamp_btoa",
        strategy_id="base64_keyword_timestamp",
        source_context="""function buildSign(keyword, timestamp) {
  return btoa(`${keyword}:${timestamp}`);
}""",
        expected_sign=base64.b64encode(_message().encode("utf-8")).decode("ascii"),
        description="Base64 encoding over keyword:timestamp.",
    ),
    StrategySample(
        sample_id="urlencode_keyword_timestamp_encodeuricomponent",
        strategy_id="urlencode_keyword_timestamp",
        source_context="""function buildSign(keyword, timestamp) {
  return encodeURIComponent(`${keyword}:${timestamp}`);
}""",
        expected_sign=quote(_message(), safe=""),
        description="URL encoding over keyword:timestamp.",
    ),
)


def list_strategy_sample_corpus() -> list[dict[str, object]]:
    return [
        {
            "sample_id": sample.sample_id,
            "strategy_id": sample.strategy_id,
            "keyword": sample.keyword,
            "timestamp": sample.timestamp,
            "expected_sign": sample.expected_sign,
            "description": sample.description,
        }
        for sample in STRATEGY_SAMPLE_CORPUS
    ]
