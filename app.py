import os
import time
from flask import Flask, request, render_template_string
from google import genai
from parallel import Parallel
from pypdf import PdfReader
import io

app = Flask(__name__)

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
parallel_client = Parallel(api_key=os.environ["PARALLEL_API_KEY"])

MODEL = "gemini-3.1-flash-lite"


_last_call_time = [0]

def generate_with_retry(client, model, contents, max_retries=5):
    for attempt in range(max_retries):
        elapsed = time.time() - _last_call_time[0]
        min_gap = 13  # stay under 5 requests/minute
        if elapsed < min_gap:
            time.sleep(min_gap - elapsed)
        try:
            response = client.models.generate_content(model=model, contents=contents)
            _last_call_time[0] = time.time()
            return response
        except Exception as e:
            _last_call_time[0] = time.time()
            if attempt == max_retries - 1:
                raise
            wait_time = 15 * (attempt + 1)
            time.sleep(wait_time)


def extract_text_from_upload(file):
    filename = file.filename.lower()
    if filename.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(file.read()))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    else:
        return file.read().decode("utf-8", errors="ignore")


GENRE_GUIDANCE = {
    "Sci-Fi / Fantasy": "This is a Sci-Fi/Fantasy script. Impossible or ahistorical claims may be deliberate worldbuilding, not errors. Only mark something FLAGGED if it seems like an accidental factual mistake rather than a creative choice. If a false claim seems intentional to the story's world, mark it INTENTIONAL instead of FLAGGED.",
    "Comedy": "This is a Comedy script. Exaggeration or absurd claims may be jokes, not errors. Mark obvious jokes as INTENTIONAL. Only FLAG claims that look like accidental factual mistakes rather than comedic exaggeration.",
    "Historical / Biopic": "This is a Historical/Biopic script. Factual accuracy matters a great deal here. Flag any claim that contradicts the historical record.",
    "Documentary": "This is a Documentary script. Factual accuracy is critical. Flag any claim that contradicts the evidence.",
    "Drama": "This is a Drama script. Flag claims that contradict real-world facts unless they are clearly meant as a character's mistaken belief within the story.",
    "Thriller / Crime": "This is a Thriller/Crime script. Flag claims that contradict real-world facts, especially procedural, legal, or technical details.",
    "Other / Unsure": "Flag claims that contradict real-world facts, using ordinary judgment about what is likely a writing error versus a deliberate choice.",
}


def normalize_verdict(v):
    v = v.upper()
    if v in ("FALSE", "FLAGGED", "INCORRECT"):
        return "FLAGGED"
    if v in ("TRUE", "VERIFIED", "CORRECT"):
        return "VERIFIED"
    if v in ("INTENTIONAL", "DELIBERATE", "CREATIVE"):
        return "INTENTIONAL"
    return "UNCERTAIN"


def check_script(script_text, genre="Drama"):
    extract_prompt = f"""
Read this screenplay excerpt. Extract every factual claim that could be checked
against real-world facts: historical events, dates, real places, real people,
real companies, or technical/scientific claims.

List each claim as a short, standalone sentence, one per line, with no extra
commentary, no numbering, no bullets.

Screenplay excerpt:
{script_text}
"""
    extract_response = generate_with_retry(gemini_client, MODEL, extract_prompt)
    claims = [line.strip() for line in extract_response.text.strip().split("\n") if line.strip()]

    claim_evidence = []
    for claim in claims:
        search = parallel_client.search(
            objective=f"Verify this claim for accuracy: {claim}",
            search_queries=[claim],
        )
        evidence_text = ""
        source_title = None
        if search.results:
            source_title = search.results[0].title
            for result in search.results[:2]:
                if result.excerpts:
                    evidence_text += f"Source: {result.title}\n{result.excerpts[0][:300]}\n\n"
        claim_evidence.append({"claim": claim, "evidence": evidence_text, "source": source_title})

    guidance = GENRE_GUIDANCE.get(genre, GENRE_GUIDANCE["Other / Unsure"])

    batch_prompt = f"""Fact-check each claim below against its evidence.

{guidance}

Respond with one line per claim, in this exact format, nothing else:
CLAIM_N | VERDICT | NOTE

VERDICT must be one of: VERIFIED, FLAGGED, INTENTIONAL, UNCERTAIN

"""
    for i, ce in enumerate(claim_evidence):
        batch_prompt += f"CLAIM_{i}: {ce['claim']}\nEVIDENCE_{i}: {ce['evidence'] or 'No evidence found.'}\n\n"

    judge_response = generate_with_retry(gemini_client, MODEL, batch_prompt)
    lines = [l.strip() for l in judge_response.text.strip().split("\n") if "|" in l]

    results = []
    for i, ce in enumerate(claim_evidence):
        verdict, note = "UNCERTAIN", "Could not parse a verdict."
        for line in lines:
            if line.startswith(f"CLAIM_{i}"):
                parts = line.split("|")
                if len(parts) >= 3:
                    verdict = normalize_verdict(parts[1].strip())
                    note = parts[2].strip()
                break
        results.append({"claim": ce["claim"], "verdict": verdict, "note": note, "source": ce["source"]})

    return results


SAMPLE_SCENE = """INT. LIBRARY - DAY

STUDENT
Did you know the Great Wall of China is visible from space with the naked eye?

TEACHER
Also, Napoleon was extremely short for his time. The Eiffel Tower opened in 1889, right?
"""

PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Script Doctor — Coverage for your screenplay</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700&family=Zilla+Slab:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --ink: #14171C;
    --ink-2: #1B2029;
    --paper: #EDE7D9;
    --paper-dim: #E1D9C4;
    --paper-line: #C9BF9F;
    --flag: #B23A2E;
    --flag-bg: #F6E7E4;
    --verified: #3F6B52;
    --verified-bg: #E7EFE9;
    --uncertain: #C98A2C;
    --uncertain-bg: #F6EEE0;
    --rule: #4C5B72;
    --cream-text: #EDE7D9;
    --ink-text: #23282F;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--ink);
    color: var(--cream-text);
    font-family: 'Inter', sans-serif;
  }
  a { color: inherit; }

  nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 22px 48px;
    border-bottom: 1px solid rgba(237,231,217,0.12);
  }
  .brand {
    font-family: 'Zilla Slab', serif;
    font-weight: 700;
    font-size: 20px;
    letter-spacing: 0.02em;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .brand .slate {
    width: 22px; height: 22px;
    border: 2px solid var(--flag);
    border-radius: 3px;
    position: relative;
    transform: rotate(-4deg);
  }
  .brand .slate::before {
    content: "";
    position: absolute;
    top: 4px; left: -2px; right: -2px;
    height: 2px;
    background: var(--flag);
  }
  nav .cta {
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    font-size: 14px;
    padding: 10px 20px;
    border: 1px solid var(--cream-text);
    border-radius: 2px;
    text-decoration: none;
    transition: background 0.15s, color 0.15s;
  }
  nav .cta:hover { background: var(--cream-text); color: var(--ink); }

  .hero {
    max-width: 980px;
    margin: 0 auto;
    padding: 110px 32px 90px;
    text-align: center;
    position: relative;
  }
  .eyebrow {
    font-family: 'Courier Prime', monospace;
    font-size: 13px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--flag);
    margin-bottom: 22px;
  }
  h1.headline {
    font-family: 'Zilla Slab', serif;
    font-weight: 700;
    font-size: clamp(40px, 6vw, 72px);
    line-height: 1.04;
    margin: 0 0 26px;
    letter-spacing: -0.01em;
  }
  .headline .accent { color: var(--flag); }
  .sub {
    font-family: 'Inter', sans-serif;
    font-size: 19px;
    line-height: 1.6;
    color: rgba(237,231,217,0.72);
    max-width: 620px;
    margin: 0 auto 44px;
  }
  .hero-actions {
    display: flex;
    gap: 16px;
    justify-content: center;
    flex-wrap: wrap;
  }
  .btn-primary {
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    font-size: 16px;
    padding: 15px 30px;
    background: var(--flag);
    color: var(--cream-text);
    border: none;
    border-radius: 2px;
    text-decoration: none;
    display: inline-block;
    transition: transform 0.15s ease;
  }
  .btn-primary:hover { transform: translateY(-1px); }
  .btn-ghost {
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    font-size: 16px;
    padding: 15px 30px;
    background: transparent;
    color: var(--cream-text);
    border: 1px solid rgba(237,231,217,0.4);
    border-radius: 2px;
    text-decoration: none;
    display: inline-block;
  }

  .page-mock {
    max-width: 560px;
    margin: 70px auto 0;
    background: var(--paper);
    color: var(--ink-text);
    border-radius: 2px;
    padding: 40px 44px;
    text-align: left;
    font-family: 'Courier Prime', monospace;
    font-size: 14px;
    line-height: 1.85;
    position: relative;
    box-shadow: 0 30px 70px rgba(0,0,0,0.45);
    transform: rotate(-1.2deg);
  }
  .page-mock .slug { font-weight: 700; }
  .page-mock .margin-flag {
    position: absolute;
    right: -18px;
    background: var(--flag);
    color: var(--cream-text);
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.06em;
    padding: 3px 10px;
    border-radius: 2px;
    transform: rotate(8deg);
  }
  .page-mock .line-flagged { text-decoration: underline wavy var(--flag); text-decoration-thickness: 1.5px; }

  .how {
    max-width: 980px;
    margin: 0 auto;
    padding: 90px 32px 110px;
    border-top: 1px solid rgba(237,231,217,0.12);
  }
  .how h2 {
    font-family: 'Zilla Slab', serif;
    font-size: 30px;
    margin: 0 0 46px;
    text-align: center;
  }
  .steps {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 32px;
  }
  .step {
    border-top: 2px solid var(--flag);
    padding-top: 18px;
  }
  .step .num {
    font-family: 'Courier Prime', monospace;
    font-size: 13px;
    color: rgba(237,231,217,0.5);
    margin-bottom: 10px;
    display: block;
  }
  .step h3 {
    font-family: 'Inter', sans-serif;
    font-size: 18px;
    margin: 0 0 10px;
  }
  .step p {
    font-size: 14.5px;
    line-height: 1.6;
    color: rgba(237,231,217,0.65);
    margin: 0;
  }
  footer {
    text-align: center;
    padding: 36px;
    font-size: 13px;
    color: rgba(237,231,217,0.4);
    font-family: 'Courier Prime', monospace;
  }

  .app-shell { background: var(--paper); color: var(--ink-text); min-height: 100vh; }
  .app-nav {
    display: flex; justify-content: space-between; align-items: center;
    padding: 20px 48px; border-bottom: 1px solid var(--paper-line);
  }
  .app-nav .brand { color: var(--ink-text); }
  .app-nav .brand .slate { border-color: var(--flag); }
  .app-nav .back { font-family:'Inter',sans-serif; font-size:14px; font-weight:600; text-decoration:none; color: var(--ink-text); opacity:0.7; }

  .workspace {
    max-width: 980px;
    margin: 0 auto;
    padding: 48px 32px 100px;
  }
  .workspace h1 {
    font-family: 'Zilla Slab', serif;
    font-size: 30px;
    margin: 0 0 6px;
  }
  .workspace .lede {
    color: #55606e;
    margin: 0 0 34px;
    font-size: 15px;
  }
  textarea {
    width: 100%;
    min-height: 220px;
    font-family: 'Courier Prime', monospace;
    font-size: 14px;
    line-height: 1.7;
    padding: 22px 26px;
    background: #fff;
    border: 1px solid var(--paper-line);
    border-radius: 2px;
    resize: vertical;
    color: var(--ink-text);
  }
  textarea:focus { outline: 2px solid var(--rule); outline-offset: 2px; }

  .genre-field {
    margin-top: 18px;
    display: block;
    font-family: 'Inter', sans-serif;
    font-size: 13px;
    font-weight: 600;
    color: #55606e;
  }
  .genre-field select {
    display: block;
    margin-top: 6px;
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    padding: 10px 12px;
    border: 1px solid var(--paper-line);
    border-radius: 2px;
    background: #fff;
    width: 260px;
  }

  .toolbar {
    display: flex; justify-content: space-between; align-items: center;
    margin-top: 14px; flex-wrap: wrap; gap: 12px;
  }
  .sample-link {
    font-family: 'Inter', sans-serif;
    font-size: 13px;
    font-weight: 600;
    color: var(--rule);
    background: none;
    border: none;
    cursor: pointer;
    text-decoration: underline;
    padding: 0;
  }
  .submit-btn {
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    font-size: 15px;
    padding: 13px 28px;
    background: var(--ink);
    color: var(--cream-text);
    border: none;
    border-radius: 2px;
    cursor: pointer;
  }
  .submit-btn:hover { background: #000; }

  .coverage-bar {
    margin-top: 48px;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    border: 1px solid var(--paper-line);
    border-radius: 2px;
    overflow: hidden;
  }
  .coverage-cell {
    padding: 22px 20px;
    border-right: 1px solid var(--paper-line);
    background: #fff;
  }
  .coverage-cell:last-child { border-right: none; }
  .coverage-cell .n {
    font-family: 'Zilla Slab', serif;
    font-size: 32px;
    font-weight: 700;
    display: block;
  }
  .coverage-cell .l {
    font-family: 'Inter', sans-serif;
    font-size: 12.5px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #78807a;
  }
  .coverage-cell.total .n { color: var(--ink-text); }
  .coverage-cell.flagged .n { color: var(--flag); }
  .coverage-cell.verified .n { color: var(--verified); }
  .coverage-cell.uncertain .n { color: var(--uncertain); }

  .results { margin-top: 30px; }
  .results h2 {
    font-family: 'Zilla Slab', serif;
    font-size: 20px;
    margin: 0 0 18px;
  }
  .note-card {
    background: #fff;
    border: 1px solid var(--paper-line);
    border-left: 4px solid var(--paper-line);
    border-radius: 2px;
    padding: 20px 24px;
    margin-bottom: 14px;
    position: relative;
    display: flex;
    gap: 20px;
    align-items: flex-start;
  }
  .note-card.FLAGGED { border-left-color: var(--flag); }
  .note-card.VERIFIED { border-left-color: var(--verified); }
  .note-card.UNCERTAIN { border-left-color: var(--uncertain); }
  .note-card.INTENTIONAL { border-left-color: var(--rule); }

  .stamp {
    font-family: 'Zilla Slab', serif;
    font-weight: 700;
    font-size: 12.5px;
    letter-spacing: 0.08em;
    padding: 5px 10px;
    border: 2px solid currentColor;
    border-radius: 3px;
    transform: rotate(-6deg);
    white-space: nowrap;
    flex-shrink: 0;
    margin-top: 2px;
  }
  .FLAGGED .stamp { color: var(--flag); }
  .VERIFIED .stamp { color: var(--verified); }
  .UNCERTAIN .stamp { color: var(--uncertain); }
  .INTENTIONAL .stamp { color: var(--rule); }

  .note-body .claim {
    font-family: 'Courier Prime', monospace;
    font-size: 14.5px;
    margin: 0 0 6px;
  }
  .note-body .note {
    font-size: 14px;
    color: #4a5158;
    margin: 0 0 6px;
    line-height: 1.55;
  }
  .note-body .src {
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    color: #8b9198;
  }

  @media (max-width: 720px) {
    .steps { grid-template-columns: 1fr; }
    .coverage-bar { grid-template-columns: repeat(2, 1fr); }
    nav, .app-nav { padding: 18px 22px; }
    .hero { padding: 70px 22px 60px; }
  }
</style>
</head>
<body>

{% if page == 'landing' %}
  <nav>
    <div class="brand"><span class="slate"></span> Script Doctor</div>
    <a class="cta" href="/check">Open the tool</a>
  </nav>

  <section class="hero">
    <div class="eyebrow">Coverage, before the table read</div>
    <h1 class="headline">Every fact in your script,<br>checked before your <span class="accent">audience</span> does.</h1>
    <p class="sub">Paste a scene. Script Doctor pulls out every checkable claim, verifies it against live sources, and hands back coverage notes, the way a script supervisor would, in seconds instead of days.</p>
    <div class="hero-actions">
      <a class="btn-primary" href="/check">Check a scene</a>
      <a class="btn-ghost" href="#how">How it works</a>
    </div>

    <div class="page-mock">
      <div class="slug">INT. NEWSROOM &mdash; NIGHT</div><br>
      REPORTER<br>
      Turn on the TV — they just landed the<br>
      <span class="line-flagged">first rover on Mars in 1990.</span>
      <div class="margin-flag" style="top: 128px;">FLAGGED</div>
    </div>
  </section>

  <section class="how" id="how">
    <h2>Three passes, one page at a time</h2>
    <div class="steps">
      <div class="step">
        <span class="num">01</span>
        <h3>Extract</h3>
        <p>Gemini reads your scene and pulls out every claim that could be checked, dates, places, real people, technical details.</p>
      </div>
      <div class="step">
        <span class="num">02</span>
        <h3>Verify</h3>
        <p>Each claim is checked against live web evidence through Parallel Search, not memory, not guesswork.</p>
      </div>
      <div class="step">
        <span class="num">03</span>
        <h3>Coverage</h3>
        <p>You get a verdict per claim: cleared, flagged with the correct fact, or uncertain, laid out like a real coverage report.</p>
      </div>
    </div>
  </section>

  <footer>Built for Agentic Cinema — Gemini + Parallel Search</footer>

{% else %}
<div class="app-shell">
  <div class="app-nav">
    <div class="brand"><span class="slate"></span> Script Doctor</div>
    <a class="back" href="/">&larr; Back</a>
  </div>

  <div class="workspace">
    <h1>Run coverage on a scene</h1>
    <p class="lede">Paste your scene below. Every factual claim gets checked against real sources.</p>

    <form method="POST" id="scriptForm" enctype="multipart/form-data">
      <textarea name="script_text" id="scriptText" placeholder="INT. LOCATION - DAY&#10;&#10;CHARACTER&#10;Dialogue goes here...">{{ script_text or '' }}</textarea>

      <label class="genre-field">
        Genre
        <select name="genre">
          <option value="Drama" {{ 'selected' if genre == 'Drama' }}>Drama</option>
          <option value="Historical / Biopic" {{ 'selected' if genre == 'Historical / Biopic' }}>Historical / Biopic</option>
          <option value="Documentary" {{ 'selected' if genre == 'Documentary' }}>Documentary</option>
          <option value="Comedy" {{ 'selected' if genre == 'Comedy' }}>Comedy</option>
          <option value="Thriller / Crime" {{ 'selected' if genre == 'Thriller / Crime' }}>Thriller / Crime</option>
          <option value="Sci-Fi / Fantasy" {{ 'selected' if genre == 'Sci-Fi / Fantasy' }}>Sci-Fi / Fantasy</option>
          <option value="Other / Unsure" {{ 'selected' if genre == 'Other / Unsure' }}>Other / Unsure</option>
        </select>
      </label>

      <div class="toolbar">
        <div style="display:flex; align-items:center; gap:16px;">
          <button type="button" class="sample-link" onclick="loadSample()">Load a sample scene</button>
          <label class="sample-link" style="cursor:pointer;">
            Upload a file (.txt or .pdf)
            <input type="file" name="script_file" id="scriptFile" accept=".txt,.pdf" style="display:none;" onchange="document.getElementById('scriptForm').querySelector('.submit-btn').textContent = 'Run coverage on ' + this.files[0].name;">
          </label>
        </div>
        <button type="submit" class="submit-btn">Run coverage</button>
      </div>
    </form>

    {% if results %}
      {% set flagged = results|selectattr('verdict','equalto','FLAGGED')|list|length %}
      {% set verified = results|selectattr('verdict','equalto','VERIFIED')|list|length %}
      {% set uncertain = results|selectattr('verdict','equalto','UNCERTAIN')|list|length %}
      <div class="coverage-bar">
        <div class="coverage-cell total"><span class="n">{{ results|length }}</span><span class="l">Claims checked</span></div>
        <div class="coverage-cell flagged"><span class="n">{{ flagged }}</span><span class="l">Flagged</span></div>
        <div class="coverage-cell verified"><span class="n">{{ verified }}</span><span class="l">Verified</span></div>
        <div class="coverage-cell uncertain"><span class="n">{{ uncertain }}</span><span class="l">Uncertain</span></div>
      </div>

      <div class="results">
        <h2>Coverage notes</h2>
        {% for r in results %}
          <div class="note-card {{ r.verdict }}">
            <div class="stamp">{{ 'CLEARED' if r.verdict == 'VERIFIED' else r.verdict }}</div>
            <div class="note-body">
              <p class="claim">&ldquo;{{ r.claim }}&rdquo;</p>
              <p class="note">{{ r.note }}</p>
              {% if r.source %}<p class="src">Source: {{ r.source }}</p>{% endif %}
            </div>
          </div>
        {% endfor %}
      </div>
    {% endif %}
  </div>
</div>

<script>
function loadSample() {
  document.getElementById('scriptText').value = {{ sample|tojson }};
}
</script>
{% endif %}

</body>
</html>
"""

@app.route("/")
def landing():
    return render_template_string(PAGE, page="landing")

@app.route("/check", methods=["GET", "POST"])
def check():
    results = None
    script_text = ""
    genre = "Drama"
    if request.method == "POST":
        uploaded_file = request.files.get("script_file")
        if uploaded_file and uploaded_file.filename:
            script_text = extract_text_from_upload(uploaded_file)
        else:
            script_text = request.form.get("script_text", "")
        genre = request.form.get("genre", "Drama")
        results = check_script(script_text, genre)
    return render_template_string(PAGE, page="app", results=results, script_text=script_text, sample=SAMPLE_SCENE, genre=genre)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
