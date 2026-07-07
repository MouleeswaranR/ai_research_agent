"""Check authorization and working status for all 121 NVIDIA NIM models using OpenAI SDK."""

import os
import sys
import asyncio
from dotenv import load_dotenv
from openai import OpenAI, APIStatusError, APIConnectionError

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv(override=True)

NVIDIA_NIM_API_KEY = os.getenv("NVIDIA_NIM_API_KEY", "")
NVIDIA_NIM_BASE_URL = os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")

MODELS_TO_TEST = [
    "01-ai/yi-large",
    "abacusai/dracarys-llama-3.1-70b-instruct",
    "adept/fuyu-8b",
    "ai21labs/jamba-1.5-large-instruct",
    "aisingapore/sea-lion-7b-instruct",
    "baai/bge-m3",
    "bigcode/starcoder2-15b",
    "bytedance/seed-oss-36b-instruct",
    "databricks/dbrx-instruct",
    "deepseek-ai/deepseek-coder-6.7b-instruct",
    "deepseek-ai/deepseek-v4-flash",
    "deepseek-ai/deepseek-v4-pro",
    "google/codegemma-1.1-7b",
    "google/codegemma-7b",
    "google/deplot",
    "google/diffusiongemma-26b-a4b-it",
    "google/gemma-2-2b-it",
    "google/gemma-2b",
    "google/gemma-3-12b-it",
    "google/gemma-3-4b-it",
    "google/gemma-3n-e2b-it",
    "google/gemma-3n-e4b-it",
    "google/gemma-4-31b-it",
    "google/recurrentgemma-2b",
    "ibm/granite-3.0-3b-a800m-instruct",
    "ibm/granite-3.0-8b-instruct",
    "ibm/granite-34b-code-instruct",
    "ibm/granite-8b-code-instruct",
    "meta/codellama-70b",
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.2-11b-vision-instruct",
    "meta/llama-3.2-1b-instruct",
    "meta/llama-3.2-3b-instruct",
    "meta/llama-3.2-90b-vision-instruct",
    "meta/llama-3.3-70b-instruct",
    "meta/llama-4-maverick-17b-128e-instruct",
    "meta/llama-guard-4-12b",
    "meta/llama2-70b",
    "microsoft/kosmos-2",
    "microsoft/phi-3-vision-128k-instruct",
    "microsoft/phi-3.5-moe-instruct",
    "microsoft/phi-4-mini-instruct",
    "microsoft/phi-4-multimodal-instruct",
    "minimaxai/minimax-m2.7",
    "minimaxai/minimax-m3",
    "mistralai/codestral-22b-instruct-v0.1",
    "mistralai/ministral-14b-instruct-2512",
    "mistralai/mistral-7b-instruct-v0.3",
    "mistralai/mistral-large",
    "mistralai/mistral-large-2-instruct",
    "mistralai/mistral-large-3-675b-instruct-2512",
    "mistralai/mistral-medium-3.5-128b",
    "mistralai/mistral-nemotron",
    "mistralai/mistral-small-4-119b-2603",
    "mistralai/mixtral-8x22b-v0.1",
    "mistralai/mixtral-8x7b-instruct-v0.1",
    "moonshotai/kimi-k2.6",
    "nv-mistralai/mistral-nemo-12b-instruct",
    "nvidia/ai-synthetic-video-detector",
    "nvidia/cosmos-reason2-8b",
    "nvidia/embed-qa-4",
    "nvidia/gliner-pii",
    "nvidia/ising-calibration-1-35b-a3b",
    "nvidia/llama-3.1-nemoguard-8b-content-safety",
    "nvidia/llama-3.1-nemoguard-8b-topic-control",
    "nvidia/llama-3.1-nemotron-51b-instruct",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "nvidia/llama-3.1-nemotron-nano-8b-v1",
    "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
    "nvidia/llama-3.1-nemotron-safety-guard-8b-v3",
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    "nvidia/llama-3.2-nemoretriever-1b-vlm-embed-v1",
    "nvidia/llama-3.2-nv-embedqa-1b-v1",
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nvidia/llama-nemotron-embed-1b-v2",
    "nvidia/llama-nemotron-embed-vl-1b-v2",
    "nvidia/llama3-chatqa-1.5-70b",
    "nvidia/mistral-nemo-minitron-8b-8k-instruct",
    "nvidia/nemoretriever-parse",
    "nvidia/nemotron-3-content-safety",
    "nvidia/nemotron-3-nano-30b-a3b",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3.5-content-safety",
    "nvidia/nemotron-4-340b-instruct",
    "nvidia/nemotron-4-340b-reward",
    "nvidia/nemotron-content-safety-reasoning-4b",
    "nvidia/nemotron-mini-4b-instruct",
    "nvidia/nemotron-nano-12b-v2-vl",
    "nvidia/nemotron-nano-3-30b-a3b",
    "nvidia/nemotron-parse",
    "nvidia/neva-22b",
    "nvidia/nv-embed-v1",
    "nvidia/nv-embedcode-7b-v1",
    "nvidia/nv-embedqa-e5-v5",
    "nvidia/nv-embedqa-mistral-7b-v2",
    "nvidia/nvclip",
    "nvidia/nvidia-nemotron-nano-9b-v2",
    "nvidia/riva-translate-4b-instruct",
    "nvidia/riva-translate-4b-instruct-v1.1",
    "nvidia/vila",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-next-80b-a3b-instruct",
    "qwen/qwen3.5-122b-a10b",
    "qwen/qwen3.5-397b-a17b",
    "sarvamai/sarvam-m",
    "snowflake/arctic-embed-l",
    "stepfun-ai/step-3.5-flash",
    "stepfun-ai/step-3.7-flash",
    "stockmark/stockmark-2-100b-instruct",
    "upstage/solar-10.7b-instruct",
    "writer/palmyra-creative-122b",
    "writer/palmyra-fin-70b-32k",
    "writer/palmyra-med-70b",
    "writer/palmyra-med-70b-32k",
    "z-ai/glm-5.2",
    "zyphra/zamba2-7b-instruct",
]


def test_model_sync(client: OpenAI, model_name: str) -> tuple[str, int, str]:
    extra_body = None
    if "glm" in model_name.lower() or "nemotron" in model_name.lower():
        extra_body = {"chat_template_kwargs": {"enable_thinking": True, "clear_thinking": False}}

    try:
        kwargs = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 10,
            "temperature": 0.1,
            "timeout": 12.0,
        }
        if extra_body:
            kwargs["extra_body"] = extra_body

        res = client.chat.completions.create(**kwargs)
        if res.choices:
            return model_name, 200, "OK"
        return model_name, 200, "Empty choices"

    except APIStatusError as err:
        return model_name, err.status_code, err.message[:80]
    except APIConnectionError as err:
        return model_name, 0, f"ConnectionError: {err}"
    except Exception as err:
        return model_name, 0, str(err)[:80]


def main():
    print("=" * 60)
    print(f"  NVIDIA NIM FULL MODEL TESTER ({len(MODELS_TO_TEST)} Models)")
    print("=" * 60)

    if not NVIDIA_NIM_API_KEY or NVIDIA_NIM_API_KEY.startswith("your-"):
        print("\n❌ NVIDIA_NIM_API_KEY is not set or is a placeholder in .env!")
        sys.exit(1)

    masked_key = NVIDIA_NIM_API_KEY[:8] + "..." + NVIDIA_NIM_API_KEY[-4:]
    print(f"  Base URL: {NVIDIA_NIM_BASE_URL}")
    print(f"  API Key:  {masked_key}\n")

    client = OpenAI(
        base_url=NVIDIA_NIM_BASE_URL,
        api_key=NVIDIA_NIM_API_KEY,
    )

    working = []
    forbidden = []
    not_found = []
    other_errs = []

    for idx, model in enumerate(MODELS_TO_TEST, 1):
        name, code, msg = test_model_sync(client, model)
        if code == 200:
            print(f"[{idx:3d}/{len(MODELS_TO_TEST)}] ✅ [200 OK]        {name}")
            working.append(name)
        elif code == 403:
            print(f"[{idx:3d}/{len(MODELS_TO_TEST)}] ❌ [403 Forbidden] {name}")
            forbidden.append(name)
        elif code == 404:
            print(f"[{idx:3d}/{len(MODELS_TO_TEST)}] ⚠️ [404 Not Found] {name}")
            not_found.append(name)
        else:
            print(f"[{idx:3d}/{len(MODELS_TO_TEST)}] ⚠️ [{code}]            {name} -> {msg}")
            other_errs.append((name, code, msg))

    print("\n" + "=" * 60)
    print("  SUMMARY RESULTS")
    print("=" * 60)
    print(f"  ✅ Working (200 OK):      {len(working)}")
    print(f"  ❌ Forbidden (403):       {len(forbidden)}")
    print(f"  ⚠️ Not Found (404):       {len(not_found)}")
    print(f"  ⚠️ Other Errors / Timeout: {len(other_errs)}")
    print("=" * 60)

    if working:
        print("\n🎉 Verified Working Models for Your API Key:")
        for w in working:
            print(f"  • {w}")


if __name__ == "__main__":
    main()
