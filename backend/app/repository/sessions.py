from contextlib import contextmanager

from redis import Redis
from redis.exceptions import RedisError

from app.core.errors import ErrorKind, ServiceError
from app.core.security import digest, session_store_key

RATE_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


@contextmanager
def available_session_store():
    try:
        yield
    except RedisError as exc:
        raise ServiceError(
            ErrorKind.UNAVAILABLE, "Oturum servisi geçici olarak kullanılamıyor"
        ) from exc


class SessionRepository:
    """Redis veri biçimi ve atomik işlemleri; cookie/Request nesnesini bilmez."""

    def __init__(self, client: Redis, secret: str):
        self.client = client
        self.secret = secret

    def get_key_id(self, raw_session: str) -> str | None:
        with available_session_store():
            return self.client.get(session_store_key(raw_session, self.secret))

    def rotate(self, old: str | None, raw: str, key_id: str, ttl: int) -> None:
        # Eski oturumu silme ve yeni oturumu yazma aynı Redis transaction'ındadır.
        with available_session_store(), self.client.pipeline(transaction=True) as pipe:
            if old:
                pipe.delete(session_store_key(old, self.secret))
            pipe.set(session_store_key(raw, self.secret), key_id, ex=ttl)
            pipe.execute()

    def delete(self, raw: str) -> None:
        with available_session_store():
            self.client.delete(session_store_key(raw, self.secret))

    def increment(self, scope: str, identity: str) -> int:
        bucket = digest(self.secret, identity, scope)
        with available_session_store():
            return self.client.eval(RATE_SCRIPT, 1, f"rate:{scope}:{bucket}", 60)

    def ping(self) -> None:
        with available_session_store():
            self.client.ping()
