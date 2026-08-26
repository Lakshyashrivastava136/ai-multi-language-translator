# 🌍 AI Multi-Language Translator

A web-based multilingual translation system that supports text and voice input, automatic language detection, and real-time translation.

## 🚀 Features

- 🌐 Translate between multiple languages (English, Hindi, Telugu)
- 🎤 Voice input (Speech → Text)
- 🧠 Automatic language detection
- ⚡ Real-time translation
- 📊 Translation evaluation (BLEU score & text similarity)

## 🧠 How It Works

The system follows this pipeline:

`Speech/Text Input → Speech Recognition → Language Detection → Translation → Output`

Step-by-step:

1. **Input** — User enters text OR uses voice input
2. **Speech Recognition (optional)** — Converts speech into text using the browser's Web Speech API
3. **Language Detection** — Automatically detects the input language using `langdetect` (runs locally, no external API call)
4. **Translation** — Tries `deep-translator`'s Google Translate backend first; if that fails (rate limiting, a changed page layout — recurring issues with this scraping-based approach), it automatically retries via MyMemory, a second, independent, keyless translation service
5. **Output** — Displays the translated text, with an optional accuracy check against a reference translation you supply

## 🛠️ Tech Stack

- **Frontend:** HTML, CSS, JavaScript (Web Speech API for voice input)
- **Backend:** Flask (Python)
- **Libraries:**
  - `deep-translator` – translation (Google Translate backend)
  - `langdetect` – offline language detection
  - `nltk` – BLEU score
  - `difflib` – similarity calculation

> **Note on the original spec:** it listed `googletrans` for translation/detection. This build uses `deep-translator` + `langdetect` instead, because `googletrans` scrapes an undocumented Google endpoint that breaks every time Google changes it — and, as it turns out, so does `deep-translator`'s Google backend, for the same reason (it's still scraping a webpage, just through a better-maintained wrapper). That's why translation automatically falls back to MyMemory when Google fails, instead of relying on one scraping-based source alone. `transformers` isn't wired into the live pipeline yet — see *Future Improvements* for using it as a custom local model.

## 📂 Project Structure

```
translator-project/
├── app.py
├── requirements.txt
├── Procfile
├── render.yaml
├── runtime.txt
└── templates/
    └── index.html
```

## ▶️ How to Run Locally

1. Clone the repository:
   ```
   git clone https://github.com/vishalkoripala/translator-project.git
   cd translator-project
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the app:
   ```
   python app.py
   ```
4. Open in browser: http://127.0.0.1:5000

## 🌐 Deployment

Deployed on Render **as a Web Service** (not a Static Site — a Static Site only serves files and never runs `app.py`, so none of the `/api/*` routes would exist, and Render would return its own HTML for those paths instead. That HTML-instead-of-JSON response is exactly what breaks the frontend with a `res.json()` parsing error).

Two ways to set it up:

- **Blueprint (recommended):** the repo includes `render.yaml`. In the Render dashboard, choose **New → Blueprint**, point it at this repo, and Render reads the service type, build command, and start command from that file directly — nothing to fill in by hand.
- **Manual:** choose **New → Web Service**, then set:
  - Build command: `pip install -r requirements.txt`
  - Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`

Either way, `runtime.txt` pins the Python version, and the explicit `--bind 0.0.0.0:$PORT` matters: Render assigns the port at runtime, and gunicorn's default (`127.0.0.1:8000`) isn't reachable from outside the container.

## 📌 Example

**Input:** Hello, how are you?
**Output:** नमस्ते, आप कैसे हैं?

## 🎯 Key Highlights

- Supports voice + text input
- Uses auto language detection
- Built on a pretrained NLP-based translation service
- Includes evaluation metrics (BLEU score, text similarity) you can run against your own reference translation, right in the UI

## 📚 Future Improvements

- Add more languages
- Improve UI/UX
- Add speech-to-speech translation
- Swap in custom-trained `transformers` models instead of the Google Translate backend
