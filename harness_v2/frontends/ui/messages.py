"""MVU messages and effects for the v2 UI.

Both are pure data. ``Msg`` values flow into ``update`` (from the runtime reading
keys/lines, or from a ``Choice`` being activated). ``Effect`` values flow out of
``update`` and are the only thing the runtime is allowed to hand to the
controller — the single impure boundary. Nothing here performs I/O.
"""

from __future__ import annotations

from dataclasses import dataclass


# --- Messages: inputs to update ------------------------------------------------


@dataclass(frozen=True, slots=True)
class Key:
    key: str


@dataclass(frozen=True, slots=True)
class SubmitLine:
    text: str


@dataclass(frozen=True, slots=True)
class Navigate:
    screen_id: str
    context: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Invoke:
    command: str
    args: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Back:
    pass


@dataclass(frozen=True, slots=True)
class Home:
    pass


@dataclass(frozen=True, slots=True)
class Quit:
    pass


Msg = Key | SubmitLine | Navigate | Invoke | Back | Home | Quit


# --- Effects: outputs of update, performed via the controller ------------------


@dataclass(frozen=True, slots=True)
class Nothing:
    pass


@dataclass(frozen=True, slots=True)
class Select:
    run_id: str


@dataclass(frozen=True, slots=True)
class Start:
    root_bundle: str
    request: str


@dataclass(frozen=True, slots=True)
class RetryStep:
    step_id: str


@dataclass(frozen=True, slots=True)
class RetryBundle:
    bundle: str


@dataclass(frozen=True, slots=True)
class Cancel:
    pass


@dataclass(frozen=True, slots=True)
class Resume:
    pass


@dataclass(frozen=True, slots=True)
class Decision:
    response: str


@dataclass(frozen=True, slots=True)
class Refresh:
    pass


@dataclass(frozen=True, slots=True)
class Watch:
    timeout: float = 1.0


Effect = (
    Nothing
    | Select
    | Start
    | RetryStep
    | RetryBundle
    | Cancel
    | Resume
    | Decision
    | Refresh
    | Watch
)
