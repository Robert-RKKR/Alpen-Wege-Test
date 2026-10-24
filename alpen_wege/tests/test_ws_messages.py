# Local application
from app.management.jobs.events import (
    CH_ALL, ch_ctl, ch_job, ch_user, control_event, notice_event, progress_event,
)


def test_channel_names_share_the_prefix():
    assert CH_ALL == "aw:all"
    assert ch_user("u1") == "aw:user:u1"
    assert ch_job("j1") == "aw:job:j1"
    assert ch_ctl("u1") == "aw:ctl:u1"


def test_message_shapes():
    assert control_event("close", "logout") == {"type": "control", "action": "close", "reason": "logout"}
    assert progress_event("j1", "parsing", 40) == {"type": "job.progress", "job_id": "j1", "stage": "parsing", "progress": 40}
    notice = notice_event("warning", "Maintenance", None)
    assert notice["type"] == "system.notice" and notice["level"] == "warning" and notice["expires_at"] is None
