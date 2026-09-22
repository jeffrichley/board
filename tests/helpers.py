from dataclasses import dataclass


@dataclass
class Reply:
    returncode: int
    stdout: str
    stderr: str


class FakeRun:
    """A gh runner that answers only the calls it was given, and records them."""

    def __init__(self, mapping: dict[tuple[str, ...], tuple[int, str, str]]):
        self.mapping = mapping
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> Reply:
        self.calls.append(args)
        key = tuple(args)
        if key not in self.mapping:
            raise AssertionError(f"unexpected call {args}")
        return Reply(*self.mapping[key])
