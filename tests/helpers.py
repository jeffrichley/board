from board.run import Result


class FakeRun:
    """A runner that answers only the calls it was given, and records them.

    A key is the whole command, program first: ``("gh", "repo", "view")``,
    ``("tmux", "-V")``. Any other call fails the test.
    """

    def __init__(self, mapping: dict[tuple[str, ...], tuple[int, str, str]]):
        self.mapping = mapping
        self.calls: list[list[str]] = []
        self.captures: list[bool] = []

    def __call__(self, args: list[str], *, capture: bool = True) -> Result:
        self.calls.append(args)
        self.captures.append(capture)
        key = tuple(args)
        if key not in self.mapping:
            raise AssertionError(f"unexpected call {args}")
        return Result(*self.mapping[key])
