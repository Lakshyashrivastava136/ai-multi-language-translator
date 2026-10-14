"""
AI Multi-Language Translator - Flask backend (200+ translatable languages,
1600+ detectable languages).

Endpoints
---------
GET  /                 Serve the UI.
GET  /api/languages    ?q=<search>  -> every language the app can translate.
GET  /api/health       Engine status and language counts.
POST /api/detect       {text} -> detected language (+ whether it is translatable).
POST /api/translate    {text, source, target} -> translated text.
POST /api/evaluate     {hypothesis, reference} -> BLEU score + similarity.

Engines: Google Translate, NLLB-200 (optional, local), MyMemory.
If no engine supports a pair directly, text is pivoted through English.

Environment variables
---------------------
NLLB_ENABLED=1        Load NLLB-200 (needs: transformers, sentencepiece, torch)
NLLB_MODEL=...        default facebook/nllb-200-distilled-600M
GLOTLID_ENABLED=1     Use GlotLID detection (needs: fasttext-wheel, huggingface_hub, numpy<2)
MAX_CHARS=20000       Maximum accepted text length

Production: gunicorn -w 1 --threads 8 app:app
"""

import difflib
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import langcodes
from deep_translator import GoogleTranslator, MyMemoryTranslator
from flask import Flask, jsonify, render_template, request
from langdetect import DetectorFactory, LangDetectException, detect_langs
from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu
from werkzeug.exceptions import HTTPException

DetectorFactory.seed = 0

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
NLLB_ENABLED = os.getenv("NLLB_ENABLED", "0") == "1"
NLLB_MODEL = os.getenv("NLLB_MODEL", "facebook/nllb-200-distilled-600M")
GLOTLID_ENABLED = os.getenv("GLOTLID_ENABLED", "0") == "1"
MAX_CHARS = int(os.getenv("MAX_CHARS", "20000"))

ENGINE_LIMITS = {"google": 4500, "mymemory": 450, "nllb": 400}
ENGINE_LABELS = {"google": "Google Translate", "nllb": "NLLB-200", "mymemory": "MyMemory"}

app = Flask(__name__)
log = logging.getLogger("translator")
logging.basicConfig(level=logging.INFO)


@app.errorhandler(HTTPException)
def handle_http_exception(e):
    return jsonify({"error": e.description or e.name}), e.code


@app.errorhandler(Exception)
def handle_unexpected_exception(e):
    app.logger.exception("Unhandled exception")
    return jsonify({"error": f"Internal server error: {e}"}), 500


# --------------------------------------------------------------------------
# Language registry
# --------------------------------------------------------------------------
REGISTRY: dict[str, dict] = {}
ALIASES: dict[str, str] = {}

FLORES_RE = re.compile(r"^[a-z]{3}_[A-Z][a-z]{3}$")

NLLB_KEY_OVERRIDES = {
    "zho_Hans": "zh-CN", "zho_Hant": "zh-TW", "arb_Arab": "ar", "pes_Arab": "fa",
    "khk_Cyrl": "mn", "azj_Latn": "az", "uzn_Latn": "uz", "zsm_Latn": "ms",
    "lvs_Latn": "lv", "ekk_Latn": "et", "npi_Deva": "ne", "ory_Orya": "or",
    "plt_Latn": "mg", "gaz_Latn": "om", "ydd_Hebr": "yi", "kmr_Latn": "ku",
    "tgl_Latn": "tl", "nob_Latn": "no", "swh_Latn": "sw", "quy_Latn": "qu",
    "ayr_Latn": "ay", "grn_Latn": "gn", "ckb_Arab": "ckb", "nya_Latn": "ny",
}


def _display_name(code: str) -> str:
    try:
        return langcodes.get(code).display_name()
    except Exception:
        return code


def _norm(code: str) -> str:
    return code.strip().replace("_", "-").lower()


def _alias(alias: str, key: str) -> None:
    ALIASES.setdefault(_norm(alias), key)


def _entry(key: str, name: str) -> dict:
    return REGISTRY.setdefault(
        key, {"key": key, "name": name, "google": None, "nllb": None, "mymemory": None}
    )


def resolve(code: str | None) -> str | None:
    """Turn any code (en, EN, en-US, hin, hin_Deva, iw ...) into a registry key."""
    if not code:
        return None
    c = _norm(code)
    if c in ALIASES:
        return ALIASES[c]
    base = re.split(r"[-_]", c)[0]
    if base in ALIASES:
        return ALIASES[base]
    try:
        short = langcodes.get(base).language
        return ALIASES.get(_norm(short))
    except Exception:
        return None


def _register_google() -> None:
    try:
        langs = GoogleTranslator().get_supported_languages(as_dict=True)
    except Exception as exc:
        log.warning("Could not load Google language list: %s", exc)
        return
    for name, code in langs.items():
        e = _entry(code, name.title())
        e["google"] = code
        _alias(code, code)
    for a, b in (("he", "iw"), ("jv", "jw"), ("fil", "tl")):
        if a in REGISTRY and b not in REGISTRY:
            _alias(b, a)
        elif b in REGISTRY and a not in REGISTRY:
            _alias(a, b)
    if "zh-CN" in REGISTRY:
        _alias("zh", "zh-CN")


def _register_mymemory() -> None:
    try:
        codes = MyMemoryTranslator(source="en-US", target="fr-FR").get_supported_languages(
            as_dict=True
        ).values()
    except Exception as exc:
        log.warning("Could not load MyMemory language list: %s", exc)
        return
    for code in codes:
        base = _norm(code).split("-")[0]
        key = ALIASES.get(_norm(code)) or ALIASES.get(base)
        if key is None:
            key = base
            _alias(base, key)
        e = _entry(key, _display_name(key))
        e["mymemory"] = e["mymemory"] or code
    if "en" in REGISTRY:
        REGISTRY["en"]["mymemory"] = "en-US"


def _register_nllb(flores_codes: list[str]) -> None:
    for flores in flores_codes:
        iso3, script = flores.split("_")
        key = NLLB_KEY_OVERRIDES.get(flores)
        if key is None:
            try:
                key = langcodes.get(iso3).language
            except Exception:
                key = iso3
        key = ALIASES.get(_norm(key), key)

        existing = REGISTRY.get(key)
        if existing and existing["nllb"] and existing["nllb"] != flores:
            key = f"{key}-{script}"
            existing = REGISTRY.get(key)

        name = existing["name"] if existing else _display_name(iso3)
        if not existing and "-" in key:
            name = f"{name} ({script})"
        e = _entry(key, name)
        e["nllb"] = flores
        _alias(key, key)
        _alias(flores, key)
        _alias(iso3, key)


# ---- NLLB-200 (local model, lazy) ----------------------------------------
_nllb = {"tok": None, "model": None, "device": "cpu"}
_nllb_lock = threading.RLock()


def _nllb_codes() -> list[str]:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(NLLB_MODEL)
    _nllb["tok"] = tok
    return sorted(t for t in tok.get_vocab() if FLORES_RE.match(t))


def _nllb_get():
    with _nllb_lock:
        if _nllb["model"] is None:
            import torch
            from transformers import AutoModelForSeq2SeqLM

            log.info("Loading %s ...", NLLB_MODEL)
            model = AutoModelForSeq2SeqLM.from_pretrained(NLLB_MODEL)
            _nllb["device"] = "cuda" if torch.cuda.is_available() else "cpu"
            _nllb["model"] = model.to(_nllb["device"]).eval()
        return _nllb["tok"], _nllb["model"], _nllb["device"]


def build_registry() -> None:
    _register_google()
    _register_mymemory()
    if NLLB_ENABLED:
        try:
            _register_nllb(_nllb_codes())
        except Exception as exc:
            log.warning("NLLB disabled (could not load tokenizer): %s", exc)
    log.info("Language registry ready: %d languages", len(REGISTRY))


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------
_glotlid = {"model": None, "failed": False}
_glotlid_lock = threading.Lock()


def _glotlid_model():
    with _glotlid_lock:
        if _glotlid["model"] is None and not _glotlid["failed"]:
            try:
                import fasttext
                from huggingface_hub import hf_hub_download

                path = hf_hub_download("cis-lmu/glotlid", "model.bin")
                _glotlid["model"] = fasttext.load_model(path)
            except Exception as exc:
                log.warning("GlotLID unavailable, using langdetect: %s", exc)
                _glotlid["failed"] = True
        return _glotlid["model"]


def _describe(raw: str, confidence: float, detector: str) -> dict:
    key = resolve(raw)
    if key:
        name, code = REGISTRY[key]["name"], key
    else:
        code = raw
        name = _display_name(raw.split("_")[0])
    return {
        "code": code,
        "label": name,
        "confidence": round(confidence, 3),
        "translatable": bool(key and _engines_for(key)),
        "detector": detector,
    }


def detect_language(text: str) -> dict | None:
    sample = " ".join(text.split())[:2000]
    if not sample:
        return None

    if GLOTLID_ENABLED:
        model = _glotlid_model()
        if model is not None:
            try:
                labels, probs = model.predict(sample, k=1)
                raw = labels[0].replace("__label__", "")
                return _describe(raw, float(probs[0]), "glotlid")
            except Exception as exc:
                log.warning("GlotLID predict failed: %s", exc)

    try:
        top = detect_langs(sample)[0]
    except LangDetectException:
        return None
    lang = top.lang
    # langdetect often mislabels very short English as Welsh/Somali/Tagalog.
    if len(sample) <= 40 and sample.isascii() and lang in {"cy", "so", "tl"}:
        lang = "en"
    return _describe(lang, top.prob, "langdetect")


# --------------------------------------------------------------------------
# Translation
# --------------------------------------------------------------------------
SENT_SPLIT = re.compile(r"(?<=[.!?\u0964\u0965\u3002\uff01\uff1f])\s+")


class TranslationError(Exception):
    pass


def chunk_text(text: str, limit: int) -> list[str]:
    chunks, cur = [], ""
    for sent in SENT_SPLIT.split(text):
        while len(sent) > limit:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(sent[:limit])
            sent = sent[limit:]
        if not cur:
            cur = sent
        elif len(cur) + 1 + len(sent) <= limit:
            cur = f"{cur} {sent}"
        else:
            chunks.append(cur)
            cur = sent
    if cur:
        chunks.append(cur)
    return chunks


def _engines_for(src: str, tgt: str | None = None) -> list[str]:
    s = REGISTRY[src]
    t = REGISTRY[tgt] if tgt else s
    order = [("google", True), ("nllb", NLLB_ENABLED), ("mymemory", True)]
    return [e for e, on in order if on and s[e] and t[e]]


def _parallel(fn, items, workers=4):
    if len(items) == 1:
        return [fn(items[0])]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, items))


def _run_engine(engine: str, chunks: list[str], src: str, tgt: str) -> list[str]:
    s, t = REGISTRY[src][engine], REGISTRY[tgt][engine]

    if engine == "nllb":
        tok, model, device = _nllb_get()
        import torch

        out: list[str] = []
        for i in range(0, len(chunks), 8):
            batch = chunks[i : i + 8]
            with _nllb_lock:
                tok.src_lang = s
                enc = tok(batch, return_tensors="pt", padding=True,
                          truncation=True, max_length=256).to(device)
                with torch.inference_mode():
                    gen = model.generate(
                        **enc,
                        forced_bos_token_id=tok.convert_tokens_to_ids(t),
                        max_new_tokens=256,
                        num_beams=4,
                    )
                out.extend(tok.batch_decode(gen, skip_special_tokens=True))
        return out

    if engine == "google":
        fn = lambda c: GoogleTranslator(source=s, target=t).translate(c)
    else:
        fn = lambda c: MyMemoryTranslator(source=s, target=t).translate(c)

    def checked(c):
        r = fn(c)
        if not r:
            raise TranslationError("empty result")
        return r

    return _parallel(checked, chunks)


def _translate_direct(text: str, src: str, tgt: str, engine: str) -> str:
    lines = text.split("\n")
    units, owner = [], []
    for i, line in enumerate(lines):
        if line.strip():
            for piece in chunk_text(line.strip(), ENGINE_LIMITS[engine]):
                units.append(piece)
                owner.append(i)
    results = _run_engine(engine, units, src, tgt)
    parts: list[list[str]] = [[] for _ in lines]
    for i, r in zip(owner, results):
        parts[i].append(r)
    return "\n".join(" ".join(p) for p in parts)


@lru_cache(maxsize=1024)
def cached_translate(text: str, src: str, tgt: str) -> tuple[str, str]:
    """Return (translated_text, engine_label). Failures are not cached."""
    errors = []
    for engine in _engines_for(src, tgt):
        try:
            return _translate_direct(text, src, tgt, engine), ENGINE_LABELS[engine]
        except Exception as exc:
            log.warning("%s failed for %s->%s: %s", engine, src, tgt, exc)
            errors.append(f"{ENGINE_LABELS[engine]} ({exc})")

    if "en" in REGISTRY and src != "en" and tgt != "en":
        if _engines_for(src, "en") and _engines_for("en", tgt):
            try:
                mid, e1 = cached_translate(text, src, "en")
                out, e2 = cached_translate(mid, "en", tgt)
                return out, f"{e1} -> {e2} (via English)"
            except Exception as exc:
                errors.append(f"English pivot ({exc})")

    raise TranslationError("; ".join(errors) or "No translation engine supports this language pair")


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/languages")
def api_languages():
    q = (request.args.get("q") or "").strip().lower()
    items = []
    for e in REGISTRY.values():
        engines = _engines_for(e["key"])
        if not engines:
            continue
        if q and q not in e["name"].lower() and q not in e["key"].lower():
            continue
        items.append({"code": e["key"], "name": e["name"],
                      "engines": [ENGINE_LABELS[x] for x in engines]})
    items.sort(key=lambda x: x["name"])
    return jsonify({"count": len(items), "languages": items})


@app.route("/api/health")
def api_health():
    return jsonify({
        "languages": sum(1 for e in REGISTRY.values() if _engines_for(e["key"])),
        "engines": {"google": True, "mymemory": True, "nllb": NLLB_ENABLED},
        "detector": "glotlid" if GLOTLID_ENABLED and not _glotlid["failed"] else "langdetect",
    })


@app.route("/api/detect", methods=["POST"])
def api_detect():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    result = detect_language(text)
    if result is None:
        return jsonify({"error": "Could not detect language"}), 422
    result["supported"] = result["translatable"]
    return jsonify(result)


@app.route("/api/translate", methods=["POST"])
def api_translate():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    source = data.get("source") or "auto"
    target = data.get("target") or "en"

    if not text:
        return jsonify({"error": "No text provided"}), 400
    if len(text) > MAX_CHARS:
        return jsonify({"error": f"Text too long (max {MAX_CHARS} characters)"}), 413

    tgt = resolve(target)
    if tgt is None or not _engines_for(tgt):
        return jsonify({"error": f"Unsupported target language: {target}"}), 400

    detected = None
    if source == "auto":
        detected = detect_language(text)
        if detected is None:
            return jsonify({"error": "Could not detect the language of this text"}), 422
        if not detected["translatable"]:
            return jsonify({
                "error": f"Detected {detected['label']}, which no translation engine supports yet.",
                "detected_code": detected["code"],
                "detected_label": detected["label"],
            }), 422
        src = detected["code"]
    else:
        src = resolve(source)
        if src is None or not _engines_for(src):
            return jsonify({"error": f"Unsupported source language: {source}"}), 400
        if src == tgt:
            return jsonify({"error": "Source and target languages must differ"}), 400

    base = {
        "detected_code": detected["code"] if detected else None,
        "detected_label": detected["label"] if detected else None,
        "confidence": detected["confidence"] if detected else None,
        "source_code": src,
        "target_code": tgt,
    }

    if src == tgt:
        return jsonify({**base, "translated_text": text, "engine": "none (already in target language)"})

    try:
        translated, engine = cached_translate(text, src, tgt)
    except TranslationError as exc:
        return jsonify({"error": f"Translation failed: {exc}"}), 502

    return jsonify({**base, "translated_text": translated, "engine": engine})


_NO_SPACE_SCRIPTS = re.compile(
    "[\u3040-\u30ff\u3400-\u9fff\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff]"
)


def _tokens(text: str) -> list[str]:
    text = text.lower()
    if _NO_SPACE_SCRIPTS.search(text):
        return [ch for ch in text if not ch.isspace()]
    return text.split()


@app.route("/api/evaluate", methods=["POST"])
def api_evaluate():
    data = request.get_json(silent=True) or {}
    hypothesis = (data.get("hypothesis") or "").strip()
    reference = (data.get("reference") or "").strip()

    if not hypothesis or not reference:
        return jsonify({"error": "Both a translation and a reference are required"}), 400

    hyp, ref = _tokens(hypothesis), _tokens(reference)
    n = max(1, min(4, len(hyp)))
    weights = tuple(1 / n for _ in range(n))
    bleu = sentence_bleu([ref], hyp, weights=weights,
                         smoothing_function=SmoothingFunction().method1)
    similarity = difflib.SequenceMatcher(None, reference.lower(), hypothesis.lower()).ratio()

    return jsonify({
        "bleu_score": round(bleu, 4),
        "similarity_percent": round(similarity * 100, 1),
    })


build_registry()

if __name__ == "__main__":
    app.run(debug=True)