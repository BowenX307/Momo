from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.infra.models import Base

# 当前 Alembic 配置对象；数据库地址只从应用配置读取，不写入 alembic.ini。
config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

# 加载 alembic.ini 中的日志配置。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Alembic 通过模型元数据比较代码中的目标结构和数据库当前结构。
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线生成迁移 SQL，不直接连接或修改数据库。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        compare_type=True,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """连接数据库并执行迁移。每次运行使用独立连接，不复用应用连接池。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
