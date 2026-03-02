import math
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_RATING = 1500
K_FACTOR = 32
SURFACE_K = 0.3
SURFACES = ["hard", "clay", "grass", "indoor"]


@dataclass
class Player:
    name: str
    rating: float = DEFAULT_RATING
    surface_ratings: dict = field(default_factory=lambda: {s: DEFAULT_RATING for s in SURFACES})
    matches: int = 0
    wins: int = 0

    @property
    def win_rate(self):
        return self.wins / self.matches if self.matches else 0.0

    def __repr__(self):
        return f"Player({self.name}, overall={self.rating:.0f}, matches={self.matches})"


class TennisElo:
    """
    Tennis Elo rating model with surface-specific ratings.

    Usage:
        model = TennisElo()
        model.record_match("Alcaraz", "Djokovic", surface="clay")
        pred = model.predict("Sinner", "Medvedev", surface="hard")
        print(pred)
    """

    def __init__(self, k: float = K_FACTOR, surface_blend: float = SURFACE_K):
        self.players: dict[str, Player] = {}
        self.k = k
        self.surface_blend = surface_blend
        self.history: list[dict] = []

    def get_or_create(self, name: str) -> Player:
        if name not in self.players:
            self.players[name] = Player(name=name)
        return self.players[name]

    def _effective_rating(self, player: Player, surface: Optional[str]) -> float:
        if surface and surface in player.surface_ratings:
            return (
                (1 - self.surface_blend) * player.rating
                + self.surface_blend * player.surface_ratings[surface]
            )
        return player.rating

    def expected_score(self, ra: float, rb: float) -> float:
        return 1.0 / (1.0 + 10 ** ((rb - ra) / 400))

    def predict(self, player_a: str, player_b: str, surface: Optional[str] = None) -> dict:
        """Return win probabilities without modifying ratings."""
        a = self.get_or_create(player_a)
        b = self.get_or_create(player_b)
        ra = self._effective_rating(a, surface)
        rb = self._effective_rating(b, surface)
        p_a = self.expected_score(ra, rb)
        return {
            "player_a": player_a,
            "player_b": player_b,
            "surface": surface,
            "rating_a": round(ra, 1),
            "rating_b": round(rb, 1),
            "p_a_wins": round(p_a, 4),
            "p_b_wins": round(1 - p_a, 4),
            "favourite": player_a if p_a >= 0.5 else player_b,
        }

    def record_match(self, winner: str, loser: str, surface: Optional[str] = None) -> dict:
        """Update ratings from a completed match. Returns delta info."""
        a = self.get_or_create(winner)
        b = self.get_or_create(loser)
        ra = self._effective_rating(a, surface)
        rb = self._effective_rating(b, surface)
        p_a = self.expected_score(ra, rb)

        # Dynamic K: faster learning for new players
        k_a = self.k * (1.5 if a.matches < 20 else 1.0)
        k_b = self.k * (1.5 if b.matches < 20 else 1.0)
        d_a = k_a * (1 - p_a)
        d_b = k_b * (0 - (1 - p_a))

        a.rating += d_a
        b.rating += d_b
        if surface and surface in SURFACES:
            a.surface_ratings[surface] += d_a
            b.surface_ratings[surface] += d_b

        a.matches += 1; a.wins += 1
        b.matches += 1

        entry = {
            "winner": winner, "loser": loser, "surface": surface,
            "delta": round(d_a, 2),
            "new_rating_winner": round(a.rating, 1),
            "new_rating_loser": round(b.rating, 1),
            "upset": p_a < 0.5,
        }
        self.history.append(entry)
        return entry

    def leaderboard(self, top_n: int = 10) -> list:
        return sorted(self.players.values(), key=lambda p: p.rating, reverse=True)[:top_n]

    def accuracy(self) -> dict:
        if not self.history:
            return {"accuracy": None, "n": 0}
        correct = sum(1 for h in self.history if not h["upset"])
        return {
            "correct": correct,
            "total": len(self.history),
            "accuracy": round(correct / len(self.history), 4),
            "upsets": len(self.history) - correct,
        }

    def seed_player(self, name: str, rating: float):
        """Set initial rating for a known player."""
        p = self.get_or_create(name)
        p.rating = rating
        for s in SURFACES:
            p.surface_ratings[s] = rating


if __name__ == "__main__":
    model = TennisElo(k=32)
    seeds = [
        ("Djokovic", 2100), ("Alcaraz", 2050), ("Sinner", 2030),
        ("Medvedev", 1980), ("Zverev", 1960), ("Rublev", 1900),
        ("Tsitsipas", 1890), ("Fritz", 1850), ("De Minaur", 1830), ("Hurkacz", 1820),
    ]
    for name, r in seeds:
        model.seed_player(name, float(r))

    schedule = [
        ("Alcaraz", "Fritz", "clay"), ("Sinner", "Rublev", "hard"),
        ("Djokovic", "Tsitsipas", "grass"), ("Medvedev", "Hurkacz", "hard"),
        ("Fritz", "Sinner", "hard"), ("Alcaraz", "Djokovic", "clay"),
        ("De Minaur", "Zverev", "hard"), ("Rublev", "Tsitsipas", "clay"),
        ("Sinner", "Djokovic", "hard"), ("Alcaraz", "Medvedev", "grass"),
    ]

    for w, l, s in schedule:
        model.record_match(w, l, s)

    print("Leaderboard:")
    for i, p in enumerate(model.leaderboard(), 1):
        print(f"  {i}. {p.name:<14} {p.rating:.0f}")
    print()
    print("Accuracy:", model.accuracy())
