#!/usr/bin/env python
"""Verify NIM model availability and test fallback mechanism."""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.agents.llm_client import call_llm


async def test_model(model_name: str, agent_name: str) -> dict:
    """Test a specific model and return status."""
    print(f"\n🔍 Testing: {agent_name}")
    print(f"   Model: {model_name}")
    
    try:
        result = await call_llm(
            messages=[{"role": "user", "content": "Respond with: OK"}],
            agent_name=agent_name,
            model=model_name,
            max_tokens=10,
            temperature=0,
        )
        
        provider = result.get("provider", "unknown")
        content = result.get("content", "")
        
        if provider == "nvidia_nim":
            print(f"   ✅ Success via NIM")
        else:
            print(f"   ⚠️  Fallback to {provider}")
        
        return {
            "agent": agent_name,
            "model": model_name,
            "status": "success",
            "provider": provider,
            "fallback_used": provider != "nvidia_nim"
        }
    
    except Exception as e:
        print(f"   ❌ Failed: {str(e)[:100]}")
        return {
            "agent": agent_name,
            "model": model_name,
            "status": "failed",
            "error": str(e)[:200]
        }


async def main():
    """Run verification tests on all configured models."""
    
    print("=" * 60)
    print("🚀 NVIDIA NIM Model Availability Check")
    print("=" * 60)
    
    # Check API keys
    if not settings.nvidia_nim_api_key or settings.nvidia_nim_api_key == "your-nvidia-nim-api-key-here":
        print("\n❌ NVIDIA_NIM_API_KEY not set in .env")
        print("   Get your key from: https://build.nvidia.com/")
        return
    
    if not settings.groq_api_key or settings.groq_api_key == "your-groq-api-key-here":
        print("\n⚠️  GROQ_API_KEY not set - fallback unavailable")
        print("   Get your key from: https://console.groq.com/")
    
    print(f"\n📋 Provider: {settings.llm_provider}")
    print(f"   NIM Base: {settings.nvidia_nim_base_url}")
    
    # Test each agent's configured model
    agent_models = settings.AGENT_MODEL_MAP
    results = []
    
    for agent_name, model_name in agent_models.items():
        result = await test_model(model_name, agent_name)
        results.append(result)
        await asyncio.sleep(0.5)  # Rate limit courtesy
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    
    successes = [r for r in results if r["status"] == "success"]
    failures = [r for r in results if r["status"] == "failed"]
    fallbacks = [r for r in results if r.get("fallback_used")]
    
    print(f"\n✅ Successful: {len(successes)}/{len(results)}")
    print(f"❌ Failed: {len(failures)}/{len(results)}")
    print(f"⚠️  Fallbacks: {len(fallbacks)}/{len(results)}")
    
    if fallbacks:
        print("\n⚠️  Models using fallback (verify in NIM catalog):")
        for r in fallbacks:
            print(f"   - {r['agent']}: {r['model']}")
    
    if failures:
        print("\n❌ Failed models:")
        for r in failures:
            print(f"   - {r['agent']}: {r['model']}")
            print(f"     Error: {r.get('error', 'Unknown')[:80]}")
    
    # Recommendations
    print("\n" + "=" * 60)
    print("💡 RECOMMENDATIONS")
    print("=" * 60)
    
    if len(fallbacks) > 5:
        print("\n⚠️  Many models using fallback. Consider using safe configuration:")
        print("   Uncomment 'Safe Fallback Configuration' in .env.example")
        print("   All agents will use: meta/llama-3.3-70b-instruct")
    
    if failures:
        print("\n❌ Some models completely failed.")
        print("   Check:")
        print("   1. NVIDIA_NIM_API_KEY is valid")
        print("   2. GROQ_API_KEY is set for fallback")
        print("   3. Internet connectivity")
    
    if len(successes) == len(results) and len(fallbacks) == 0:
        print("\n✅ All models working perfectly via NIM!")
        print("   System ready to deploy.")
    
    elif len(successes) == len(results):
        print("\n✅ All models accessible (some via fallback)")
        print("   System ready to deploy with automatic failover.")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Verification interrupted")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
