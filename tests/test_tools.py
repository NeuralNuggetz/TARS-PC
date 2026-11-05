"""Phase 7: test the real tools directly, no LLM and no voice.
Run from the project root:  uv run python -m tests.test_tools
"""
from tools import TOOLS
from tools._launch import APPS, find_app
from tools.apps import close_app, open_app
from tools.browser import open_website, search_in_browser
from tools.media import play_youtube
from tools.system import system_control


def show_installed():
    print("\nApp check:")
    for name in APPS:
        print(f"  {name:14} {find_app(name) or 'NOT FOUND'}")


def main():
    while True:
        print("\n1) Show which apps are found")
        print("2) Open an app")
        print("3) Browser search (Google / YouTube)")
        print("4) Open a website")
        print("5) System control (volume, screenshot, time...)")
        print("6) Play on YouTube (best_match / latest)")
        print("7) Close an app")
        print("q) Quit")
        choice = input("> ").strip().lower()
        if choice == "1":
            show_installed()
        elif choice == "2":
            name = input(f"App {list(APPS)}: ").strip()
            print(open_app.invoke({"app": name}))
        elif choice == "3":
            site = input("Site (google/youtube): ").strip() or "google"
            query = input("Query: ").strip()
            print(search_in_browser.invoke({"query": query, "site": site}))
        elif choice == "4":
            site = input("Site (youtube/github/google/gmail): ").strip()
            print(open_website.invoke({"site": site}))
        elif choice == "5":
            action = input("Action (volume_up/volume_down/mute/screenshot/time/date): ").strip()
            print(system_control.invoke({"action": action}))
        elif choice == "6":
            query = input("Song, video or channel: ").strip()
            which = input("best_match or latest (Enter = best_match): ").strip() or "best_match"
            print(play_youtube.invoke({"query": query, "which": which}))
        elif choice == "7":
            name = input(f"App {list(APPS)}: ").strip()
            force = input("Force close? (y/N): ").strip().lower() == "y"
            print(close_app.invoke({"app": name, "force": force}))
        elif choice == "q":
            break


if __name__ == "__main__":
    main()