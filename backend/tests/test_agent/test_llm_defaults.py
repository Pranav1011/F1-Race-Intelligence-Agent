"""
One default local model everywhere, and a local Ollama URL outside Docker.

`make setup` used to pull llama3.2 while the code defaulted to deepseek-r1:8b,
and the default base URL only resolved inside docker-compose.
"""

import re
from pathlib import Path

import pytest

from agent import graph as graph_module
from agent.llm import DEFAULT_OLLAMA_BASE_URL, DEFAULT_OLLAMA_MODEL, LLMConfig

REPO_ROOT = Path(__file__).resolve().parents[3]


def _repo_file(name: str) -> str:
    path = REPO_ROOT / name
    if not path.exists():
        pytest.skip(f"{name} is not available (backend-only checkout or container)")
    return path.read_text()


def test_default_model_is_the_tested_one():
    assert DEFAULT_OLLAMA_MODEL == "llama3.1:8b"
    assert LLMConfig().ollama_model == DEFAULT_OLLAMA_MODEL


def test_setup_compose_and_env_example_use_the_same_model():
    pulled = re.findall(r"ollama pull (\S+)", _repo_file("Makefile"))
    compose = re.search(r"OLLAMA_MODEL: \$\{OLLAMA_MODEL:-([^}]+)\}", _repo_file("docker-compose.yml"))
    env_example = re.search(r"^OLLAMA_MODEL=(\S+)$", _repo_file(".env.example"), re.MULTILINE)

    assert pulled == [DEFAULT_OLLAMA_MODEL]
    assert compose is not None and compose.group(1) == DEFAULT_OLLAMA_MODEL
    assert env_example is not None and env_example.group(1) == DEFAULT_OLLAMA_MODEL


def test_env_example_lists_every_provider_key():
    env_example = _repo_file(".env.example")
    for key in ("OPENAI_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY", "GOOGLE_API_KEY"):
        assert re.search(rf"^{key}=$", env_example, re.MULTILINE), key


def test_ollama_url_defaults_to_localhost_outside_docker(monkeypatch):
    from api.routers import chat

    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(chat, "_agent", None)
    monkeypatch.setattr(graph_module, "_agent", None)

    agent = chat.get_chat_agent()

    assert DEFAULT_OLLAMA_BASE_URL == "http://localhost:11434"
    assert agent.ollama_base_url == DEFAULT_OLLAMA_BASE_URL


def test_local_model_client_is_a_declared_dependency():
    # agent/llm.py imports ChatOllama from langchain_ollama; a fresh install
    # (pip/uv from pyproject, or the Docker image) failed at import without it
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text()
    assert '"langchain-ollama' in pyproject
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
    if dockerfile.exists():
        assert "langchain-ollama" in dockerfile.read_text()


def test_container_image_points_at_the_compose_ollama_service():
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
    if not dockerfile.exists():
        pytest.skip("Dockerfile is not available")
    assert "ENV OLLAMA_BASE_URL=http://ollama:11434" in dockerfile.read_text()
