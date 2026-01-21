from sqlalchemy import text


def initialize_db(engine):
    with engine.connect() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL;"))
        connection.execute(text("PRAGMA synchronous=NORMAL;"))
        connection.execute(text("PRAGMA cache_size=-64000;"))
        connection.commit()
