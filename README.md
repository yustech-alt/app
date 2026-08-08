# Script Doctor

Script Doctor is an AI agent that fact-checks screenplay scripts before production. It reads a scene, pulls out every factual claim, verifies each one against live web evidence, and returns a coverage report styled after a real script supervisor's notes.

Built for Google Cloud's **Agentic Cinema: The Blockbuster Hackathon**, Parallel track.

## What it does

1. **Extract** — Gemini reads the uploaded or pasted scene and identifies every checkable factual claim: historical events, dates, real places, real people, real companies, and technical or scientific claims.
2. **Verify** — Each claim is checked against live web evidence using the Parallel Search API.
3. **Judge** — Gemini compares each claim to the evidence and returns a verdict: **VERIFIED**, **FLAGGED** (with the correct fact), **INTENTIONAL** (a deliberate creative choice, genre-aware), or **UNCERTAIN**.
4. **Coverage report** — Results are shown as a summary bar plus individual coverage notes, styled like a script supervisor's stamped notes.

## Genre-aware judgment

The tool accounts for the script's genre before judging claims. A historically inaccurate detail is treated very differently in a Documentary versus a Sci-Fi/Fantasy script, where it may be deliberate worldbuilding rather than an error.

## Tech stack

- **Google Gemini** (`google-genai`) — claim extraction and fact judgment
- **Parallel Search API** (`parallel-web`) — live web verification
- **Flask** — web application
- **pypdf** — PDF script upload support

## Running locally

```bash
pip install -r requirements.txt

export GEMINI_API_KEY="your-key-here"
export PARALLEL_API_KEY="your-key-here"

python app.py
```

Visit `http://127.0.0.1:5000` for the landing page, or `http://127.0.0.1:5000/check` for the tool.

## Deployment

Deployed on Render using the included `Procfile` and `requirements.txt`. Set `GEMINI_API_KEY` and `PARALLEL_API_KEY` as environment variables in the Render dashboard.

## License

MIT, see [LICENSE](./LICENSE).
