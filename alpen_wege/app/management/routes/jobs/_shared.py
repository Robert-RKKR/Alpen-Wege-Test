# Local application
from app.management.models.job import MgmtLogJob
from app.profile.permissions import require_groups


admin_only = require_groups("administrator")


T = MgmtLogJob
