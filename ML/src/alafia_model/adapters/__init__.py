# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""ALAFIAModel adapters package."""

from alafia_model.adapters.base_adapter import BaseAdapter
from alafia_model.adapters.ollama_adapter import OllamaAdapter
from alafia_model.adapters.openai_adapter import OpenAIAdapter

__all__ = ["BaseAdapter", "OllamaAdapter", "OpenAIAdapter"]
