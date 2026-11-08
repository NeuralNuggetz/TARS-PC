"""On-screen TARS overlay.

The assistant talks to the UI through four methods (set_state, show_text,
collapse, quit). NullUi has the same methods and does nothing, so the assistant
runs unchanged with the GUI turned off.
"""


class NullUi:
    def set_state(self, state: str):
        pass

    def show_text(self, title: str, text: str):
        pass

    def collapse(self):
        pass

    def quit(self):
        pass