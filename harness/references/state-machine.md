# State Machine Authority

Only the Python orchestrator and state machine select transitions. Workers cannot mutate state, mark work complete, choose another task, or alter retry limits.

