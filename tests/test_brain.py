"""Phase 6 brain tests in TEXT mode (no mic, no voice).
Run from the project root:  uv run python -m tests.test_brain
"""
import time

from brain.agent import Brain

# (phrase, expected tool or None for "answer directly")
TEST_SET = [
    ("open vs code", "open_app"),
    ("open notepad and calculator", "open_app"),
    ("open chrome and search python tutorials", "search_in_browser"),
    ("search lo-fi music on youtube", "search_in_browser"),
    ("open browser and search github", "search_in_browser"),
    ("open youtube", "open_website"),
    ("turn the volume up", "system_control"),
    ("take a screenshot", "system_control"),
    ("what time is it", "system_control"),
    ("what's the recent news in AI", "web_search"),
    ("who is the current prime minister of India", "web_search"),
    ("what is the capital of France", None),
    ("explain what RAG is", None),
    ("hello, how are you", None),
]


def show(brain, text):
    t0 = time.time()
    answer, tools = brain.run(text)
    print(f"  tools : {tools or '-'}")
    print(f"  reply : {answer}")
    print(f"  time  : {time.time() - t0:.2f}s")
    return tools


def chat(brain):
    print("Type a command ('reset' clears memory, Enter to go back).")
    while True:
        text = input("\nyou> ").strip()
        if not text:
            return
        if text.lower() == "reset":
            brain.reset()
            print("  memory cleared")
            continue
        show(brain, text)


def run_tests(brain):
    passed = 0
    for phrase, expected in TEST_SET:
        brain.reset()   # each test starts with clean memory
        print(f"\n> {phrase}")
        tools = show(brain, phrase)
        ok = (expected in tools) if expected else (not tools)
        passed += ok
        print(f"  {'PASS' if ok else 'FAIL'} (expected {expected})")
    print(f"\n{passed}/{len(TEST_SET)} passed")


def memory_test(brain):
    brain.reset()
    for text in ["open chrome and search lo-fi music", "now do the same on youtube"]:
        print(f"\n> {text}")
        show(brain, text)


def main():
    brain = Brain()
    while True:
        print("\n1) Chat in text mode")
        print("2) Run routing test set")
        print("3) Follow-up memory test")
        print("q) Quit")
        choice = input("> ").strip().lower()
        if choice == "1":
            chat(brain)
        elif choice == "2":
            run_tests(brain)
        elif choice == "3":
            memory_test(brain)
        elif choice == "q":
            break


if __name__ == "__main__":
    main()