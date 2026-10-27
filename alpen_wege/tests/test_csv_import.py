# Standard library
import asyncio
import uuid

# Third-party
from sqlalchemy import Integer, SmallInteger, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Local application
from app.core.utils.csv_import import _required_columns, import_csv
from sqlalchemy import inspect as sa_inspect


class _Base(DeclarativeBase):
    pass


class Scale(_Base):
    __tablename__ = "scale"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    created_by: Mapped[uuid.UUID] = mapped_column(nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)       # a Python default fills it in


class _File:
    def __init__(self, text: str):
        self._bytes = text.encode("utf-8")

    async def read(self):
        return self._bytes


class _Db:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add_all(self, objects):
        self.added.extend(objects)

    async def commit(self):
        self.commits += 1


USER = uuid.uuid4()


def _run(text: str):
    db = _Db()
    result = asyncio.run(import_csv(_File(text), Scale, USER, db))
    return result, db


def test_required_columns_are_the_ones_nothing_fills_in():
    assert _required_columns(sa_inspect(Scale)) == ["color", "rank"]     # not id, created_by, name, uses


def test_a_good_file_is_imported_and_created_by_is_the_user():
    result, db = _run("name,color,rank\nA,#000000,2\nB,#111111,4\n")
    assert result == {"inserted": 2, "errors": []} and db.commits == 1
    assert [o.rank for o in db.added] == [2, 4] and all(o.created_by == USER for o in db.added)


def test_a_file_without_a_required_column_inserts_nothing_and_says_which():
    result, db = _run("name,color\nA,#000000\n")
    assert result["inserted"] == 0 and db.added == [] and db.commits == 0
    assert len(result["errors"]) == 1 and "rank" in result["errors"][0] and "header" in result["errors"][0]


def test_a_row_with_an_empty_required_value_is_reported_and_the_other_rows_are_kept():
    result, db = _run("name,color,rank\nA,#000000,2\nB,#111111,\nC,,3\nD,#222222,5\n")
    assert result["inserted"] == 2 and [o.name for o in db.added] == ["A", "D"]
    assert result["errors"] == ["row 3: missing value for rank", "row 4: missing value for color"]


def test_a_bad_number_is_reported_per_row_as_before():
    result, db = _run("name,color,rank\nA,#000000,x\nB,#111111,4\n")
    assert result["inserted"] == 1 and len(result["errors"]) == 1 and result["errors"][0].startswith("row 2:")


def test_an_empty_file_or_header_only_file_inserts_nothing_without_a_database_call():
    for text in ("", "name,color,rank\n"):
        result, db = _run(text)
        assert result["inserted"] == 0 and db.commits == 0
