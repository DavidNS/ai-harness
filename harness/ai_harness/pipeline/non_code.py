from ..contracts.enums import PhaseName

PHASES = (
    PhaseName.INITIALIZING,
    PhaseName.LOADING_KNOWLEDGE,
    PhaseName.DETECTING_INTENT,
    PhaseName.ROUTING,
    PhaseName.SELECTING_STRATEGY,
    PhaseName.NON_CODE_STUB,
    PhaseName.FINALIZING,
    PhaseName.SNAPSHOTTING,
    PhaseName.COMPLETED,
)
