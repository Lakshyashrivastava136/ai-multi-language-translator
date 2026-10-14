import app as app_module


def fake_detect(code="en", label="English"):
    return lambda text: {
        "code": code, "label": label, "confidence": 0.99,
        "translatable": True, "detector": "mock",
    }


# ---------- languages & registry ----------
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["languages"] >= 100


def test_languages_include_core(client):
    data = client.get("/api/languages").get_json()
    codes = {lang["code"] for lang in data["languages"]}
    assert {"en", "hi", "te"} <= codes
    assert data["count"] >= 100


def test_languages_search(client):
    data = client.get("/api/languages?q=tamil").get_json()
    assert any("tamil" in lang["name"].lower() for lang in data["languages"])


def test_resolve_variants():
    assert app_module.resolve("EN") == "en"
    assert app_module.resolve("en-US") == "en"
    assert app_module.resolve("hin") == "hi"
    assert app_module.resolve("xx") is None


# ---------- chunking ----------
def test_chunk_text_respects_limit():
    text = ("This is a sentence. " * 100).strip()
    chunks = app_module.chunk_text(text, 100)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join("".join(chunks).split()) == "".join(text.split())


def test_chunk_text_splits_huge_sentence():
    chunks = app_module.chunk_text("a" * 250, 100)
    assert len(chunks) == 3
    assert all(len(c) <= 100 for c in chunks)


# ---------- translate: validation ----------
def test_translate_requires_text(client):
    r = client.post("/api/translate", json={"text": "  ", "target": "hi"})
    assert r.status_code == 400


def test_translate_rejects_unknown_target(client):
    r = client.post("/api/translate", json={"text": "Hello", "target": "zzz"})
    assert r.status_code == 400


def test_translate_rejects_same_language(client):
    r = client.post("/api/translate", json={"text": "Hello", "source": "en", "target": "en"})
    assert r.status_code == 400


def test_translate_rejects_too_long(client):
    text = "a" * (app_module.MAX_CHARS + 1)
    r = client.post("/api/translate", json={"text": text, "target": "hi"})
    assert r.status_code == 413


# ---------- translate: engines (mocked, so tests run offline) ----------
def test_translate_success(client, monkeypatch):
    monkeypatch.setattr(
        app_module, "_run_engine",
        lambda engine, chunks, s, t: [f"[{t}] {c}" for c in chunks],
    )
    r = client.post("/api/translate", json={"text": "Hello", "source": "en", "target": "hi"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["translated_text"] == "[hi] Hello"
    assert body["engine"] == "Google Translate"


def test_translate_falls_back_to_mymemory(client, monkeypatch):
    def fake(engine, chunks, s, t):
        if engine == "google":
            raise RuntimeError("blocked")
        return ["ok" for _ in chunks]

    monkeypatch.setattr(app_module, "_run_engine", fake)
    r = client.post("/api/translate", json={"text": "Hello", "source": "en", "target": "hi"})
    assert r.status_code == 200
    assert r.get_json()["engine"] == "MyMemory"


def test_translate_returns_502_when_all_engines_fail(client, monkeypatch):
    def boom(engine, chunks, s, t):
        raise RuntimeError("down")

    monkeypatch.setattr(app_module, "_run_engine", boom)
    r = client.post("/api/translate", json={"text": "Hello", "source": "en", "target": "hi"})
    assert r.status_code == 502


def test_translate_auto_detect(client, monkeypatch):
    monkeypatch.setattr(app_module, "detect_language", fake_detect())
    monkeypatch.setattr(app_module, "_run_engine", lambda e, chunks, s, t: ["namaste"] * len(chunks))
    r = client.post("/api/translate", json={"text": "Hello", "source": "auto", "target": "hi"})
    body = r.get_json()
    assert r.status_code == 200
    assert body["detected_code"] == "en"


# ---------- detect ----------
def test_detect_requires_text(client):
    assert client.post("/api/detect", json={"text": ""}).status_code == 400


def test_detect_english(client):
    r = client.post("/api/detect", json={"text": "Hello, how are you doing today my friend?"})
    assert r.status_code == 200
    assert r.get_json()["code"] == "en"


# ---------- evaluate ----------
def test_evaluate_perfect_match(client):
    s = "the cat sat on the mat"
    r = client.post("/api/evaluate", json={"hypothesis": s, "reference": s})
    body = r.get_json()
    assert body["bleu_score"] == 1.0
    assert body["similarity_percent"] == 100.0


def test_evaluate_requires_both_fields(client):
    assert client.post("/api/evaluate", json={"hypothesis": "hi"}).status_code == 400


# ---------- errors are always JSON ----------
def test_404_is_json(client):
    r = client.get("/no-such-page")
    assert r.status_code == 404
    assert r.is_json


def test_405_is_json(client):
    r = client.get("/api/translate")
    assert r.status_code == 405
    assert r.is_json