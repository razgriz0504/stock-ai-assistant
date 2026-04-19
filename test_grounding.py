"""测试 litellm + Gemini Google Search Grounding 是否生效"""
import os
import json
from litellm import completion
from dotenv import load_dotenv

load_dotenv()

print(f"GEMINI_API_KEY: {'set' if os.environ.get('GEMINI_API_KEY') else 'NOT SET'}")

# 测试1: 用 litellm 传 tools 参数
print("\n=== 测试1: litellm + tools=[{'googleSearch': {}}] ===")
try:
    response = completion(
        model="gemini/gemini-2.0-flash",
        messages=[{"role": "user", "content": "S&P 500 指数当前的 Forward P/E 是多少？近5年均值是多少？"}],
        tools=[{"googleSearch": {}}],
        safety_settings=[
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
        ],
        timeout=60,
    )
    content = response.choices[0].message.content
    print(f"Content: {content[:300]}...")
    
    # 检查 grounding metadata
    hidden = getattr(response, "_hidden_params", {})
    gm = hidden.get("vertex_ai_grounding_metadata", [])
    print(f"\n_hidden_params grounding_metadata: {json.dumps(gm, indent=2, ensure_ascii=False)[:500]}")
    
    attr_gm = getattr(response, "vertex_ai_grounding_metadata", [])
    print(f"attr grounding_metadata: {json.dumps(attr_gm, indent=2, ensure_ascii=False)[:500]}")
    
    model_extra = getattr(response, "model_extra", {})
    me_gm = model_extra.get("vertex_ai_grounding_metadata", [])
    print(f"model_extra grounding_metadata: {json.dumps(me_gm, indent=2, ensure_ascii=False)[:500]}")

except Exception as e:
    print(f"ERROR: {e}")

# 测试2: 直接用 google-genai SDK 对比
print("\n\n=== 测试2: google-genai SDK (原生) ===")
try:
    from google import genai
    from google.genai import types
    
    client = genai.Client()
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[grounding_tool])
    
    response2 = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="S&P 500 指数当前的 Forward P/E 是多少？近5年均值是多少？",
        config=config,
    )
    print(f"Content: {response2.text[:300]}...")
    
    gm2 = response2.candidates[0].grounding_metadata
    print(f"\ngrounding_metadata type: {type(gm2)}")
    print(f"webSearchQueries: {getattr(gm2, 'web_search_queries', 'N/A')}")
    chunks = getattr(gm2, 'grounding_chunks', [])
    print(f"groundingChunks ({len(chunks)}):")
    for i, c in enumerate(chunks[:5]):
        web = getattr(c, 'web', None)
        if web:
            print(f"  [{i}] {web.title} -> {web.uri}")
except ImportError:
    print("google-genai SDK not installed, skipping")
except Exception as e:
    print(f"ERROR: {e}")
