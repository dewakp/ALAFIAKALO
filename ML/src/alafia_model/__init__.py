"""ALAFIAModel — Unified Multimodal Health AI.

This package is the future backbone of ALAFIA's AI layer. It provides a single
router interface ``ALAFIAModel.infer(modality, payload)`` that dispatches to the
correct capability module.

Architecture phases:
  Phase 1  NLM: food text → (food, qty_g) pairs              [scaffolded]
  Phase 2  NLM: clinical text → ICD-10 / symptoms            [planned]
  Phase 3  LLM: health coaching (fine-tuned BioMistral 7B)   [planned]
  Phase 4  LLM: nutrition RAG over USDA / WAFCT              [planned]
  Phase 5  Vision: food photo → nutrition                     [planned]
  Phase 6  Vision: lab report OCR → structured data           [planned]
  Phase 7  Voice: speech → clinical NLP                       [planned]
  Phase 8  Video: exercise form analysis                      [planned]
  Phase 9  Unified API: ALAFIAModel.infer(modality, input)    [planned]

Usage (once fully implemented)::

    from alafia_model import ALAFIAModel, Modality, InferencePayload

    model = ALAFIAModel()
    result = await model.infer(
        Modality.LLM,
        InferencePayload(text="What should I eat to lower my potassium?")
    )
"""

from alafia_model.router import ALAFIAModel, Modality, InferencePayload, InferenceResult

__all__ = ["ALAFIAModel", "Modality", "InferencePayload", "InferenceResult"]
__version__ = "0.1.0-scaffold"
