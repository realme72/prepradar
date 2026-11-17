"""Settings loaded from environment / .env."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# The AI providers that read pages, tried in order. A used-up daily quota, a long overload
# or a request too big for one moves the call (and, for a quota, the rest of the run) to
# the next. A provider is used only when its key is set; LLM_PROVIDERS picks and orders
# them by name. Gemini and Groq speak OpenAI's chat completions API, so one client does.
@dataclass(frozen=True)
class Provider:
    name: str
    key_env: str
    base_url: str | None  # None: OpenAI's own
    model: str            # for extraction and the guide
    judge_model: str      # for classify, duplicate and tag checks (see JUDGE_MODEL)
    rpm: float = 0        # requests per minute, across threads; 0 = no pacing
    max_chars: int = 0    # longest request (instructions + input); 0 = no limit
    max_output: int | None = None
    reasoning: str | None = None  # effort used when a call doesn't ask for one


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Gemini's free tier: Flash ~20 requests a day, Flash-Lite ~500, both ~10 a minute. Raise
# LLM_RPM on a paid key.
_GEMINI_RPM = float(os.getenv("LLM_RPM", "8"))
# Groq's free tier: 8,000 tokens a minute and 200,000 a day per model, and a request's
# max_output counts against both. So requests are capped (~16k chars + 2.5k tokens out),
# one a minute, and each model is its own provider with its own quota.
_ALL_PROVIDERS = [
    Provider("openai", "OPENAI_API_KEY", None, os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
             os.getenv("JUDGE_MODEL", "gpt-5.4-mini")),
    Provider("gemini", "GEMINI_API_KEY", GEMINI_BASE_URL, "gemini-3.5-flash", "gemini-3.5-flash", rpm=_GEMINI_RPM),
    Provider("gemini-lite", "GEMINI_API_KEY", GEMINI_BASE_URL, "gemini-3.5-flash-lite", "gemini-3.5-flash-lite",
             rpm=_GEMINI_RPM),
    Provider("groq", "GROQ_API_KEY", GROQ_BASE_URL, "openai/gpt-oss-120b", "openai/gpt-oss-120b", rpm=1,
             max_chars=16_000, max_output=2_500, reasoning="low"),
    Provider("groq-small", "GROQ_API_KEY", GROQ_BASE_URL, "openai/gpt-oss-20b", "openai/gpt-oss-20b", rpm=1,
             max_chars=16_000, max_output=2_500, reasoning="low"),
]
_by_name = {p.name: p for p in _ALL_PROVIDERS}
PROVIDERS = [_by_name[n.strip()] for n in os.getenv("LLM_PROVIDERS", ",".join(_by_name)).split(",")
             if n.strip() in _by_name and os.getenv(_by_name[n.strip()].key_env)]
_FIRST = PROVIDERS[0] if PROVIDERS else _ALL_PROVIDERS[0]
LLM_PROVIDER = _FIRST.name
_GEMINI = LLM_PROVIDER.startswith("gemini")
# Callers name a model by role: OPENAI_MODEL for extraction, JUDGE_MODEL for judgement
# calls. A fallback provider swaps in its own model for the same role.
OPENAI_MODEL = _FIRST.model
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/prepradar")
MAX_PAGE_CHARS = 15_000  # one question-extraction call reads this much of a page
MAX_CHUNKS = 4           # longer pages are read in up to this many chunks (60k chars)
EXPERIENCE_CHARS = 60_000  # the experience call reads a page in one go, so a story isn't split
# Pages read at once (fetch + AI calls). Saving stays one page at a time, so duplicate
# and tag checks see everything saved before them. One at a time took ~70s a page.
INGEST_WORKERS = int(os.getenv("INGEST_WORKERS", "3" if _GEMINI else "6"))

# cosine similarity at or above which two questions are the same question
# (picked from real pairs: true rewrites scored 0.93+, "MongoDB vs MySQL schema" 0.87)
DEDUPE_THRESHOLD = float(os.getenv("DEDUPE_THRESHOLD", "0.88"))
# Between this and DEDUPE_THRESHOLD the score can't decide: "debounce function" vs
# "what is debounce" (0.856) is a duplicate, "debug a failing API" vs "debug a slow
# API" (0.863) is not. Those pairs go to an LLM judge. No true duplicates seen below.
DEDUPE_JUDGE = float(os.getenv("DEDUPE_JUDGE", "0.80"))
# Model for judgement calls that run rarely (duplicate judge, recategorise), so they
# can afford more care than extraction. For the duplicate judge, gpt-4o-mini flipped between merging "kth largest" with
# "2nd largest" and missing "debounce function" = "what is debounce, implement it".
JUDGE_MODEL = _FIRST.judge_model
# With no reasoning the classifier flipped on borderline pages (an AI-written summary
# read as candidate reviews 2 runs in 5); "low" was stable, "medium" no better.
JUDGE_REASONING = {"effort": os.getenv("JUDGE_REASONING", "low")}
# The client's own retries for brief failures (it waits seconds); rate limits and long
# overloads are handled in extractor.parse.
LLM_RETRIES = int(os.getenv("LLM_RETRIES", "2"))
# Short tag names embed poorly ("Java" vs "JavaScript" 0.83, "Prod Debugging" vs
# "Production Troubleshooting" 0.73), so similarity alone can't decide tag merges:
# >= AUTO: merge; between CANDIDATE and AUTO: ask the LLM; below CANDIDATE: new tag.
TOPIC_AUTO_MERGE = float(os.getenv("TOPIC_AUTO_MERGE", "0.92"))
TOPIC_CANDIDATE = float(os.getenv("TOPIC_CANDIDATE", "0.70"))
