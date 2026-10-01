from library.database.sqlite_model_table import SQLiteModelTable
from sqlmodel import Field, SQLModel


class EpubSchemaStats(SQLModel, table=True):
    __tablename__ = "epub_schema_stats"

    filepath: str = Field(primary_key=True)
    error: str | None = None

    has_titlepage: bool = False
    has_stylesheet: bool = False
    has_page_styles: bool = False
    has_content: bool = False
    has_toc: bool = False

    fonts: int = 0
    len_creators: int = 0
    len_contributors: int = 0
    len_identifiers: int = 0

    guide_type: str | None = None
    guide_href: str | None = None
    guide_title: str | None = None

    creator_file: str | None = None
    creator_role: str | None = None
    creator_text: str | None = None

    contributor_role: str | None = None
    contributor_text: str | None = None

    identifier_id: str | None = None
    identifier_scheme: str | None = None

    has_calibre_ts: bool = False
    has_cover_cover: bool = False


class EpubSchemaStatsTable(SQLiteModelTable[EpubSchemaStats]):
    def create_all(self):
        # A schema survey must not create unrelated processing/analytics tables.
        return self.create()

    def upsert_many(self, rows: list[EpubSchemaStats]) -> None:
        if rows:
            self.upsert_many_dicts([tuple(row.model_dump() for row in rows)])
