# Standard library
import re

# Third-party
from sqlalchemy.exc import IntegrityError

# <table>_icon_id_fkey: the constraint of icon_id on a reference table, country or region (22 tables)
_ICON_FK = re.compile(r'^insert or update on table "[a-z0-9_]+" violates foreign key constraint "[a-z0-9_]+_icon_id_fkey"')


def is_missing_icon(exc: IntegrityError) -> bool:
    # True when a WRITE (insert or update) named an icon_id that is not in asset_agg_icon. The deleting side (an icon that
    # is still used) breaks the same constraint but its message starts "update or delete on table"; that one is answered
    # 409 by DELETE /assets/icons/{id} and is not matched here. The message is the only thing both drivers (asyncpg and
    # psycopg2) share; asyncpg keeps the "Key (icon_id)=... is not present" part in a separate detail field.
    return bool(_ICON_FK.match(str(getattr(exc, "orig", exc)).lstrip()))
