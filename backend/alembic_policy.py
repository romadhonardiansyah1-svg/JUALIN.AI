"""Alembic autogenerate policy for runtime-owned schema objects."""


def include_object(_object, name, type_, reflected, compare_to):
    """Exclude only the disposable database guard table from schema drift."""
    return not (
        type_ == "table"
        and reflected
        and compare_to is None
        and name == "disposable_db_sentinel"
    )
