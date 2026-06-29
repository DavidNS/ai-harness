from ..contracts.enums import PhaseName

PHASES = (
    PhaseName.INITIALIZING,
    PhaseName.LOADING_KNOWLEDGE,
    PhaseName.DETECTING_INTENT,
    PhaseName.ROUTING,
    PhaseName.SELECTING_STRATEGY,
    PhaseName.EXPLORER_INTAKE,
    PhaseName.EXPLORER_DISCOVERY,
    PhaseName.EXPLORER_DECISION,
    PhaseName.EXPLORER_ARTIFACT,
    PhaseName.EXPLORER_REVIEW,
    PhaseName.FINALIZING,
    PhaseName.SNAPSHOTTING,
    PhaseName.COMPLETED,
)
