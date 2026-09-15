"""The Phase 5 network: MobileNetV3-Small with one output per kind of label.

    dish        softmax — what is being made or served
    components  sigmoid per class — what it is made of; several at once
    stage       softmax — how far through preparation

A single softmax over dish names cannot answer "what is in this": a composite
has several components at once. That is why components is its own
multi-label output.

Normalisation and output activations live INSIDE the graph. Every client feeds
raw 0-255 RGB and reads probabilities, instead of three platforms each
re-implementing ImageNet mean/std and softmax — the likeliest place for an
on-device model to disagree silently with the one that was evaluated.
"""

from __future__ import annotations

import torch
from torch import nn
from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

from food_vision.dataset import HEAD_KIND, HEAD_ORDER

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
EMBED_WIDTH = 1024


class FoodNet(nn.Module):
    def __init__(self, head_sizes: dict[str, int], pretrained: bool = True):
        super().__init__()
        unknown = set(head_sizes) - set(HEAD_ORDER)
        if unknown:
            raise ValueError(f"unknown head(s): {sorted(unknown)}")
        self.head_names = [name for name in HEAD_ORDER if head_sizes.get(name)]
        if not self.head_names:
            raise ValueError("a model needs at least one output")
        self.head_sizes = {name: int(head_sizes[name]) for name in self.head_names}

        base = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None)
        self.features = base.features
        self.pool = nn.AdaptiveAvgPool2d(1)
        # The pretrained 576 -> 1024 projection is kept; only the heads start from zero.
        self.embed = nn.Sequential(base.classifier[0], nn.Hardswish(), nn.Dropout(0.2))
        self.heads = nn.ModuleDict({name: nn.Linear(EMBED_WIDTH, size) for name, size in self.head_sizes.items()})
        self.register_buffer("mean", torch.tensor(IMAGENET_MEAN).view(1, 3, 1, 1) * 255.0)
        self.register_buffer("std", torch.tensor(IMAGENET_STD).view(1, 3, 1, 1) * 255.0)

    def set_trunk_trainable(self, trainable: bool) -> None:
        for parameter in self.features.parameters():
            parameter.requires_grad_(trainable)

    def logits(self, image: torch.Tensor) -> dict[str, torch.Tensor]:
        """Raw scores for training, where the losses want logits."""
        x = (image - self.mean) / self.std
        embedding = self.embed(torch.flatten(self.pool(self.features(x)), 1))
        return {name: self.heads[name](embedding) for name in self.head_names}

    def forward(self, image: torch.Tensor) -> tuple[torch.Tensor, ...]:
        """Probabilities, one tensor per head in HEAD_ORDER — the exported graph.

        image: float32 RGB in 0-255, NCHW.
        """
        scores = self.logits(image)
        return tuple(
            torch.sigmoid(scores[name]) if HEAD_KIND[name] == "multi" else torch.softmax(scores[name], dim=-1)
            for name in self.head_names
        )
