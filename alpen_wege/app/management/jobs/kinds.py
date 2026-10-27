class JobKind:
    TRACK_PROCESS = "track.process"
    TRACK_REPROCESS = "track.reprocess"
    POI_RESCAN = "poi.rescan"
    CARD_RESCAN = "card.rescan"
    CARD_RENDER = "card.render"
    DEMO = "demo"


# Celery task that starts a job of each kind (used when a job row is created)
TASK_NAME = {
    JobKind.TRACK_PROCESS: "tracks.process_gpx",
    JobKind.TRACK_REPROCESS: "tracks.reprocess",
    JobKind.POI_RESCAN: "tracks.rescan_poi",
    JobKind.CARD_RESCAN: "tracks.rescan_card",
    JobKind.CARD_RENDER: "cards.render",
    JobKind.DEMO: "mgmt.demo_job",
}

# Task name -> job kind, for the Celery API ("is this task tracked?")
TRACKED_TASKS = {name: kind for kind, name in TASK_NAME.items()}

# Tasks that continue an existing job (they receive job_id as a keyword argument)
CHAIN_TASKS = frozenset({"tracks.detect_pois"})


# Life cycle states of a job (the `status` column of mgmt_log_job)
JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
