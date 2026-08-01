"""Database integration tests: schema registration and round trips."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.schema import Base, SystemMetadata


def test_schema_metadata_is_registered() -> None:
    assert "system_metadata" in Base.metadata.tables


def test_metadata_table_roundtrip(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path}/roundtrip.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        session.add(SystemMetadata(key="schema_version", value="1"))
        session.commit()
        row = session.get(SystemMetadata, "schema_version")
        assert row is not None
        assert row.value == "1"
