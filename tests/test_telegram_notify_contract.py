from __future__ import annotations

from types import SimpleNamespace


def test_run_add_notify_uses_local_completion_and_warns_on_missing_pdf(tmp_path, monkeypatch):
    from applycling import pipeline, tracker

    class FakeNotifier:
        def __init__(self) -> None:
            self.messages: list[str] = []
            self.documents: list[tuple[str, str]] = []

        def notify(self, text: str) -> None:
            self.messages.append(text)

        def send_document(self, path, caption: str = "") -> None:
            self.documents.append((path.name, caption))

    class FakeStore:
        def update_job(self, job_id: str, **fields):
            return None

    job = tracker.Job(
        id="job_123",
        title="Platform Engineer",
        company="ExampleCo",
        date_added="2026-04-27T00:00:00Z",
        date_updated="2026-04-27T00:00:00Z",
    )
    result = pipeline.AddResult(
        run_id="run_123",
        job=job,
        resume_tailored="resume",
        fit_summary="Strong fit.",
    )

    monkeypatch.setattr(
        "applycling.scraper.fetch_job_posting",
        lambda url, model, provider=None: (
            SimpleNamespace(
                title="Platform Engineer",
                company="ExampleCo",
                description="Build platforms.",
                company_url=None,
            ),
            None,
        ),
    )
    monkeypatch.setattr("applycling.storage.load_config", lambda: {"model": "stub", "provider": "stub"})
    monkeypatch.setattr("applycling.storage.load_profile", lambda: {})
    monkeypatch.setattr("applycling.storage.load_stories", lambda: "")
    monkeypatch.setattr("applycling.storage.load_linkedin_profile", lambda: None)
    monkeypatch.setattr("applycling.storage.load_applicant_profile", lambda: {})
    monkeypatch.setattr("applycling.storage.load_resume", lambda: "base resume")
    monkeypatch.setattr("applycling.tracker.get_store", lambda: FakeStore())
    monkeypatch.setattr("applycling.pipeline.run_add", lambda **kwargs: result)

    def fake_persist(result, output_root=None, generate_docx=False, generate_run_log=True):
        folder = tmp_path / "package"
        folder.mkdir()
        (folder / "resume.pdf").write_bytes(b"%PDF-fake")
        return folder

    monkeypatch.setattr("applycling.pipeline.persist_add_result", fake_persist)

    notifier = FakeNotifier()
    folder = pipeline.run_add_notify("https://example.com/job", notifier, output_root=tmp_path)

    messages = "\n".join(notifier.messages)
    assert folder == tmp_path / "package"
    assert ("resume.pdf", "Resume — Platform Engineer @ ExampleCo") in notifier.documents
    assert "Missing cover_letter.pdf" in messages
    assert "Local package:" in messages
    assert "Storage: local validation/private-use artifacts." in messages
    assert "Notion" not in messages

