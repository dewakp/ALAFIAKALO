---
applyTo: "ML/src/alafia_model/**,WEB/backend/app/services/alafia_model_service.py"
description: "ALAFIAModel development rules — use when adding capabilities, adapters, or wiring the model into the backend."
---

# ALAFIAModel — Domain Instructions

## Core Rule: ALAFIAModel First

All new AI/ML capabilities MUST be scaffolded in `ML/src/alafia_model/` first.
External API calls are temporary fallbacks — wrap them in adapters.

## Phase Discipline

Do not implement a phase out of order unless explicitly asked. Current status:
- Phase 1 NLM (meal parse): **LIVE**
- Phase 2–9: **PLANNED** (scaffold only, no model yet)

## Adding a New Capability

1. Create `ML/src/alafia_model/capabilities/<name>.py` extending `BaseCapability`
2. Set `is_implemented = False` until the model is trained and loaded
3. Add `capability_id`, `version`, `get_model_spec()` classmethod
4. Register in `ML/src/alafia_model/router.py` under `Modality` enum
5. Add phase entry to `ML/src/alafia_model/registry/roadmap.json`
6. All external AI calls inside the capability get `# TODO(alafia-model): replace with native model`

## Adding an Adapter

1. Create `ML/src/alafia_model/adapters/<service>_adapter.py` extending `BaseAdapter`
2. Implement `chat()`, `complete()`, `health_check()`
3. Mark with `# TODO(alafia-model): remove once Phase N is live`
4. Export from `ML/src/alafia_model/adapters/__init__.py`

## Wiring Into Backend

- The backend accesses ALAFIAModel via `WEB/backend/app/services/alafia_model_service.py`
- Use `get_alafia_model()` singleton — never instantiate `ALAFIAModel()` directly in endpoints
- Always `await model.infer(Modality.X, InferencePayload(...))`

## TODO Marker Convention

Every external AI call site must have:
```python
# TODO(alafia-model): replace with ALAFIAModel.<Modality>.<task> — Phase <N>
```

This lets us grep for migration progress:
```bash
grep -r "TODO(alafia-model)" WEB/backend/
```

## Model Registry

After training any model, add a record to `ML/src/alafia_model/registry/roadmap.json`
with `"status": "live"` and `"completed": "YYYY-MM-DD"`.

## Security

- Never log PHI in model inference calls
- `image_bytes`, `audio_bytes`, `video_bytes` in `InferencePayload` must not be stored
- All external adapter calls must de-identify health data before sending
