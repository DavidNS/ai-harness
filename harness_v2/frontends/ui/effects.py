"""The single impure boundary: run an Effect through the controller.

``update`` decides *what* side effect should happen and returns it as a data
``Effect``. ``perform`` is the only place that turns that into a controller call
(which is itself the only layer that talks to the daemon) and folds the result
back into the model. Keeping this apart is what makes update/screens/renderer
pure and testable.
"""

from __future__ import annotations

from harness_v2.frontends.ui import messages as m
from harness_v2.frontends.ui.controller import UiController
from harness_v2.frontends.ui.state import UiState


def perform(effect: m.Effect, controller: UiController, state: UiState) -> UiState:
    if isinstance(effect, m.Nothing):
        return state
    if isinstance(effect, m.Select):
        return controller.select(state, effect.run_id)
    if isinstance(effect, m.Start):
        return controller.start(state, effect.request, root_bundle=effect.root_bundle)
    if isinstance(effect, m.Resume):
        return controller.resume(state)
    if isinstance(effect, m.Cancel):
        return controller.cancel(state)
    if isinstance(effect, m.RetryStep):
        return controller.retry(state, effect.step_id)
    if isinstance(effect, m.RetryBundle):
        return controller.retry_bundle(state, effect.bundle)
    if isinstance(effect, m.Decision):
        return controller.submit_decision(state, effect.response)
    if isinstance(effect, m.Refresh):
        return controller.refresh(state)
    if isinstance(effect, m.Watch):
        return controller.refresh(controller.poll_events(state, timeout=effect.timeout))
    return state
