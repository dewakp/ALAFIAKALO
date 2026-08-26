import asyncio, statistics, time
import app.services.alafia_model_service  # noqa: F401
from alafia_model import privacy
from alafia_model.capabilities.llm import LLMCapability

privacy.register_identity(user_id=63, name="Jane Doe",
                          email="jane.doe@example.com", phone="+1 (555) 010-9999")

SHORT = "My potassium was 5.2 after dialysis. One sentence: is that concerning?"
LONG = ("I'm Jane Doe. Dialysis 3x weekly. Potassium 5.2, phosphorus 6.1, "
        "calcium 8.9, albumin 3.4, Kt/V 1.4. I take calcitriol 0.5 mcg, "
        "sevelamer 800 mg with meals, and epoetin weekly. Yesterday I ate jollof "
        "rice, grilled tilapia, plantain and a small orange. Give me three "
        "specific dietary adjustments for the next week, with reasons.")

async def bench(cap, label, prompt, local_only, runs=3, max_tokens=400):
    times, toks, provider, model = [], [], None, None
    for _ in range(runs):
        t0 = time.monotonic()
        r = await cap.infer({"task": "chat", "local_only": local_only,
                             "max_tokens": max_tokens,
                             "messages": [{"role": "user", "content": prompt}]})
        dt = time.monotonic() - t0
        if not r.success:
            print(f"  {label:<28} FAILED: {(r.error or '')[:70]}"); return
        times.append(dt); toks.append((r.data or {}).get("tokens_used") or 0)
        provider = (r.data or {}).get("provider"); model = (r.data or {}).get("model")
    print(f"  {label:<28} {statistics.median(times):6.2f}s median   "
          f"[{min(times):.2f}–{max(times):.2f}]  {int(statistics.mean(toks)):>4} tok   "
          f"{provider}:{str(model)[:28]}")

async def main():
    cap = LLMCapability()
    print("=" * 92)
    print("HOSTED PROVIDER (third-party, PII stripped)      3 runs each")
    print("=" * 92)
    await bench(cap, "short prompt", SHORT, local_only=False)
    await bench(cap, "long clinical prompt", LONG, local_only=False)

    print()
    print("=" * 92)
    print("ALAFIA-OPERATED OLLAMA (local; WARM here — prod is scale-to-zero)")
    print("=" * 92)
    await bench(cap, "short prompt", SHORT, local_only=True, runs=2)
    await bench(cap, "long clinical prompt", LONG, local_only=True, runs=2)

asyncio.run(main())
