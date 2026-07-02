"""Pure bundle traversal helpers for v2 lifecycle declarations."""

from __future__ import annotations

from harness_v2.backend.domain.errors import DomainValidationError, InvalidTransitionError
from harness_v2.backend.domain.lifecycle import (
    BundleName,
    BundleRef,
    ExecutableStep,
    PhaseName,
    PhaseRef,
    TerminalState,
    bundle_spec,
    phase_spec,
)


def linearize_bundle(root_bundle: BundleName | str) -> tuple[ExecutableStep, ...]:
    root = BundleName(root_bundle)
    steps: list[ExecutableStep] = []
    counter = 0

    def visit(bundle: BundleName, path: tuple[BundleName, ...]) -> None:
        nonlocal counter
        for child in bundle_spec(bundle).children:
            if isinstance(child, BundleRef):
                visit(child.name, (*path, child.name))
            elif isinstance(child, PhaseRef):
                steps.append(
                    ExecutableStep(
                        step_id=f"{root.value}:{counter + 1:03d}",
                        step_index=counter,
                        root_bundle=root,
                        bundle_path=path,
                        bundle_name=path[-1],
                        phase=phase_spec(child.name),
                    )
                )
                counter += 1
            else:
                raise DomainValidationError(f"unsupported bundle child: {type(child).__name__}")

    visit(root, (root,))
    if not steps:
        raise DomainValidationError(f"root bundle {root.value} has no executable phases")
    return tuple(steps)


def step_ids(root_bundle: BundleName | str) -> tuple[str, ...]:
    return tuple(step.step_id for step in linearize_bundle(root_bundle))


def phases(root_bundle: BundleName | str) -> tuple[PhaseName, ...]:
    return tuple(step.phase_name for step in linearize_bundle(root_bundle))


def start_step(root_bundle: BundleName | str) -> ExecutableStep:
    return linearize_bundle(root_bundle)[0]


def step_for_step_id(root_bundle: BundleName | str, step_id: str) -> ExecutableStep:
    normalized = str(step_id)
    for step in linearize_bundle(root_bundle):
        if step.step_id == normalized:
            return step
    raise InvalidTransitionError(f"{normalized} is not in {BundleName(root_bundle).value} bundle")


def step_for_phase(root_bundle: BundleName | str, phase: PhaseName | str, *, occurrence: int = 0) -> ExecutableStep:
    normalized = PhaseName(phase)
    matches = [step for step in linearize_bundle(root_bundle) if step.phase_name is normalized]
    if occurrence < 0 or occurrence >= len(matches):
        raise InvalidTransitionError(f"{normalized.value} is not in {BundleName(root_bundle).value} bundle")
    return matches[occurrence]


def parent_bundle(root_bundle: BundleName | str, step_or_phase: str | PhaseName) -> BundleName:
    return _step_from_identifier(root_bundle, step_or_phase).bundle_name


def next_after(root_bundle: BundleName | str, current: str | PhaseName) -> ExecutableStep | TerminalState:
    steps = linearize_bundle(root_bundle)
    current_step = _step_from_identifier(root_bundle, current)
    index = current_step.step_index
    if index == len(steps) - 1:
        return TerminalState.COMPLETED
    return steps[index + 1]


def completed_prefix_before(root_bundle: BundleName | str, step_or_phase: str | PhaseName) -> tuple[str, ...]:
    current_step = _step_from_identifier(root_bundle, step_or_phase)
    return tuple(step.step_id for step in linearize_bundle(root_bundle)[: current_step.step_index])


def step_ids_from(root_bundle: BundleName | str, step_or_phase: str | PhaseName) -> tuple[str, ...]:
    current_step = _step_from_identifier(root_bundle, step_or_phase)
    return tuple(step.step_id for step in linearize_bundle(root_bundle)[current_step.step_index :])


def completed_bundles(root_bundle: BundleName | str, completed_step_ids: tuple[str, ...] | tuple[PhaseName, ...]) -> tuple[BundleName, ...]:
    root = BundleName(root_bundle)
    completed = _normalize_completed_steps(root, completed_step_ids)
    completed_bundles: list[BundleName] = []
    completed_set = set(completed)
    all_steps = linearize_bundle(root)
    for bundle in _bundle_postorder(root):
        bundle_steps = tuple(step.step_id for step in all_steps if step.bundle_name is bundle)
        if bundle_steps and all(step_id in completed_set for step_id in bundle_steps):
            completed_bundles.append(bundle)
    return tuple(completed_bundles)


def validate_completed_prefix(root_bundle: BundleName | str, completed_step_ids: tuple[str, ...] | tuple[PhaseName, ...]) -> None:
    normalized = _normalize_completed_steps(BundleName(root_bundle), completed_step_ids)
    expected = step_ids(root_bundle)[: len(normalized)]
    if tuple(normalized) != expected:
        raise DomainValidationError("completed steps must be an ordered prefix of the root bundle")


def _step_from_identifier(root_bundle: BundleName | str, identifier: str | PhaseName) -> ExecutableStep:
    if isinstance(identifier, PhaseName):
        return step_for_phase(root_bundle, identifier)
    text = str(identifier)
    if ":" in text:
        return step_for_step_id(root_bundle, text)
    return step_for_phase(root_bundle, text)


def _normalize_completed_steps(root_bundle: BundleName, completed_items: tuple[str, ...] | tuple[PhaseName, ...]) -> tuple[str, ...]:
    steps = linearize_bundle(root_bundle)
    normalized: list[str] = []
    start_index = 0
    for item in completed_items:
        if isinstance(item, PhaseName):
            phase = item
        else:
            text = str(item)
            if ":" in text:
                step = step_for_step_id(root_bundle, text)
                normalized.append(step.step_id)
                start_index = step.step_index + 1
                continue
            phase = PhaseName(text)
        for step in steps[start_index:]:
            if step.phase_name is phase:
                normalized.append(step.step_id)
                start_index = step.step_index + 1
                break
        else:
            raise DomainValidationError(f"{phase.value} is not in {root_bundle.value} bundle")
    return tuple(normalized)


def _bundle_postorder(root: BundleName) -> tuple[BundleName, ...]:
    values: list[BundleName] = []

    def visit(bundle: BundleName) -> None:
        for child in bundle_spec(bundle).children:
            if isinstance(child, BundleRef):
                visit(child.name)
        values.append(bundle)

    visit(root)
    return tuple(values)
