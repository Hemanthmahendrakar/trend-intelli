from datetime import timedelta

from tests.helpers import NOW
from trendintel.collectors.base import BaseCollector, CollectorConfigError
from trendintel.config import Settings
from trendintel.models import Article
from trendintel.pipeline import Pipeline, collect_in_memory


class FakeRepo:
    def __init__(self):
        self.runs = {}
        self.inserted = []
        self.snapshots = []
        self.stored = []

    def upsert_source(self, name, kind, base_url):
        return len(name)

    def start_run(self, source_id):
        run_id = len(self.runs) + 1
        self.runs[run_id] = {"status": "running"}
        return run_id

    def finish_run(self, run_id, status, fetched=0, inserted=0, error=None):
        self.runs[run_id] = {"status": status, "fetched": fetched, "inserted": inserted, "error": error}

    def insert_articles(self, source_id, run_id, articles):
        self.inserted.extend(articles)
        return len(articles)

    def fetch_articles_since(self, since):
        return self.stored

    def first_collected_at(self):
        return NOW - timedelta(days=3)

    def save_trend_snapshot(self, scores, computed_at):
        self.snapshots.append((list(scores), computed_at))


class Good(BaseCollector):
    name, key = "Good", "good"

    def fetch(self):
        return [
            Article(source="Good", title="Hello World", url="https://x.com/1?utm_source=a"),
            Article(source="Good", title="hello world!", url="https://x.com/2"),  # duplicate title
            Article(source="Good", title="", url="https://x.com/3"),  # unusable
        ]


class Failing(BaseCollector):
    name, key = "Failing", "failing"

    def fetch(self):
        raise RuntimeError("source exploded")


class Unconfigured(BaseCollector):
    name, key = "Unconfigured", "unconfigured"

    def fetch(self):
        raise CollectorConfigError("no credentials")


def make_pipeline(repo=None):
    settings = Settings()
    repo = repo or FakeRepo()
    return Pipeline(settings, repo, [Failing(None, settings), Good(None, settings), Unconfigured(None, settings)]), repo


def test_failures_are_isolated_and_recorded():
    pipeline, repo = make_pipeline()
    outcomes = {o.source: o for o in pipeline.collect()}
    assert outcomes["Failing"].status == "failed" and "exploded" in outcomes["Failing"].error
    assert outcomes["Unconfigured"].status == "skipped"
    assert outcomes["Good"].status == "success" and outcomes["Good"].fetched == 3 and outcomes["Good"].inserted == 1
    assert [r["status"] for r in repo.runs.values()] == ["failed", "success", "skipped"]
    assert repo.inserted[0].url == "https://x.com/1"  # cleaned URL stored


def test_collect_in_memory_skips_bad_sources():
    settings = Settings()
    articles = collect_in_memory([Failing(None, settings), Good(None, settings), Unconfigured(None, settings)])
    assert len(articles) == 1


def test_analyze_persists_snapshot():
    repo = FakeRepo()
    repo.stored = [
        Article(id=i, source=s, title="GPT-5 launch news", url=f"https://x.com/{i}", published_at=NOW - timedelta(hours=i), collected_at=NOW - timedelta(hours=i))
        for i, s in enumerate(["A", "B", "C"], start=1)
    ]
    pipeline, _ = make_pipeline(repo)
    scores = pipeline.analyze(NOW)
    assert scores and repo.snapshots
    assert repo.snapshots[0][1] == NOW


def test_analyze_without_articles_does_nothing():
    pipeline, repo = make_pipeline()
    assert pipeline.analyze(NOW) == [] and repo.snapshots == []
