"""
AI service for FluxForge.

Primary provider: Google Gemini (via the official google-genai SDK).
Falls back to OpenAI-compatible endpoints (OpenAI / OpenRouter) when
GEMINI_API_KEY is not set.
"""
import logging
import os

from backend.config import Config

logger = logging.getLogger(__name__)

# Module-level cache for SDK clients — these are expensive to construct
# (involves importing heavy SDKs and creating HTTP connection pools), so
# we reuse a single instance across all AIService() constructions.
_GEMINI_CLIENT = None
_OPENAI_CLIENT = None


def _get_gemini_client():
    """Lazy-init and cache the Gemini client (module-level singleton)."""
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is not None:
        return _GEMINI_CLIENT
    api_key = Config.GEMINI_API_KEY
    if not api_key:
        return None
    try:
        from google import genai
        _GEMINI_CLIENT = genai.Client(api_key=api_key)
        return _GEMINI_CLIENT
    except Exception as exc:
        logger.warning("Failed to initialise Gemini client: %s", exc)
        return None


def _get_openai_client():
    """Lazy-init and cache the OpenAI-compatible client (module-level singleton)."""
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is not None:
        return _OPENAI_CLIENT
    api_key = Config.OPENAI_API_KEY
    if not api_key:
        return None
    try:
        from openai import OpenAI
        base_url = Config.OPENAI_BASE_URL or None
        # Auto-detect OpenRouter
        if api_key.startswith("sk-or-") and not base_url:
            base_url = "https://openrouter.ai/api/v1"
        _OPENAI_CLIENT = OpenAI(api_key=api_key, base_url=base_url)
        return _OPENAI_CLIENT
    except Exception as exc:
        logger.warning("Failed to initialise OpenAI client: %s", exc)
        return None


def _try_gemini(prompt: str, max_tokens: int = 500, temperature: float = 0.3) -> str | None:
    """Call Gemini via the official SDK. Returns text or None on failure."""
    client = _get_gemini_client()
    if client is None:
        return None
    try:
        # gemini-flash-lite-latest is the fastest available model (~0.8s typical latency)
        model = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        return response.text
    except Exception as exc:
        logger.warning("Gemini call failed: %s", exc)
        return None


def _try_openai(prompt: str, max_tokens: int = 500, temperature: float = 0.3) -> str | None:
    """Call OpenAI / OpenRouter via the OpenAI SDK. Returns text or None on failure."""
    client = _get_openai_client()
    if client is None:
        return None
    try:
        model = Config.OPENAI_MODEL
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.warning("OpenAI call failed: %s", exc)
        return None


def _call_llm(prompt: str, max_tokens: int = 500, temperature: float = 0.3) -> str:
    """Call Gemini first (fast), then fall back to OpenAI."""
    text = _try_gemini(prompt, max_tokens, temperature)
    if text:
        return text
    text = _try_openai(prompt, max_tokens, temperature)
    if text:
        return text
    return "AI analysis unavailable: no working API key (set GEMINI_API_KEY or OPENAI_API_KEY in .env)"


class AIService:
    """AI service that uses Gemini by default with OpenAI fallback."""

    def __init__(self):
        self.provider = "gemini" if Config.GEMINI_API_KEY else ("openai" if Config.OPENAI_API_KEY else "none")
        if self.provider == "none":
            logger.warning("No AI provider configured. Set GEMINI_API_KEY or OPENAI_API_KEY in .env")

    def analyze_logs(self, logs: str):
        if not logs:
            return {"summary": "No logs provided", "issues": []}

        if self.provider == "none":
            return {"summary": "AI analysis unavailable", "error": "AI client not initialized. Check credentials."}

        prompt = (
            "Analyze the following CI/CD logs. Identify error patterns, warnings, root causes, and suggest fixes. "
            "Return a JSON object with issue categories, recommendations, and severity.\n\n" + logs
        )
        try:
            text = _call_llm(prompt, max_tokens=500, temperature=0.3)
            return {"summary": "AI analysis completed", "debug_advice": text}
        except Exception as exc:
            return {"summary": "AI analysis unavailable", "error": str(exc)}

    def explain_error(self, error_text: str):
        if self.provider == "none":
            return "Could not analyze error: AI client not initialized. Check credentials."

        prompt = f"Explain this pipeline error and propose a fix: {error_text}"
        try:
            return _call_llm(prompt, max_tokens=300, temperature=0.2)
        except Exception as exc:
            return f"Could not analyze error: {exc}"

    def generate_code_fix(self, broken_code: str, error_log: str) -> str:
        """Generate a code fix for the given broken file + error log."""
        if self.provider == "none":
            return ""
        prompt = (
            "You are an expert software engineer. Given a source file and an error log, "
            "return ONLY the corrected source file content (no markdown fences, no explanations).\n\n"
            f"BROKEN CODE:\n{broken_code}\n\n"
            f"ERROR LOG:\n{error_log}\n\n"
            "FIXED CODE:\n"
        )
        try:
            return _call_llm(prompt, max_tokens=2000, temperature=0.1)
        except Exception as exc:
            logger.error("Code-fix generation failed: %s", exc)
            return ""
