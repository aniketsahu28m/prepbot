"""Multi-agent interview simulator: root coordinator + 4 specialist agents."""

import os
from typing import Literal

from google.adk import Agent
from google.adk.models import Gemini
from google.genai import types
from pydantic import BaseModel, Field

from .tools import get_questions, parse_resume, record_turn, save_session

TEXT_MODEL = os.getenv("TEXT_MODEL", "gemini-flash-latest")
# Gemini often returns 503 "high demand" for a few seconds; retry instead of failing.
RETRY = types.HttpRetryOptions(attempts=6, initial_delay=2, max_delay=30)


# --- JSON output schemas -----------------------------------------------------

class PlannedQuestion(BaseModel):
    id: int
    kind: Literal["technical", "behavioral", "customer_roleplay"]
    topic: str
    question: str
    what_good_looks_like: str = Field(description="Key points a strong answer covers.")


class InterviewPlan(BaseModel):
    role: str
    seniority: str
    focus_areas: list[str]
    candidate_strengths: list[str]
    candidate_gaps: list[str] = Field(description="JD requirements the resume doesn't show.")
    questions: list[PlannedQuestion] = Field(description="6-8 questions, including exactly one customer_roleplay.")
    customer_scenario: str = Field(description="Persona + broken API integration for the roleplay.")


class AnswerScore(BaseModel):
    question: str
    technical_accuracy: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    structure: int = Field(ge=1, le=5)
    works_for_non_technical_listener: bool
    non_technical_notes: str = Field(description="Jargon used, missing analogies, what a layperson would miss.")
    feedback: str


class Evaluation(BaseModel):
    scores: list[AnswerScore]
    overall_score: float = Field(ge=1, le=5)
    summary: str


# --- Agents ------------------------------------------------------------------

def build_interviewer(model, standalone: bool = False) -> Agent:
    """The interviewer. standalone=True runs it as its own root (the web app's voice
    mode): no task hand-off, the candidate ends the interview with a button."""
    ending = (
        "tell the candidate they can press 'End & get my report'."
        if standalone else "thank them and call finish_task with a one-line summary."
    )
    if isinstance(model, str):
        model = Gemini(model=model, retry_options=RETRY)
    return Agent(
        name="interviewer",
        model=model,
        mode=None if standalone else "task",
        description="Runs the mock interview with the candidate, including a customer roleplay.",
        instruction=(
            "You are a friendly but rigorous interviewer. Interview plan:\n{plan}\n\n"
            "Rules:\n"
            "- Ask ONE question at a time, in plan order. Keep your turns short (this may be spoken aloud).\n"
            "- After each answer, call record_turn with the question and the candidate's answer.\n"
            "- Adaptive follow-ups: if an answer is vague, wrong or skips a key point from "
            "what_good_looks_like, ask at most 2 follow-ups (record them with kind='follow_up'). "
            "If it is strong, move on. Use get_questions for extra material if needed.\n"
            "- Never give feedback or reveal scores during the interview.\n"
            "- For the customer_roleplay question: say 'Let's switch to a roleplay: I'm a customer.' "
            "Then fully play the customer from customer_scenario: non-technical, a bit stressed, "
            "confused by jargon. If the candidate uses jargon, ask what it means. Stay in "
            "character for 3-5 exchanges until they solve it or you've seen enough, then say "
            "'Ending roleplay.' Record each exchange with kind='customer_roleplay'.\n"
            "- When all questions are done, or the candidate asks to stop, " + ending
        ),
        tools=[record_turn, get_questions],
    )


def build_root(speaking_model: str = TEXT_MODEL, worker_model: str = TEXT_MODEL) -> Agent:
    """Builds a fresh agent tree. Voice mode passes a Live model as speaking_model;
    the silent JSON/report workers always use a text model."""
    speaking_model = Gemini(model=speaking_model, retry_options=RETRY)
    worker_model = Gemini(model=worker_model, retry_options=RETRY)
    jd_analyst = Agent(
        name="jd_analyst",
        model=worker_model,
        mode="single_turn",
        description="Turns a job description plus resume into a structured JSON interview plan.",
        instruction=(
            "You are a hiring manager preparing an interview. From the job description and "
            "resume (plus parsed resume data) in the request, build an interview plan. "
            "Target the JD's must-haves, probe the candidate's gaps, and use their real "
            "projects for behavioral questions. Include exactly one customer_roleplay question: "
            "a non-technical customer whose API integration is broken (e.g. expired key -> 401, "
            "webhook URL changed, rate limits). Describe that persona in customer_scenario."
        ),
        output_schema=InterviewPlan,
        output_key="plan",
    )

    interviewer = build_interviewer(speaking_model)

    evaluator = Agent(
        name="evaluator",
        model=worker_model,
        mode="single_turn",
        description="Scores every answer in the saved transcript. Call after the interview ends.",
        instruction=(
            "You are a strict interview evaluator. Interview plan:\n{plan?}\n\n"
            "Transcript:\n{transcript?}\n\n"
            "Score EVERY answer 1-5 on technical_accuracy, clarity and structure, using the "
            "plan's what_good_looks_like as the rubric. Decide whether the explanation would "
            "work for a non-technical listener (jargon explained? analogies? clear next step?) "
            "and say why. Be specific; quote the candidate where helpful. If the transcript "
            "is empty, return an empty scores list and say so in summary."
        ),
        output_schema=Evaluation,
        output_key="scores",
    )

    coach = Agent(
        name="coach",
        model=worker_model,
        mode="single_turn",
        description="Writes the final coaching report. Call after the evaluator.",
        instruction=(
            "You are an interview coach. Plan:\n{plan?}\n\nTranscript:\n{transcript?}\n\n"
            "Scores:\n{scores?}\n\n"
            "Write a Markdown report with these sections:\n"
            "## Overall\n2-3 sentences and the overall score.\n"
            "## Weak spots\nThe 3 most important, each tied to a specific answer.\n"
            "## Better sample answers\nFor the 3 weakest answers: the question, a short "
            "critique, and a model answer in the candidate's voice using their real experience.\n"
            "## Explaining to non-technical people\nWhat to change, with one rewritten explanation.\n"
            "## 7-day practice plan\nOne concrete, small task per day.\n"
            "Be direct and encouraging. No filler."
        ),
        output_key="report",
    )

    return Agent(
        name="interview_coach",
        model=speaking_model,
        description="Coordinates a full mock interview: plan, interview, evaluation, coaching.",
        instruction=(
            "You coordinate a mock job interview. Steps, in order:\n"
            "1. Greet the user briefly. Ask them to paste the job description and their resume "
            "(both at once is fine). Wait until you have both.\n"
            "2. Call parse_resume with the resume text, then call jd_analyst with a request "
            "containing the full JD, the full resume and the parsed resume data.\n"
            "3. Summarise the plan in 3-4 short lines (role, focus areas, number of questions, "
            "that there's a customer roleplay) and ask if they're ready.\n"
            "4. When ready, call interviewer to run the interview.\n"
            "5. When the interviewer finishes, tell the user you're scoring. Call evaluator, "
            "then coach, then save_session.\n"
            "6. Show the coach's report in full, then say where the files were saved.\n"
            "Keep your own messages short. If the user wants to redo the interview, go back to step 4."
        ),
        tools=[parse_resume, save_session],
        sub_agents=[jd_analyst, interviewer, evaluator, coach],
    )


root_agent = build_root()
