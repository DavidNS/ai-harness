BLOQUED BY: explorer improvements initiative. 

DESIGN phase needs to be smarter. With the new information provided by the EXPLORER should be now capable to detect better the user prompt comlexity.

Should estimate better the scope of the layers and complexity.

Should detect the priority of the tasks.

Should detect wich task can be done in parallel without cause conflicts in PR.

Should decide if split the user promt in several bundle initiaives that can be archived without conflicts in between.

Should detect if refactor in code is requied to improve code, should rank refactors into something like this:

0. NONE
   La feature encaja sin empeorar nada.

1. LOCAL_CLEANUP
   Pequeño cambio en el mismo archivo/módulo.
   Ej: if-else → hashmap.

2. STRUCTURAL_REFACTOR
   Cambia límites internos, extrae servicios, separa responsabilidades.

3. ARCHITECTURAL_CHANGE
   Cambia arquitectura global, contratos, storage, runtime, plugins, etc.

4. SEPARATE_INITIATIVE
   Es valioso, pero demasiado grande para mezclar con esta feature.