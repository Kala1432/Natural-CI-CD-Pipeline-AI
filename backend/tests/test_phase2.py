import pytest
from unittest.mock import patch, MagicMock
from backend.services.ai_service import AIService
from backend.services.workflow_service import build_workflow
from backend.models_mongo import Project, AutomationStep, DetectedStack


def test_ai_validate_pipeline_valid():
    svc = AIService()
    yaml_str = """
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm install
"""
    is_valid, result = svc.validate_pipeline(yaml_str)
    assert is_valid is True
    assert "npm install" in result


def test_ai_validate_pipeline_invalid_yaml():
    svc = AIService()
    yaml_str = """
name: CI
on: [push]
jobs:
  build:
   runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
    is_valid, result = svc.validate_pipeline(yaml_str)
    assert is_valid is False
    assert "Invalid YAML syntax" in result


def test_ai_validate_pipeline_missing_jobs():
    svc = AIService()
    yaml_str = """
name: CI
on: [push]
"""
    is_valid, result = svc.validate_pipeline(yaml_str)
    assert is_valid is False
    assert "missing required 'jobs' key" in result


def test_ai_validate_pipeline_placeholders():
    svc = AIService()
    yaml_str = """
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo your_token
"""
    is_valid, result = svc.validate_pipeline(yaml_str)
    assert is_valid is False
    assert "unresolved placeholders" in result


@patch("backend.services.workflow_service.AIService")
def test_build_workflow_fallback(MockAIService):
    # Mock AI to fail
    mock_ai = MagicMock()
    mock_ai.client = True
    mock_ai.generate_pipeline.return_value = None
    MockAIService.return_value = mock_ai

    project = MagicMock()
    project.repo_name = "test-repo"
    project.default_branch = "main"
    project.detected_stack = {"language": "python", "package_manager": "pip"}

    step = MagicMock()
    step.step_key = "lint"
    step.title = "Lint"

    # Should fallback to static generation
    yaml_output = build_workflow(project, [step])
    assert "name: HiFi CI" in yaml_output
    assert "jobs" in yaml_output


@patch("backend.services.workflow_service.AIService")
def test_build_workflow_uses_ai(MockAIService):
    # Mock AI to succeed
    mock_ai = MagicMock()
    mock_ai.client = True
    mock_ai.generate_pipeline.return_value = "name: AI Generated CI\njobs:\n  test:\n    runs-on: ubuntu-latest"
    MockAIService.return_value = mock_ai

    project = MagicMock()
    project.repo_name = "test-repo"
    project.default_branch = "main"
    project.detected_stack = {"language": "python", "package_manager": "pip"}

    step = MagicMock()
    step.step_key = "lint"
    step.title = "Lint"

    yaml_output = build_workflow(project, [step])
    assert "AI Generated CI" in yaml_output
    assert "jobs" in yaml_output
