"""Function tools shared by the interview agents."""

import json
import re
from datetime import datetime
from pathlib import Path

from google.adk.tools import ToolContext

QUESTION_BANK = json.loads((Path(__file__).parent / "questions.json").read_text())
SESSIONS_DIR = Path(__file__).resolve().parents[2] / "sessions"

SKILL_KEYWORDS = [
    "python", "java", "javascript", "typescript", "go", "node", "react", "sql", "postgresql",
    "postgres", "mysql", "redis", "kafka", "docker", "kubernetes", "aws", "gcp",
    "azure", "rest", "graphql", "grpc", "webhooks", "oauth", "twilio", "plivo",
    "sip", "webrtc", "linux", "git", "ci/cd", "terraform", "django", "flask",
    "fastapi", "spring", "microservices", "llm", "machine learning", "api",
]
SECTION_HEADINGS = ["summary", "experience", "work experience", "education",
                    "skills", "projects", "certifications", "achievements"]


def parse_resume(resume_text: str) -> dict:
    """Extracts sections, known skills and contact details from a pasted resume.

    Args:
        resume_text: The full resume as plain text.
    """
    sections, current = {}, "header"
    for line in resume_text.splitlines():
        heading = line.strip().strip(":").lower()
        if heading in SECTION_HEADINGS:
            current = heading
            continue
        if line.strip():
            sections.setdefault(current, []).append(line.strip())

    lower = resume_text.lower()
    skills = [s for s in SKILL_KEYWORDS
              if re.search(rf"(?<![\w/]){re.escape(s)}(?![\w/])", lower)]
    years = [int(y) for y in re.findall(r"(\d{1,2})\+?\s*years?", lower)]
    return {
        "sections": {k: "\n".join(v) for k, v in sections.items()},
        "skills": skills,
        "years_of_experience": max(years) if years else None,
        "emails": re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", resume_text),
    }


def get_questions(topic: str, count: int = 3) -> dict:
    """Returns questions from the question bank for a topic.

    Args:
        topic: One of the bank topics, e.g. "api_debugging", "webhooks",
            "system_design", "behavioral", "customer_roleplay".
        count: How many questions to return.
    """
    if topic not in QUESTION_BANK:
        return {"error": f"Unknown topic '{topic}'.", "topics": sorted(QUESTION_BANK)}
    return {"topic": topic, "questions": QUESTION_BANK[topic][:count]}


def record_turn(question: str, answer: str, kind: str, tool_context: ToolContext) -> dict:
    """Appends one question/answer pair to the interview transcript.

    Args:
        question: The question exactly as asked (or the customer's message).
        answer: The candidate's answer, verbatim or a faithful summary.
        kind: "technical", "behavioral", "follow_up" or "customer_roleplay".
    """
    transcript = tool_context.state.get("transcript", [])
    transcript = transcript + [{"question": question, "answer": answer, "kind": kind}]
    tool_context.state["transcript"] = transcript
    return {"status": "recorded", "turns": len(transcript)}


def save_session(tool_context: ToolContext) -> dict:
    """Saves the plan, transcript, scores and coach report to the sessions folder."""
    folder = SESSIONS_DIR / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder.mkdir(parents=True, exist_ok=True)
    state = tool_context.state
    for key in ("plan", "transcript", "scores"):
        if key in state:
            (folder / f"{key}.json").write_text(json.dumps(state[key], indent=2))
    if "report" in state:
        (folder / "report.md").write_text(state["report"])
    return {"status": "saved", "folder": str(folder)}
