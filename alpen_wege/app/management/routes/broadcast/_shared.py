# Local application
from app.profile.permissions import require_groups


admin_only = require_groups("administrator")
