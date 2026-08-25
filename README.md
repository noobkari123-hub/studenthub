
## AI Teddy — Groq free-tier setup

This build uses Groq over HTTPS with Python `requests`; no Groq SDK, Gemini SDK, or OpenAI SDK is required.
Create a Groq API key and put it in `.env` as `GROQ_API_KEY`. The default model is `qwen/qwen3.6-27b`.
Groq's free plan has rate/token limits, so it is free within those limits rather than unlimited.

Example `.env`:
```env
AI_API_PROVIDER=groq
GROQ_API_KEY=your_key_here
GROQ_MODEL=qwen/qwen3.6-27b
GROQ_FALLBACK_MODEL=groq/compound
AI_PROVIDER_ORDER=groq
AI_FALLBACK_ENABLED=true
```

# Student Hub

Student Hub is a Flask-based student platform with a friendly AI Teddy, search, calculators, study tools, authentication, a SQLite user database, and an admin login-activity dashboard.

## Main behavior

- **AI-first search:** when `AI_API_KEY` is configured, normal study questions are answered by the AI model first. Student Hub does not automatically turn every question into a web lookup.
- **Explicit web sources:** use **Browse web sources** when the student wants external source material.
- **Deterministic math:** supported calculations are solved locally before AI/web lookup.
- **AI Teddy:** Explain, Make it Simple, Generate MCQs, Practice Questions, Flashcards, Exam Notes, and Summarize.
- **Authentication:** email/password signup and login, secure password hashing, sessions, logout, and Google OAuth.
- **Database:** SQLite stores users and successful login events, including account creation, last login, method, IP and user-agent.
- **Admin dashboard:** users listed in `ADMIN_EMAILS` can open `/admin/users` to see registered accounts and login history.
- **Responsive UI:** modern Student Hub design, mobile layout, theme support, polished authentication pages, and AI-helper interactions.

## Setup

```bash
cd student-hub
python -m venv venv
# Windows:
venv\\Scripts\\activate
# macOS/Linux:
# source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Open `http://127.0.0.1:5000` in the browser.

## Environment variables

Never commit `.env` or put secrets in frontend JavaScript.

```text
FLASK_SECRET_KEY=use-a-long-random-secret
FLASK_ENV=development
SESSION_COOKIE_SECURE=false

# AI tutor
AI_API_KEY=your-real-key
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
AI_API_PROVIDER=auto
AI_PROVIDER_ORDER=openai,anthropic
AI_FALLBACK_ENABLED=true
AI_MODEL=gpt-5.6-luna
ANTHROPIC_MODEL=claude-sonnet-4-6

# Optional explicit web-source provider
SEARCH_API_KEY=your-search-key
SEARCH_API_PROVIDER=brave

# Google OAuth Web Application
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:5000/auth/google/callback

# Administrator emails, comma separated
ADMIN_EMAILS=your-email@example.com

# Optional persistent database location
# STUDENT_HUB_DB_PATH=./student_hub.db
```

### Google OAuth

Create a Google OAuth **Web application** credential and register the exact callback URL used by Student Hub. For local development, the easiest stable setup is:

```text
http://127.0.0.1:5000/auth/google/callback
```

If you open Student Hub through a LAN address such as `192.168.1.12:5000`, use a callback URL registered for that address instead and set `GOOGLE_REDIRECT_URI` to the exact same value. Google will reject a callback URL that does not exactly match an authorized redirect URI.

The Google client ID and secret stay on the Flask server. The browser only follows the OAuth redirect.

## Database and admin dashboard

The default database is `student_hub.db` in the project directory. It is created automatically when Flask starts.

The database contains:

- `users` — name, email, password hash, Google ID, creation time, last login
- `login_events` — successful login method, time, IP address and browser/device information
- `searches` — search history used by the application
- study-related tables used by the existing tools

Set `ADMIN_EMAILS` to the email of your Student Hub account. After logging in, use **Users** in the header or open:

```text
/admin/users
```

Do not expose the SQLite file publicly. For production hosting, use persistent storage/database infrastructure.

## AI without a key

The app remains honest when no AI key is configured. Math calculations continue to work locally, greetings receive a friendly local response, and other searches fall back to verified source lookup. It does not fabricate an AI answer.

With `AI_API_KEY` configured, the AI model becomes the primary answer engine. Search resources are supplementary and can be explicitly requested.

## Project structure

```text
student-hub/
├── app.py
├── config/config.py
├── models/models.py
├── routes/
│   ├── main.py
│   ├── search.py
│   └── coding.py
├── services/
│   ├── ai_service.py
│   ├── search_service.py
│   ├── math_service.py
│   └── code_execution_service.py
├── templates/
└── static/
    ├── css/
    └── js/
```


## AI Teddy chat

AI Teddy is the conversational AI area of Student Hub. It is free for students and requires a Student Hub account so conversations can be saved privately. Each user gets their own persistent chats, message history, automatic titles, rename/delete controls, and follow-up context. Normal questions go directly to the configured LLM; optional web browsing is only enabled when the student turns on the Browse web control.

Configure `AI_API_PROVIDER=openai`, `AI_API_KEY`, and `AI_MODEL=gpt-5.6-luna` in `.env`. The OpenAI API key stays server-side.


### AI Teddy provider fallback

AI Teddy uses the configured LLM directly for normal conversations. Web search is optional and is only included when the user enables Browse web.

Provider order is configurable with `AI_PROVIDER_ORDER`. With the default `openai,anthropic`, Teddy tries OpenAI first and, if it fails because of quota, authentication, permission, timeout, network, or provider availability, tries Anthropic when an Anthropic key is configured. The real provider failure is logged server-side; no fake response is generated.

If OpenAI reports `429` with zero remaining credits and no fallback key is configured, no code can manufacture an OpenAI response. Add usable provider quota or configure a second provider.


### Gemini on older Python
AI Teddy uses the Gemini REST API through `requests`; the `google-genai` Python package is not required. Configure `GEMINI_API_KEY` in `.env`.
