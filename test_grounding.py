"""测试 litellm + Gemini Google Search Grounding - 精简版"""
import os
import json
from litellm import completion
from dotenv import load_dotenv

load_dotenv()

print(f"GEMINI_API_KEY: {'set' if os.environ.get('GEMINI_API_KEY') else 'NOT SET'}")

MODELS_TO_TEST = [
    "gemini/gemini-2.0-flash",
    "gemini/gemini-3.1-pro-preview",
]

SAFETY = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
]

PROMPT = "S&P 500 Forward P/E 当前值？近5年均值、最低、最高？"

for model_name in MODELS_TO_TEST:
    print(f"\n{'='*60}")
    print(f"模型: {model_name}")
    print(f"{'='*60}")
    try:
        response = completion(
            model=model_name,
            messages=[{"role": "user", "content": PROMPT}],
            tools=[{"googleSearch": {}}],
            safety_settings=SAFETY,
            timeout=120,
        )
        content = response.choices[0].message.content
        print(f"\n--- 回答 ---")
        print(content[:500])

        # 精确检查 metadata 结构（只打印 key 和关键字段）
        gm = getattr(response, "_hidden_params", {}).get(
            "vertex_ai_grounding_metadata", []
        )
        if not gm:
            gm = getattr(response, "vertex_ai_grounding_metadata", [])

        print(f"\n--- grounding_metadata 结构 ---")
        for i, m in enumerate(gm):
            keys = list(m.keys())
            print(f"  metadata[{i}] keys: {keys}")

            if "webSearchQueries" in m:
                print(f"  webSearchQueries: {m['webSearchQueries']}")

            if "groundingChunks" in m:
                chunks = m["groundingChunks"]
                print(f"  groundingChunks ({len(chunks)} items):")
                for j, c in enumerate(chunks[:5]):
                    web = c.get("web", {})
                    print(f"    [{j}] {web.get('title', '?')} -> {web.get('uri', '?')[:80]}")

            if "groundingSupports" in m:
                supports = m["groundingSupports"]
                print(f"  groundingSupports: {len(supports)} items")

            if "searchEntryPoint" in m:
                print(f"  searchEntryPoint: present (CSS/HTML, skipped)")

        if not gm:
            print("  (no grounding_metadata found)")

    except Exception as e:
        print(f"ERROR: {e}")

print("\n\nDone.")
