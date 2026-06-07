#!/usr/bin/env python3
"""Quick test of Claude 3 Haiku for nutrition estimation."""
import anthropic, json

c = anthropic.Anthropic()
r = c.messages.create(
    model='claude-3-haiku-20240307',
    system='You are an expert renal dietitian. Return ONLY valid JSON with keys: calories, protein, carbs, fat, fiber, sugar, sodium, potassium, calcium, iron, phosphorus, cholesterol. All values are numbers.',
    messages=[{'role':'user','content':'Estimate nutrients: 1 cup of garri made into eba + 2 cups of melon soup with chard, fish, chicken; 1 cup of pineapple juice'}],
    temperature=0.1, max_tokens=800
)
print('Model:', r.model)
print('Input:', r.usage.input_tokens, '| Output:', r.usage.output_tokens)
cost = (r.usage.input_tokens * 0.25 + r.usage.output_tokens * 1.25) / 1_000_000
print(f'Cost this call: ${cost:.6f}')
print(f'Est for 3833 rows: ${cost * 3833:.2f}')
print()
print(r.content[0].text)
