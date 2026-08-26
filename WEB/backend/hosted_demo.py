"""Real hosted-provider call: show the payload, the response, and the latency."""
import asyncio, json, time
import app.services.alafia_model_service  # sys.path side effect  # noqa: F401
from alafia_model import privacy
from alafia_model.capabilities.llm import LLMCapability
from alafia_model.adapters import anthropic_adapter as aa

SENT = {}
_orig = aa.AnthropicAdapter.chat

async def spy(self, messages, **kw):
    SENT["messages"] = messages
    SENT["model"] = getattr(self, "model", None)
    return await _orig(self, messages, **kw)

aa.AnthropicAdapter.chat = spy

# A real dev user, identified the way the auth dependency does it.
USER_ID, NAME, EMAIL, PHONE = 63, "Jane Doe", "jane.doe@example.com", "+1 (555) 010-9999"
privacy.register_identity(user_id=USER_ID, name=NAME, email=EMAIL, phone=PHONE)

PROMPT = (
    f"I'm {NAME} ({EMAIL}, {PHONE}), DOB 04/11/1962, record MRN0012345. "
    "Dr. Sarah Okafor put me on calcitriol 0.5 mcg. My potassium was 5.2 and "
    "phosphorus 6.1 after dialysis. In one short paragraph: should I be worried?"
)

async def main():
    cap = LLMCapability()
    print("=" * 78); print("WHAT THE USER TYPED (stays inside ALAFIA)"); print("=" * 78)
    print(PROMPT)

    print()
    print("=" * 78); print(f"ALAFIA SUBJECT TOKEN  (user id {USER_ID} -> opaque handle)"); print("=" * 78)
    print(f"  {privacy.current_subject()}")

    t0 = time.monotonic()
    r = await cap.infer({"task": "chat", "local_only": False, "max_tokens": 300,
                         "messages": [{"role": "user", "content": PROMPT}]})
    elapsed = time.monotonic() - t0

    print()
    print("=" * 78); print("EXACT PAYLOAD SENT TO THE HOSTED PROVIDER"); print("=" * 78)
    print(json.dumps(SENT.get("messages"), indent=2))

    print()
    print("=" * 78); print("LEAK CHECK ON THAT PAYLOAD"); print("=" * 78)
    wire = json.dumps(SENT.get("messages") or [])
    for label, needle in [("name", NAME), ("email", EMAIL), ("phone", "010-9999"),
                          ("DOB", "04/11/1962"), ("record no.", "MRN0012345"),
                          ("clinician name", "Okafor")]:
        print(f"  {label:<16} {'*** LEAKED ***' if needle in wire else 'absent'}")
    print(f"  {'subject token':<16} {'present' if privacy.current_subject() in wire else 'MISSING'}")
    for label, needle in [("potassium 5.2", "5.2"), ("phosphorus 6.1", "6.1"),
                          ("calcitriol", "calcitriol"), ("dose 0.5 mcg", "0.5 mcg")]:
        print(f"  {label:<16} {'kept' if needle in wire else 'LOST'}")

    print()
    print("=" * 78); print("THE PROVIDER'S ACTUAL RESPONSE"); print("=" * 78)
    print(f"  provider : {(r.data or {}).get('provider')}")
    print(f"  model    : {(r.data or {}).get('model')}")
    print(f"  tokens   : {(r.data or {}).get('tokens_used')}")
    print(f"  LATENCY  : {elapsed:.2f} s")
    print()
    print((r.data or {}).get("text") or r.error)

asyncio.run(main())
