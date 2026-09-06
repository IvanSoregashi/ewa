from sqlalchemy import event, text


def initialize_db(engine):
    """Register per-connection SQLite PRAGMAs. journal_mode=WAL is persistent
    per database file, but synchronous and cache_size are per-connection -
    with pooled/reused engines they must be set on every new connection, not
    just the first one."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA cache_size=-64000;")
        cursor.close()
