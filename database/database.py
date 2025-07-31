
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from .models import Base

class DB:
    _engine = None
    _Session = None

    @classmethod
    def init(cls, url: str):
        cls._engine = create_engine(url, future=True)
        Base.metadata.create_all(cls._engine)
        cls._Session = scoped_session(sessionmaker(bind=cls._engine, autoflush=False))

    @classmethod
    def session(cls):
        if cls._Session is None:
            raise RuntimeError("DB not initialised")
        return cls._Session()
