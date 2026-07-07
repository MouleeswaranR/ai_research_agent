"""Retry rate-limited models + test additional free models on OpenRouter."""
import asyncio
import httpx
import json
import os

API_KEY = os.environ.get("OPENROUTER_API_KEY", "your-api-key-here")
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# Retry rate-limited ones (429) with staggered delays, plus extras
MODELS_TO_TEST = [
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "openai/gpt-oss-120b:free",
    "google/gemma-4-31b-it:free",
    # Additional free models to try
    "deepseek/deepseek-r1:free",
    "qwen/qwen3-235b-a22b:free",
    "microsoft/phi-4-reasoning-plus:free",
    "meta-llama/llama-4-maverick:free",
    "google/gemini-2.5-flash-preview-05-20:free",
]

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com/ai-software-builder-agent",
    "X-Title": "Auto Dev Agent",
}

async def test_model(client: httpx.AsyncClient, model: str, delay: float = 0) -> dict:
    if delay > 0:
        await asyncio.sleep(delay)
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Reply with exactly: HELLO_OK"}
        ],
        "max_tokens": 30,
        "temperature": 0.0,
    }
    try:
        resp = await client.post(BASE_URL, json=payload, headers=HEADERS, timeout=60.0)
        if resp.status_code == 200:
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            msg = choice.get("message") or {}
            content = msg.get("content", "") or ""
            return {"model": model, "status": "OK", "response": content[:80]}
        else:
            error_text = resp.text[:200]
            return {"model": model, "status": f"FAIL ({resp.status_code})", "response": error_text}
    except Exception as e:
        return {"model": model, "status": "ERROR", "response": str(e)[:120]}

async def main():
    results = []
    async with httpx.AsyncClient() as client:
        # Stagger requests to avoid simultaneous rate limiting
        tasks = [test_model(client, m, delay=i*2) for i, m in enumerate(MODELS_TO_TEST)]
        results = await asyncio.gather(*tasks)
    
    print("\n" + "=" * 80)
    print("  OPENROUTER FREE MODEL VERIFICATION (Round 2)")
    print("=" * 80)
    
    working = []
    failed = []
    for r in results:
        icon = "OK" if r["status"] == "OK" else "FAIL"
        print(f"\n  [{icon}] {r['model']}")
        print(f"       Status: {r['status']}")
        print(f"       Response: {r['response']}")
        if r["status"] == "OK":
            working.append(r["model"])
        else:
            failed.append(r["model"])
    
    print("\n" + "-" * 80)
    print("  CONFIRMED WORKING (from both rounds):")
    confirmed = working + [
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "google/gemma-4-26b-a4b-it:free",
    ]
    for m in confirmed:
        print(f"    OK  {m}")
    print(f"\n  Total available: {len(confirmed)}")

if __name__ == "__main__":
    asyncio.run(main())
