"""ALAFIAModel Phase 5 — the on-device food classifier: data, training, export.

Deliberately OUTSIDE ``ML/src/alafia_model``: that package is vendored into the
backend image at deploy time (deploy.sh), and none of this — torch, TensorFlow,
coremltools — belongs in a web server. Only an exported, verified model does.

This package must stay importable without torch: ``parity`` is used on the Mac
to verify Core ML, where the host has numpy and coremltools and nothing else.
"""
