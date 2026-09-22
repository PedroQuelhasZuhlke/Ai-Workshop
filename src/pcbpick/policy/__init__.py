"""The `policy` stage: deterministic substitution-safety evaluation for candidates.

This is the safety core described in the repository's non-negotiable invariants. It
never asks an LLM to decide a tier, a pass/fail, or a derating factor — see
`.github/skills/substitution-policy/SKILL.md`.
"""

from pcbpick.policy.candidate_input import PrePolicyCandidate
from pcbpick.policy.derating_config import (
    DEFAULT_DERATING_CONFIG,
    DERATING_CONFIG_VERSION,
    DeratingConfig,
)
from pcbpick.policy.rules import evaluate_candidate
from pcbpick.policy.stage import PolicyStage, PolicyStageInput, RequirementCandidatePair

__all__ = [
    "DEFAULT_DERATING_CONFIG",
    "DERATING_CONFIG_VERSION",
    "DeratingConfig",
    "PolicyStage",
    "PolicyStageInput",
    "PrePolicyCandidate",
    "RequirementCandidatePair",
    "evaluate_candidate",
]
