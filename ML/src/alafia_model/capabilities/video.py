"""ALAFIAModel Video Capability — Exercise Form Analysis.

Phase 8 (planned): video → exercise form feedback.
  - MediaPipe Pose for skeletal landmark extraction (on-device)
  - Temporal CNN / LSTM for rep counting and form classification
  - Joint angle analysis for injury-risk flagging

TODO(alafia-model): Phase 8 — build MediaPipe Pose + LSTM form classifier
TODO(alafia-model): Phase 8 — collect exercise video dataset for fine-tuning
"""

from __future__ import annotations

import logging
from typing import Any

from alafia_model.capabilities.base import BaseCapability, CapabilityResult

logger = logging.getLogger(__name__)

SUPPORTED_EXERCISES = [
    "squat", "deadlift", "push_up", "pull_up", "lunge",
    "plank", "shoulder_press", "bicep_curl",
]


class VideoCapability(BaseCapability):
    """Video capability for exercise form analysis and rep counting.

    Supported tasks (all PLANNED):
        "exercise_form"   → video → form score + feedback [PLANNED Ph8]
        "rep_count"       → video → exercise rep count [PLANNED Ph8]
        "gait_analysis"   → walking video → mobility score [PLANNED Ph8]
    """

    capability_id = "video"
    version = "0.1.0-scaffold"
    is_implemented = False

    async def infer(self, payload: dict[str, Any]) -> CapabilityResult:
        task = payload.get("task", "exercise_form")

        if task in ("exercise_form", "rep_count", "gait_analysis"):
            return self._scaffold_stub(task)

        return CapabilityResult(
            success=False,
            error=f"Unknown video task: {task}",
        )

    def _scaffold_stub(self, task: str) -> CapabilityResult:
        return CapabilityResult(
            success=False,
            error=(
                f"Video task '{task}' is planned for ALAFIAModel Phase 8. "
                f"Supported exercises will include: {', '.join(SUPPORTED_EXERCISES)}. "
                "See docs/AI_ENGINE_ARCHITECTURE.md for the roadmap."
            ),
        )

    @classmethod
    def get_model_spec(cls) -> dict:
        """Return the specification for the video analysis pipeline."""
        return {
            "pose_estimation": "MediaPipe Pose (on-device)",
            "form_classifier": "Temporal CNN + LSTM",
            "input": "video frames at 30 fps",
            "output": {
                "form_score": "0.0-1.0",
                "rep_count": "integer",
                "feedback": "list of actionable form corrections",
            },
            "supported_exercises": SUPPORTED_EXERCISES,
            "training_data": "NTURGB+D + custom ALAFIA exercise videos (to be collected)",
            "phase": 8,
            "status": "planned",
        }
