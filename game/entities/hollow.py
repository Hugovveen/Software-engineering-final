"""Hollow enemy — removed from the game.

Stub kept so existing imports don't break during cleanup.
"""


class Hollow:
    """Placeholder — Hollow has been removed from the game."""

    def __init__(self, **kwargs):
        self.x = 0.0
        self.y = 0.0

    def update(self, **kwargs):
        return []

    def to_dict(self):
        return {"type": "hollow", "effects": []}

    def redirect(self, *args):
        pass

    def group_redirect(self, *args):
        return False

    def get_effects(self, *args):
        return []
