from app.agents import NeuroPilotWorkflow
from app.demo import load_demo_request


def _minutes(value):
    return value.hour * 60 + value.minute


def test_workflow_places_demo_tasks_without_fixed_calendar_conflicts():
    request = load_demo_request()
    result = NeuroPilotWorkflow().run(request)

    assert result.evaluation.approved
    assert len(result.schedule.recommendations) == len(request.tasks)
    assert {step.agent for step in result.trace} == {
        "Cognitive Analyst",
        "Task Analyst",
        "Planning Agent",
        "Safety Reviewer",
        "Cognitive Coach",
    }

    planned = result.schedule.recommendations
    for index, first in enumerate(planned):
        for second in planned[index + 1 :]:
            assert not (_minutes(first.start) < _minutes(second.end) and _minutes(first.end) > _minutes(second.start))
        for block in request.calendar:
            assert not (_minutes(first.start) < _minutes(block.end) and _minutes(first.end) > _minutes(block.start))


def test_task_agent_classifies_investor_pitch_as_strategic():
    result = NeuroPilotWorkflow().run(load_demo_request())
    pitch = next(profile for profile in result.task_profiles if profile.title == "Prepare investor pitch")

    assert pitch.category == "strategic"
    assert pitch.requirements.executive >= 0.9

