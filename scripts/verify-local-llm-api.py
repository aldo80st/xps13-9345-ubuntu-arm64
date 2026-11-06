#!/usr/bin/env python3
"""Test local OpenAI-compatible HTTP and streaming inference with stdlib only."""
import json
import sys
import time
from urllib.request import Request, urlopen

URL = "http://127.0.0.1:11434"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5:0.8b"

def get(path):
    with urlopen(URL + path, timeout=10) as response:
        assert response.status == 200
        return json.load(response)

def post(payload):
    request = Request(URL + "/v1/chat/completions",
                      data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"})
    return urlopen(request, timeout=180)

def main():
    version = get("/api/version")
    assert version.get("version")
    models = get("/v1/models")
    assert MODEL in [m.get("id") for m in models.get("data", [])], "Model missing"
    payload = {"model": MODEL, "messages": [{"role": "user",
               "content": "Responde en español: dos más dos."}],
               "stream": False, "max_tokens": 128,
               "temperature": 0, "reasoning_effort": "none"}
    latencies = []
    for i in range(3):
        t = time.monotonic()
        with post(payload) as response:
            assert response.status == 200
            answer = json.load(response)
        content = answer.get("choices", [{}])[0].get("message", {}).get("content")
        assert isinstance(content, str) and content.strip(), "Empty response"
        latencies.append(round(time.monotonic() - t, 2))
    payload["stream"] = True
    chunks, done = 0, False
    with post(payload) as response:
        assert response.status == 200
        for line in response:
            if not line.startswith(b"data: "):
                continue
            data = line[6:].strip()
            if data == b"[DONE]":
                done = True
                break
            obj = json.loads(data)
            if obj.get("choices"):
                chunks += 1
    assert chunks > 0 and done, "Streaming incomplete"
    print(json.dumps({"result": "PASS", "model": MODEL,
                     "ollama_version": version["version"],
                     "http_requests": 3, "seconds": latencies,
                     "sse_stream": "PASS"}))

if __name__ == "__main__":
    main()
