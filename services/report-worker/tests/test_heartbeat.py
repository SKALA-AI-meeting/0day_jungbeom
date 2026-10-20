"""완료 기준: worker heartbeat 파일(compose healthcheck가 보는 파일)이 갱신된다."""

import time

from report_worker.heartbeat import beat


def test_beat_writes_current_time(tmp_path, monkeypatch):
    path = tmp_path / "heartbeat"
    monkeypatch.setenv("HEARTBEAT_PATH", str(path))
    assert beat() == path
    assert abs(int(path.read_text()) - time.time()) < 5
