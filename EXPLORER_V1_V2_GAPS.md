# EXPLORE_BUNDLE v1 -> v2: funcionalidad pendiente

Fecha: 2026-07-02

## Modelo correcto

En v2 solo debe existir un `EXPLORE_BUNDLE`. La intencion de la migracion es correcta: aplanar el lio de v1 en el modelo:

- orquestador
- bundle
- phase
- executor `AI_WORKER` o `DETERMINISTIC_FUNCTION`

Este documento no propone crear otro `EXPLORER_BUNDLE`. Donde v1 tenia `explorer_intake`, `explorer_discovery`, `explorer_decision`, `explorer_artifact`, `explorer_review` y `explorer_distill`, en v2 esa funcionalidad debe estar absorbida por las fases actuales o nuevas fases del mismo `EXPLORE_BUNDLE`.

## Estado actual de v2

`EXPLORE_BUNDLE` ya esta declarado como bundle plano en `harness_v2/backend/domain/bundles/explore.py`:

- `EXPLORE_REQUEST_UNDERSTANDING`
- `EXPLORE_CONTEXT_PACK`
- `EXPLORE_EVIDENCE_DIGEST`
- `EXPLORE_EXPLORATION_MAP`
- `EXPLORE_OUTCOME_SYNTHESIS`
- `EXPLORE_HANDOFF`

Tambien hay mejoras reales respecto a v1:

- `exploration_map` es controller-owned/deterministico, no salida libre de IA.
- `explore_outcome_synthesis` no puede inyectar campos controller-owned como `evidence` o `exploration_map`.
- `artifact_delta_repair` generaliza la reparacion de JSON.
- `context_pack` centraliza request profile, decision history, CI/git, related improvements, repository observations y explorer scope.
- `handoff` de explore queda como artefacto unico `published/explore-handoff.json`.

Eso no lo cuento como perdida.

## Funcionalidad v1 que si parece perdida o incompleta

### 2. Context pack no construye related improvements ni repository observations

`EXPLORE_CONTEXT_PACK` lee opcionalmente:

- `explore/related_improvements.json`
- `explore/repository_observations.json`
- `explore/explorer_scope.json`

Pero no veo una fase deterministic function que los produzca. En v1, el explorer largo calculaba related improvements desde docs canonicos y repository observations desde el repo/request/intake.

Si esos artefactos no existen antes, v2 sigue adelante con listas vacias. Eso degrada discovery sin fallar.

Pendiente:

- decidir si `EXPLORE_CONTEXT_PACK` debe construirlos directamente;
- o anadir una phase deterministic previa dentro de `EXPLORE_BUNDLE`;
- o formalizar que otro componente los debe escribir antes y fallar si faltan para requests que los necesitan.

### 3. No hay duplicate search estructurado

V1 `explorer_discovery` tenia un bloque explicito:

- `searched_terms`
- `searched_surfaces`
- `matches`
- `no_match_claims`

En v2 el `evidence_digest` y `exploration_map` pueden representar evidencia y superficies, pero no conservan una prueba estructurada de "he buscado duplicados y no existe / existe este match".

Esto importa para evitar generar mejoras que ya existen o actualizar el artefacto equivocado.

Posible destino en v2:

- `explore/evidence_digest.json` como evidence kind `structure` o `knowledge` con source normalizada;
- o campo explicito en `explore/exploration_map.json`, por ejemplo `similar_functionality` ya existe pero ahora el builder lo emite vacio.

### 4. `existing_functionality` y `similar_functionality` salen vacios

`ExplorationMapBuilder.build()` devuelve:

- `"existing_functionality": []`
- `"similar_functionality": []`

En v1 el explorer podia terminar en `existing_functionality`, `duplicate_noop` o `update_existing` apoyandose en related improvements / duplicate search.

En v2 esos arrays existen en el contrato de mapa, pero no se rellenan. Esto parece funcionalidad pendiente, no simplificacion.

### 5. Faltan value gates equivalentes

V1 tenia una gate semantica para decisiones de valor:

- selected direction conocida;
- no seleccionar direcciones rechazadas por critic findings;
- `value_hypothesis`;
- `behavioral_delta`;
- `rejected_alternatives`;
- `counterevidence` o `falsifying_conditions`;
- `minimum_verification`;
- rechazo de cambios metadata-only/prose-only sin consumidor real.

En v2 no hay `explorer_decision` como fase separada, y eso esta bien si la decision queda absorbida. Pero no veo una validacion equivalente en `EXPLORE_OUTCOME_SYNTHESIS` ni en `EXPLORE_HANDOFF`.

Resultado: el outcome puede tener entries con `classification`, `title` y `evidence_refs`, pero sin justificar por que esa direccion tiene valor, que alternativas se descartaron, o como se falsaria.

### 6. Outcome entries son demasiado laxas para reemplazar el explorer largo

El schema de `outcome_synthesis` exige solo:

- `id`
- `classification`
- `title`
- `evidence_refs`

Permite additional properties en entries, pero no obliga a:

- problem;
- desired behavior / behavioral delta;
- rationale;
- rejected alternatives;
- counterevidence;
- minimum verification;
- update target/checksum;
- duplicate target;
- action create/update/no-op;
- artifact kind exacto.

Para SDD minimo puede bastar. Para reemplazar el explorer largo, falta contrato.

### 7. No hay mapping claro de outcomes no implementables

V1 tenia outcomes:

- `new_improvement`
- `split_bundle`
- `update_existing`
- `duplicate_noop`
- `existing_functionality`
- `limitation`
- `not_worth_it`
- `needs_user_decision`
- `escalate_discovery`

V2 `EXPLORE_BUNDLE` tiene `status` libre y `entries[*].classification`, pero no veo un mapping cerrado para estos casos.

Especialmente pendientes:

- `duplicate_noop`
- `existing_functionality`
- `limitation`
- `not_worth_it`
- `update_existing`

Si se reemplazan por classifications genericas, hace falta contrato y tests para que no acaben como trabajo de implementacion normal.

### 8. Decision de usuario solo cubre clarification

`EXPLORE_REQUEST_UNDERSTANDING` pide decision al usuario cuando hay `clarification_questions`.

Lo que no veo portado del explorer largo:

- decision de producto entre candidate directions;
- opcion `none_of_above`;
- reejecucion con refinement;
- decision con scores/ranked paths/option details;
- decision que escala a discovery gap si la respuesta invalida la direccion actual.

Puede que se haya simplificado intencionadamente para SDD, pero como funcionalidad del explorer largo esta perdida.

### 9. Review/distill desaparecen como gates de calidad

V1 hacia:

- artifact candidate;
- review contra intake/discovery/decision;
- repair si review pide cambios;
- distill para limpiar process residue;
- validacion post-distill.

V2 no genera artefacto markdown de improvement en `EXPLORE_BUNDLE`, asi que no necesita el mismo pipeline literal. Pero si `EXPLORE_BUNDLE` debe sustituir al explorer largo, falta una gate equivalente sobre `outcome_bundle`:

- detectar drift entre evidencia y entries;
- detectar entries demasiado genericas;
- detectar process residue o IDs internos en handoff humano;
- reparar synthesis cuando las entries no son implementables;
- validar que acceptance/minimum verification sea observable.

Ahora mismo la validacion es mas estructural que semantica.

### 10. No hay parser/normalizador de bundle actions

V1 podia interpretar un `explorer_bundle` con entries:

- create;
- update;
- no-op;
- documentation_task;
- limitation;
- existing_functionality.

En v2 no hace falta conservar el formato `explorer_bundle` si se considera legacy, pero si falta una estructura equivalente en `outcome_bundle`.

La funcionalidad perdida no es el nombre del formato, sino la capacidad de representar acciones distintas a "hay una entry para proposito/spec".

### 11. Publicacion especifica de explorer largo no esta absorbida

V1 publicaba/manifiestaba:

- `explorer/bundle.json`
- `published/explorer.json`
- `published/explorer-handoff.json`
- `published/explorer-knowledge-extraction.json`

V2 publica:

- `explore/outcome_bundle.json`
- `published/explore-handoff.json`

Eso esta bien como simplificacion si el nuevo handoff contiene todo lo necesario. Ahora mismo no veo absorbido:

- manifest de artifacts/primary artifact;
- suggested path para improvement/update;
- checksum para update;
- telemetry de knowledge extraction por entry;
- resultado de accepted/rejected evidence por entry.

### 12. Knowledge extraction por entry

V1 extraia conocimiento por entry y registraba fallos parciales:

- evidence accepted;
- evidence rejected;
- proposal path;
- failure code/message;
- source artifacts `explorer_artifact`, `explorer_decision`.

V2 tiene knowledge extraction generico despues de `EXPLORE_BUNDLE`, pero no veo equivalencia por entry ni telemetry comparable.

Si se acepta perder granularidad, bien. Si no, falta conectar `outcome_bundle.entries` con `KNOWLEDGE_EXTRACT_EXPLORE` de forma mas especifica.

## Cosas que no considero gap

No considero gap:

- Que no exista un segundo `EXPLORER_BUNDLE`.
- Que `explorer_intake/discovery/decision/artifact/review/distill` no existan con esos nombres.
- Que `exploration_map` sea deterministico.
- Que los delta repair sean genericos.
- Que `explore_outcome_synthesis` no pueda escribir evidence/map controller-owned.
- Que `EXPLORE_BUNDLE` sea el unico punto de entrada para discovery.

Eso son simplificaciones compatibles con v2.

## Orden recomendado, manteniendo un solo EXPLORE_BUNDLE

1. Portar contenido sustantivo de workers/prompts v1 a los workers actuales de `EXPLORE`, no como fases nuevas todavia.
2. Hacer que `EXPLORE_CONTEXT_PACK` produzca o exija `related_improvements` y `repository_observations` cuando sean relevantes.
3. Rellenar `existing_functionality` y `similar_functionality` en `exploration_map`.
4. Anadir duplicate search estructurado en `exploration_map` o `evidence_digest`.
5. Endurecer `outcome_synthesis.schema.json` / validators para entries de improvement, limitation, existing functionality, duplicate/no-op/update.
6. Anadir value gate en `EXPLORE_OUTCOME_SYNTHESIS` o `EXPLORE_HANDOFF`.
7. Mapear outcomes antiguos a status/classification/action nuevos y testearlos.
8. Extender decision service de `EXPLORE_BUNDLE` mas alla de clarification si se quiere conservar decision estrategica.
9. Anadir review semantico deterministic/AI del `outcome_bundle` si las gates de schema no bastan.
10. Conectar knowledge extraction generico con entries y telemetry por entry si esa granularidad sigue siendo deseada.

## Tests concretos que faltan

- Context pack no deja vacio `related_improvements` cuando hay docs canonicos relevantes.
- Context pack no deja vacio `repository_observations` para requests con paths/scope detectables.
- Exploration map rellena `similar_functionality` ante matches de duplicados.
- Exploration map rellena `existing_functionality` cuando evidencia demuestra que ya existe.
- Outcome bundle puede representar `limitation` sin pasar a implementation normal.
- Outcome bundle puede representar `existing_functionality` sin crear tareas de implementacion.
- Outcome bundle puede representar `duplicate_noop`.
- Outcome bundle puede representar `update_existing` con path/checksum.
- Value gate rechaza entries sin behavioral delta verificable.
- Value gate rechaza entries basadas solo en metadata/prosa sin consumidor.
- `needs_user_decision` estrategico pone el run en `WAITING_FOR_USER`, no solo clarification.
- Respuesta tipo `none_of_above` reinyecta refinement y regenera discovery/evidence.
- Knowledge extraction deja telemetry por entry cuando una entry no produce proposal.

## Conclusion

La migracion va en la direccion correcta: un solo `EXPLORE_BUNDLE`, fases planas y control ownership mas claro.

Lo pendiente no es recuperar la topologia de v1. Lo pendiente es asegurar que la funcionalidad util del explorer largo no se haya evaporado al aplanar: duplicate search, related/repository context real, outcomes no implementables, value gates, decision estrategica, normalizacion de actions, review semantico y telemetry de conocimiento por entry.
