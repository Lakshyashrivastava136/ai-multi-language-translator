"""
AI Multi-Language Translator - Flask backend.

Endpoints
---------
GET  /                Serve the UI.
POST /api/detect       {text} -> detected language code + label.
POST /api/translate    {text, source, target} -> translated text.
POST /api/evaluate     {hypothesis, reference} -> BLEU score + similarity.

Implementation notes
---------------------
The original spec calls for `googletrans`. That package scrapes an
undocumented Google endpoint and breaks often when Google tweaks it -
see the long-running issue list on its GitHub repo. This build uses
`deep-translator` instead: it talks to the same Google Translate web
endpoint, but is actively maintained and raises clear exceptions
instead of silently returning malformed JSON.

Language detection uses `langdetect`, which runs entirely locally (a
bundled n-gram model, no network call). That keeps "what language is
this?" working even in the moment a translation call fails, and it's
one less thing that depends on an external service being up.

Translation itself calls Google Translate first and, if that raises
anything (rate limiting, a changed page layout, a transient network
error - all documented, recurring issues on deep-translator's tracker
because it works by scraping a webpage, not calling a real API),
automatically retries the same request against MyMemory, a second,
independent, keyless translation service with a real JSON API. Two
unrelated backends failing in the same request is far less likely
than one, so this is the single biggest reliability lever available
without requiring an API key from you.

BLEU (via nltk) and a character-level similarity ratio (via difflib)
power the "check translation accuracy" feature: paste in the
translation you expected, and compare it against what the model
produced.

Every response from this app - including 404s, wrong-method 405s, and
any unhandled bug - is JSON, never Flask's default HTML error page.
That matters because the frontend calls `res.json()` on every response;
an HTML page in that spot throws "Unexpected token '<'" and looks like
the request vanished, even though the server did respond.
"""

from flask import Flask, render_template, request, jsonify
from werkzeug.exceptions import HTTPException
from deep_translator import GoogleTranslator, MyMemoryTranslator
from langdetect import detect, DetectorFactory, LangDetectException
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
import difflib

DetectorFactory.seed = 0  # langdetect is otherwise non-deterministic

app = Flask(__name__)


@app.errorhandler(HTTPException)
def handle_http_exception(e):
    """Wrong URL, wrong HTTP method, oversized body, etc. Flask's default
    for these is an HTML page - fine for a browser, but it silently breaks
    a frontend that expects every /api/* response to be JSON (that's the
    'Unexpected token < in JSON' class of error). Route/method mistakes
    now come back as JSON like everything else."""
    return jsonify({"error": e.description or e.name}), e.code


@app.errorhandler(Exception)
def handle_unexpected_exception(e):
    """Last-resort safety net for any bug that isn't already caught -
    keeps a genuine 500 as JSON too, instead of Flask's debug traceback
    page or a generic HTML error page (the same 'HTML where JSON was
    expected' failure, just from a different cause)."""
    app.logger.exception("Unhandled exception")
    return jsonify({"error": f"Internal server error: {e}"}), 500


SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "te": "Telugu",
}

# MyMemory identifies languages with locale-style codes rather than the
# plain ISO codes Google Translate (and this app) use everywhere else.
MYMEMORY_CODES = {"en": "en-US", "hi": "hi-IN", "te": "te-IN"}


def detect_language(text: str):
    """Detect one of the three languages supported by this application."""

    text = text.strip()

    if not text:
        return None

    # Hindi / Devanagari script
    if any('\u0900' <= ch <= '\u097F' for ch in text):
        return "hi"

    # Telugu script
    if any('\u0C00' <= ch <= '\u0C7F' for ch in text):
        return "te"

    # English / Latin ASCII text
    # This prevents langdetect from misclassifying short English
    # sentences such as "Hello, how are you?" as Welsh ("cy").
    if all(ord(ch) < 128 for ch in text):
        return "en"

    # Fallback to langdetect
    try:
        detected = detect(text)

        if detected in SUPPORTED_LANGUAGES:
            return detected

    except LangDetectException:
        pass

    return None


def run_translation(text: str, source: str, target: str):
    """Translate via Google Translate, falling back to MyMemory on failure.

    Returns (translated_text, engine_name, error_message). Exactly one of
    translated_text/error_message is set.
    """
    try:
        result = GoogleTranslator(source=source, target=target).translate(text)
        if result:
            return result, "Google Translate", None
    except Exception as exc:
        google_error = str(exc)
    else:
        google_error = "returned an empty result"

    try:
        mm_source = MYMEMORY_CODES.get(source, source)
        mm_target = MYMEMORY_CODES.get(target, target)
        result = MyMemoryTranslator(source=mm_source, target=mm_target).translate(text)
        if result:
            return result, "MyMemory", None
        mymemory_error = "returned an empty result"
    except Exception as exc:
        mymemory_error = str(exc)

    return None, None, f"Google Translate ({google_error}); MyMemory ({mymemory_error})"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/detect", methods=["POST"])
def api_detect():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"error": "No text provided"}), 400

    code = detect_language(text)
    if code is None:
        return jsonify({"error": "Could not detect language"}), 422

    return jsonify({
        "code": code,
        "label": SUPPORTED_LANGUAGES.get(code, code.upper()),
        "supported": code in SUPPORTED_LANGUAGES,
    })


@app.route("/api/translate", methods=["POST"])
def api_translate():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    source = data.get("source", "auto")
    target = data.get("target", "en")

    if not text:
        return jsonify({"error": "No text provided"}), 400
    if target not in SUPPORTED_LANGUAGES:
        return jsonify({"error": "Unsupported target language"}), 400
    if source != "auto" and source not in SUPPORTED_LANGUAGES:
        return jsonify({"error": "Unsupported source language"}), 400
    if source != "auto" and source == target:
        return jsonify({"error": "Source and target languages must differ"}), 400

    detected_code = None
    src_for_translation = source

    if source == "auto":
        detected_code = detect_language(text)

    if detected_code not in SUPPORTED_LANGUAGES:
        return jsonify({
            "error": "Could not reliably detect English, Hindi, or Telugu."
        }), 422

    src_for_translation = detected_code

    translated, engine, error = run_translation(text, src_for_translation, target)

    if error:
        return jsonify({"error": f"Translation failed: {error}"}), 502

    return jsonify({
        "translated_text": translated,
        "engine": engine,
        "detected_code": detected_code,
        "detected_label": SUPPORTED_LANGUAGES.get(detected_code, detected_code) if detected_code else None,
    })


@app.route("/api/evaluate", methods=["POST"])
def api_evaluate():
    data = request.get_json(silent=True) or {}
    hypothesis = (data.get("hypothesis") or "").strip()
    reference = (data.get("reference") or "").strip()

    if not hypothesis or not reference:
        return jsonify({"error": "Both a translation and a reference are required"}), 400

    hyp_tokens = hypothesis.lower().split()
    ref_tokens = reference.lower().split()

    # Standard BLEU averages 1- through 4-gram precision. On short sentences
    # (very common when testing a translator by hand) there aren't enough
    # tokens to form 3- or 4-grams, which unfairly tanks the score even for
    # a perfect match. Capping the n-gram order to the hypothesis length
    # keeps BLEU meaningful at any sentence length.
    n = max(1, min(4, len(hyp_tokens)))
    weights = tuple(1 / n for _ in range(n))
    smoothing = SmoothingFunction().method1
    bleu = sentence_bleu([ref_tokens], hyp_tokens, weights=weights, smoothing_function=smoothing)
    similarity = difflib.SequenceMatcher(None, reference.lower(), hypothesis.lower()).ratio()

    return jsonify({
        "bleu_score": round(bleu, 4),
        "similarity_percent": round(similarity * 100, 1),
    })


if __name__ == "__main__":
    app.run(debug=True)
