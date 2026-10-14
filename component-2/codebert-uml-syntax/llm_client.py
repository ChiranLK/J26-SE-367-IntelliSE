import json
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5-coder:7b"


def is_running(url=OLLAMA_URL):
    try:
        with urllib.request.urlopen(url + "/api/tags", timeout=5) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def installed_models(url=OLLAMA_URL):
    with urllib.request.urlopen(url + "/api/tags", timeout=5) as r:
        return [m["name"] for m in json.loads(r.read())["models"]]


# Ollama's default context window is small (2048 tokens). When a prompt is
# longer, Ollama silently drops the BEGINNING of it - for a repair prompt that is
# exactly the part that says what to fix. Our longest prompt (rules + example +
# diagram + feedback) plus the answer stays under ~3500 tokens, so 4096 is enough.
# A bigger window only makes every call slower and uses more memory.
NUM_CTX = 4096
# Keep the model in memory between calls. Ollama unloads it after 5 idle minutes
# by default, and loading 7B again costs 10-30 s.
KEEP_ALIVE = "30m"
# Upper limit for the answer, so a model that starts repeating itself cannot run forever.
MAX_ANSWER_TOKENS = 1500




def ask(prompt, model=DEFAULT_MODEL, temperature=0.2, url=OLLAMA_URL, timeout=900, num_ctx=NUM_CTX):
    """Send one prompt, return the model's reply as text."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": MAX_ANSWER_TOKENS},
    }
    req = urllib.request.Request(url + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


if __name__ == "__main__":
    if not is_running():
        print("Ollama is not running. Start the Ollama app (or run 'ollama serve') and try again.")
    else:
        print("models:", installed_models())
        print(ask("Reply with one word: ready"))