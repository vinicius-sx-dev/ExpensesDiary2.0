from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {}
if settings.database_ssl_ca:
    import ssl
    context = ssl.create_default_context(cafile=settings.database_ssl_ca)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    connect_args["ssl"] = context
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=1800, connect_args=connect_args, hide_parameters=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
