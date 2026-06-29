from ..contracts.enums import PhaseName

PHASES = (
    PhaseName.INITIALIZING,
    PhaseName.LOADING_KNOWLEDGE,
    PhaseName.DETECTING_INTENT,
    PhaseName.ROUTING,
    PhaseName.SELECTING_STRATEGY,
    PhaseName.EXPLORE,
    PhaseName.PURPOSE,
    PhaseName.SPEC,
    PhaseName.DESIGN,
    PhaseName.TASKS,
    PhaseName.TDD_LOOP,
    PhaseName.LEARNING,
    PhaseName.FINALIZING,
    PhaseName.SNAPSHOTTING,
    PhaseName.COMPLETED,
)
