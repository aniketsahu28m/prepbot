"""Offline tests: no API key or network needed."""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from interview_coach import tools
from interview_coach.agent import AnswerScore, InterviewPlan, build_root

RESUME = """Asha Rao
asha.rao@example.com
Summary
Backend developer with 3+ years experience.
Skills
Python, Flask, REST, PostgreSQL, Docker, webhooks
Experience
ShopCo - built order webhooks in Python.
Education
B.Tech CSE
"""


def test_parse_resume_finds_sections_skills_and_contact():
    out = tools.parse_resume(RESUME)
    assert {"skills", "experience", "education", "summary"} <= set(out["sections"])
    assert {"python", "flask", "rest", "postgresql", "docker", "webhooks"} <= set(out["skills"])
    assert "java" not in out["skills"]  # no false match inside "javascript"-like words
    assert out["years_of_experience"] == 3
    assert out["emails"] == ["asha.rao@example.com"]


def test_parse_resume_handles_empty_text():
    assert tools.parse_resume("") == {
        "sections": {}, "skills": [], "years_of_experience": None, "emails": []}


def test_get_questions_known_and_unknown_topic():
    out = tools.get_questions("customer_roleplay", count=2)
    assert len(out["questions"]) == 2
    bad = tools.get_questions("astrology")
    assert "error" in bad and "webhooks" in bad["topics"]


def test_record_turn_appends_to_state():
    ctx = SimpleNamespace(state={})
    tools.record_turn("Q1", "A1", "technical", ctx)
    out = tools.record_turn("Q2", "A2", "follow_up", ctx)
    assert out["turns"] == 2
    assert ctx.state["transcript"][1] == {"question": "Q2", "answer": "A2", "kind": "follow_up"}


def test_save_session_writes_files(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "SESSIONS_DIR", tmp_path)
    ctx = SimpleNamespace(state={"plan": {"role": "SE"}, "transcript": [{"q": 1}], "report": "# Hi"})
    folder = tools.save_session(ctx)["folder"]
    saved = {p.name for p in tmp_path.glob("*/*")}
    assert saved == {"plan.json", "transcript.json", "report.md"}
    assert json.loads((tmp_path / folder / "plan.json").read_text()) == {"role": "SE"}


def test_score_schema_rejects_out_of_range():
    with pytest.raises(ValidationError):
        AnswerScore(question="q", technical_accuracy=6, clarity=3, structure=3,
                    works_for_non_technical_listener=True, non_technical_notes="", feedback="")


def test_plan_schema_accepts_valid_plan():
    InterviewPlan(role="SE", seniority="mid", focus_areas=["APIs"], candidate_strengths=[],
                  candidate_gaps=[], customer_scenario="Bakery owner, 401s",
                  questions=[{"id": 1, "kind": "customer_roleplay", "topic": "api",
                              "question": "q", "what_good_looks_like": "x"}])


def test_agent_tree_wiring():
    root = build_root()
    modes = {a.name: a.mode for a in root.sub_agents}
    assert modes == {"jd_analyst": "single_turn", "interviewer": "task",
                     "evaluator": "single_turn", "coach": "single_turn"}
    analyst, interviewer, evaluator, coach = root.sub_agents
    assert (analyst.output_key, evaluator.output_key, coach.output_key) == ("plan", "scores", "report")
    assert analyst.output_schema is InterviewPlan
    tool_names = {getattr(t, "name", getattr(t, "__name__", None)) for t in interviewer.tools}
    assert {"record_turn", "get_questions"} <= tool_names


def test_voice_app_uses_live_model_only_for_speaking_agents():
    root = build_root(speaking_model="live-x", worker_model="text-y")
    by_name = {a.name: a.model.model for a in root.sub_agents}
    assert root.model.model == "live-x" and by_name["interviewer"] == "live-x"
    assert by_name["jd_analyst"] == by_name["evaluator"] == by_name["coach"] == "text-y"
