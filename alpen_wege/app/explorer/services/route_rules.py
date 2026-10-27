# Local application
from app.core.utils.responses import AppError


def publish_own_segments(route, facts: dict) -> list:
    # A public route may only use public segments. The route owner's own private segments are published together with
    # the route; a private segment of somebody else cannot be (422). Returns the segments that were published.
    published = []
    blocked = []
    for f in facts.values():
        segment = f.segment
        if segment.is_public:
            continue
        if segment.created_by == route.created_by:
            segment.is_public = True
            published.append(segment)
        else:
            blocked.append(str(segment.id))
    if blocked:
        text = "A public route cannot use private segments of other users: " + ", ".join(blocked) + "."
        raise AppError(422, "Validation failed", error_message=text, error_errors=[{"field": "segments", "code": "private_segment", "message": text}])
    return published
