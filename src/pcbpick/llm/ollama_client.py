"""A real `LLMClient` backed by a local Ollama server (https://ollama.com).

Opt-in only, never used by the test suite (`.github/instructions/testing.instructions.md`
forbids live network calls in tests, and `http://localhost:11434` is still a live
network call). See `orchestrator.default_llm_client` for how this is wired in.

Determinism, prompt files, and provenance rules all come from
`.github/instructions/llm-calls.instructions.md`; this module only adds the HTTP
transport, it does not change any of those rules.
"""

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_TIMEOUT_SECONDS = 60.0
_HEALTH_CHECK_TIMEOUT_SECONDS = 1.0
_STARTUP_POLL_SECONDS = 0.5
_STARTUP_TIMEOUT_SECONDS = 15.0


def is_reachable(base_url: str, timeout_seconds: float = _HEALTH_CHECK_TIMEOUT_SECONDS) -> bool:
    """A cheap liveness probe against Ollama's own `/api/tags` endpoint."""
    try:
        urlopen(Request(f"{base_url}/api/tags"), timeout=timeout_seconds)  # noqa: S310
    except (URLError, OSError):
        return False
    return True


def ensure_ollama_running(
    *, base_url: str = _DEFAULT_BASE_URL, timeout_seconds: float = _STARTUP_TIMEOUT_SECONDS
) -> bool:
    """Dev convenience for `PCBPICK_USE_LLM=1`: starts `ollama serve` if the server
    isn't already reachable, then waits (up to `timeout_seconds`) for it to come up.

    Best-effort and never raises — every LLM call site already degrades gracefully
    if the server stays unreachable (`.github/instructions/llm-calls.instructions.md`),
    so a `False` return here is not fatal, just logged for the operator to notice.
    """
    if is_reachable(base_url):
        return True
    ollama_path = shutil.which("ollama")
    if ollama_path is None:
        logger.warning(
            "PCBPICK_USE_LLM is set but Ollama is not reachable at %s and no `ollama` "
            "executable was found on PATH; LLM-assisted stages will degrade gracefully",
            base_url,
        )
        return False
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        subprocess.Popen(  # noqa: S603
            [ollama_path, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        subprocess.Popen(  # noqa: S603
            [ollama_path, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if is_reachable(base_url):
            return True
        time.sleep(_STARTUP_POLL_SECONDS)
    logger.warning(
        "started `ollama serve` but it did not become reachable at %s within %.0fs; "
        "LLM-assisted stages will degrade gracefully",
        base_url,
        timeout_seconds,
    )
    return False


def _render_prompt(
    *, template: str, variables: dict[str, str], response_model: type[BaseModel]
) -> str:
    instructions = (_TEMPLATES_DIR / f"{template}.md").read_text(encoding="utf-8")
    rendered_variables = "\n\n".join(f"### {name}\n{value}" for name, value in variables.items())
    schema = json.dumps(response_model.model_json_schema())
    return (
        f"{instructions}\n\n## Variables\n\n{rendered_variables}\n\n"
        "Respond with ONLY a single JSON object matching this schema — no prose, no "
        f"markdown code fences:\n{schema}"
    )


@dataclass(frozen=True)
class OllamaLLMClient:
    """Calls a local Ollama server's `/api/generate` endpoint with temperature 0.

    `generate` returns raw text for `call_structured` to validate — same contract as
    every other `LLMClient`. A connection failure is turned into a raw string that
    cannot parse as JSON rather than a raised exception, so it flows through the
    existing validate-retry-degrade path in `call_structured` instead of crashing the
    run (a raised exception here would violate the "never crashes" rule).
    """

    model_id: str
    base_url: str = _DEFAULT_BASE_URL
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS

    def generate(
        self, *, template: str, variables: dict[str, str], response_model: type[BaseModel]
    ) -> str:
        prompt = _render_prompt(
            template=template, variables=variables, response_model=response_model
        )
        payload = json.dumps(
            {
                "model": self.model_id,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0},
            }
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                body = json.loads(response.read())
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return f"<ollama unavailable at {self.base_url}: {exc}>"
        return str(body.get("response", ""))
