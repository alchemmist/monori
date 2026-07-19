from alembic import context
from sqlalchemy import create_engine


def run_migrations():
    url = context.config.get_main_option("sqlalchemy.url")
    if context.is_offline_mode():
        context.configure(url=url, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(url)
        with engine.connect() as connection:
            context.configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()


run_migrations()
