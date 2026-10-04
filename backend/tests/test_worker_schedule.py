from app.worker import celery_app


def test_beat_schedules_outbox_dispatch_and_stalled_job_recovery() -> None:
    schedule = celery_app.conf.beat_schedule

    assert schedule["dispatch-investigation-outbox"]["task"] == "agent_zero.dispatch_outbox"
    assert schedule["dispatch-investigation-outbox"]["schedule"] == 2.0
    assert (
        schedule["recover-stalled-investigations"]["task"]
        == "agent_zero.recover_stalled_investigations"
    )
    assert schedule["recover-stalled-investigations"]["schedule"] == 60.0
    assert "agent_zero.process_investigation" in celery_app.tasks
