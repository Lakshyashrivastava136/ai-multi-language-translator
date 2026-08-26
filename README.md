# 🌐 AI Multi-Language Translator

> An AI-powered web-based translator built with Flask that supports English, Hindi, and Telugu translation, automatic language detection, voice input, and translation accuracy evaluation.

[![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-Web%20Framework-black?logo=flask)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 🚀 Live Demo

### 👉 [Open AI Multi-Language Translator](YOUR_RENDER_LIVE_URL)

> **Note:** Replace `YOUR_RENDER_LIVE_URL` with your actual Render deployment URL.

---

## 📌 Project Overview

AI Multi-Language Translator is a web application designed to provide fast and simple translation between:

- 🇬🇧 English
- 🇮🇳 Hindi
- 🇮🇳 Telugu

The application provides automatic language detection, text translation, voice-based input, and translation quality evaluation.

The project is built with a Flask backend and a browser-based frontend.

---

## ✨ Features

### 🌍 Multi-Language Translation

Translate text between:

```text
English ↔ Hindi
English ↔ Telugu
Hindi ↔ Telugu
```

### 🔍 Automatic Language Detection

The application can automatically detect the input language when **Auto-detect** is selected.

Supported languages:

| Language | Code |
|----------|------|
| English | `en` |
| Hindi | `hi` |
| Telugu | `te` |

### 🎤 Voice Input

The application supports voice-based text input using the browser's speech recognition capabilities.

Users can:

1. Click the microphone button.
2. Speak into the microphone.
3. Convert speech into text.
4. Translate the recognized text.

> Microphone functionality depends on browser support and microphone permissions.

### ⚡ Translation Fallback System

The application uses a two-level translation strategy:

```text
User Input
    ↓
Google Translate
    ↓
If translation fails
    ↓
MyMemory Translator
    ↓
Translation Result
```

This provides a fallback when the primary translation service encounters an error.

### 📊 Translation Accuracy Evaluation

The application allows users to compare the generated translation against an expected/reference translation.

It calculates:

- **BLEU Score**
- **Similarity Percentage**

The BLEU score is calculated using NLTK, while character-level similarity is calculated using Python's `difflib`.

### 🛡️ JSON API Error Handling

The Flask backend returns JSON responses for API errors instead of Flask's default HTML error pages.

This makes the backend easier for the JavaScript frontend to consume.

---

# 🏗️ System Architecture

```text
                    ┌──────────────────────┐
                    │       User           │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Web Frontend       │
                    │ HTML / CSS / JS      │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │    Flask Backend     │
                    │       app.py         │
                    └──────────┬───────────┘
                               │
                 ┌─────────────┼─────────────┐
                 │             │             │
                 ▼             ▼             ▼
          Language        Translation    Evaluation
          Detection        Services       Engine
                 │             │             │
                 │      ┌──────┴──────┐      │
                 │      ▼             ▼      │
                 │   Google        MyMemory  │
                 │   Translate      Fallback │
                 │                           │
                 └─────────────┬─────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Translation Result   │
                    └──────────────────────┘
```

---

# 🔌 API Endpoints

The Flask application exposes the following endpoints.

## `GET /`

Serves the translator web interface.

---

## `POST /api/detect`

Detects the language of the provided text.

### Request

```json
{
  "text": "Hello, how are you?"
}
```

### Response

```json
{
  "code": "en",
  "label": "English",
  "supported": true
}
```

---

## `POST /api/translate`

Translates the provided text.

### Request

```json
{
  "text": "Hello, how are you?",
  "source": "en",
  "target": "te"
}
```

### Response

```json
{
  "translated_text": "...",
  "engine": "Google Translate",
  "detected_code": null,
  "detected_label": null
}
```

When automatic detection is selected:

```json
{
  "text": "Hello, how are you?",
  "source": "auto",
  "target": "te"
}
```

---

## `POST /api/evaluate`

Evaluates a generated translation against a reference translation.

### Request

```json
{
  "hypothesis": "How are you?",
  "reference": "How are you?"
}
```

### Response

```json
{
  "bleu_score": 1.0,
  "similarity_percent": 100.0
}
```

---

# 🧠 Technologies Used

## Backend

- Python
- Flask
- Gunicorn

## Translation

- `deep-translator`
- Google Translate
- MyMemory Translator

## Language Detection

- `langdetect`

## Translation Evaluation

- NLTK
- BLEU Score
- Python `difflib`

## Frontend

- HTML
- CSS
- JavaScript
- Browser Speech Recognition API

## Deployment

- GitHub
- Render

---

# 📁 Project Structure

```text
multi-language-translator/
│
├── templates/
│   └── index.html
│
├── app.py
├── requirements.txt
├── Procfile
├── render.yaml
├── .gitignore
└── README.md
```

### `app.py`

Contains the Flask backend, API routes, language detection, translation logic, fallback translation system, and evaluation functionality.

### `templates/index.html`

Contains the web interface and frontend JavaScript.

### `requirements.txt`

Contains the Python dependencies required to run the application.

### `Procfile`

Defines the production command used to run the Flask application.

### `render.yaml`

Contains deployment configuration for Render.

### `.gitignore`

Prevents unnecessary files such as virtual environments and Python cache files from being committed.

---

# ⚙️ Installation

## 1. Clone the repository

```bash
git clone https://github.com/vishalkoripala/multi-language-translator.git
```

```bash
cd multi-language-translator
```

## 2. Create a virtual environment

### Windows

```powershell
python -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

# ▶️ Run Locally

Start the Flask application:

```bash
python app.py
```

The application will start at:

```text
http://127.0.0.1:5000
```

Open that address in your browser.

---

# 🧪 Testing

The application can be tested using:

### Text Translation

```text
Input:
Hello, how are you?

From:
English

To:
Telugu
```

### Auto Detection

```text
Input:
नमस्ते

From:
Auto-detect

Expected:
Hindi
```

### Telugu

```text
Input:
నమస్కారం

From:
Auto-detect

Expected:
Telugu
```

### Voice Input

Click the microphone button and speak a supported language.

### Translation Evaluation

Provide:

```text
Generated Translation
        +
Expected Translation
```

The system returns:

```text
BLEU Score
Similarity Percentage
```

---

# 🔄 Translation Workflow

```text
1. User enters text
        ↓
2. User selects source language
        ↓
3. Auto-detection if required
        ↓
4. Target language validation
        ↓
5. Google Translate request
        ↓
6. If Google fails → MyMemory fallback
        ↓
7. Translation returned
        ↓
8. User can compare translation accuracy
```

---

# 🌐 Deployment

This project is configured for deployment as a Flask web service.

## Production server

The application uses Gunicorn to serve Flask in production:

```bash
gunicorn app:app
```

## Render

The project includes:

```text
render.yaml
Procfile
```

These files provide the configuration required for deployment.

After deployment, the application can be accessed through the public Render URL.

### Live Application

👉 **[Launch the Translator](YOUR_RENDER_LIVE_URL)**

---

# 🔐 Important Notes

The project uses external translation services through `deep-translator`.

The application does **not** use an official Google Cloud Translation API key.

Instead, Google Translate is accessed through the translation library used by the project, with MyMemory serving as a fallback translation service.

External translation services may experience:

- Rate limits
- Temporary failures
- Network problems
- Service changes

The fallback system attempts to provide another translation route when the primary service fails.

---

# ⚠️ Current Limitations

- Translation quality depends on the external translation services.
- Automatic language detection may not correctly identify every possible input.
- Romanized languages such as Telugu written using English characters may not always be detected correctly.
- Browser speech recognition depends on browser support and microphone permissions.
- The application currently focuses on English, Hindi, and Telugu.

---

# 🔮 Future Improvements

Possible future enhancements include:

- Support for additional Indian languages
- Improved Romanized-language detection
- Better translation quality evaluation
- Translation history
- Copy-to-clipboard functionality
- Downloadable translations
- User accounts
- Multiple translation providers
- Official translation APIs
- Improved speech recognition
- Text-to-speech output
- Mobile-responsive improvements
- Translation confidence scoring

---

# 🎯 Use Cases

This project can be useful for:

- Students learning different languages
- Basic multilingual communication
- Educational demonstrations
- Translation experiments
- NLP demonstrations
- Speech recognition demonstrations
- Language detection experiments
- Machine translation evaluation

---

# 📚 Learning Outcomes

This project demonstrates practical usage of:

- Flask REST APIs
- Python web development
- Natural Language Processing
- Language detection
- Machine translation
- Speech recognition
- BLEU evaluation
- String similarity
- API fallback strategies
- Git and GitHub
- Cloud deployment
- Production Flask serving

---

# 👨‍💻 Author

**Vishal Koripala**

GitHub:  
https://github.com/vishalkoripala

---

# ⭐ Project

If you find this project useful, consider giving the repository a ⭐ on GitHub.

Repository:

https://github.com/vishalkoripala/multi-language-translator

Live Demo:

YOUR_RENDER_LIVE_URL

---

## 📄 License

This project is available for educational and development purposes.
