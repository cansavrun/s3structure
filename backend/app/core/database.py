from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_database(url: str) -> tuple[Engine, sessionmaker[Session]]:
    # Engine uygulama ömrü boyunca, Session yalnızca tek işlem/istek boyunca yaşar.
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    engine = create_engine(url, pool_pre_ping=True, **kwargs)
    return engine, sessionmaker(engine, expire_on_commit=False)
