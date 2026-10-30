# Public URL helpers. The API lives under /api/v1 (see Routing/api_routes_structure_proposal.md).
API_V1 = "/api/v1"


def job_url(job_id) -> str:
    # Where the owner reads one of their jobs (Location header of the 202 responses).
    return f"{API_V1}/management/my-jobs/{job_id}"


# POST to this path uploads a GPX file; UploadSizeLimitMiddleware matches this exact path.
TRACK_UPLOAD_PATH = f"{API_V1}/explorer/tracks"
# POST to this path uploads the GPX file of a segment (smaller limit); the same middleware watches it.
SEGMENT_UPLOAD_PATH = f"{API_V1}/explorer/segments"
# POST to this path uploads a photo; the same middleware watches it.
PHOTO_UPLOAD_PATH = f"{API_V1}/assets/photos"
# POST to this path uploads an SVG icon (small limit); the same middleware watches it.
ICON_UPLOAD_PATH = f"{API_V1}/assets/icons"
# POST to this path creates many icons from one CSV file (bigger limit); the same middleware watches it.
ICON_CSV_UPLOAD_PATH = f"{API_V1}/assets/icons/upload-csv"
