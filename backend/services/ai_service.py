import os
import openai


class AIService:
    def __init__(self):
        openai.api_key = os.environ.get("OPENAI_API_KEY", "")

    def analyze_logs(self, logs: str):
        if not logs:
            return {"summary": "No logs provided", "issues": []}

        prompt = (
            "Analyze the following CI/CD logs. Identify error patterns, warnings, root causes, and suggest fixes. "
            "Return a JSON object with issue categories, recommendations, and severity.\n\n" + logs
        )
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.3,
            )
            text = response.choices[0].message.content
            return {"summary": "AI analysis completed", "debug_advice": text}
        except Exception as exc:
            return {"summary": "AI analysis unavailable", "error": str(exc)}

    def explain_error(self, error_text: str):
        prompt = f"Explain this pipeline error and propose a fix: {error_text}"
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.2,
            )
            return response.choices[0].message.content
        except Exception as exc:
            return f"Could not analyze error: {exc}"
