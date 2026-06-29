We want to create an automatic learning system during the ssd phase.

BLOKED BY ANOTHER INITIAIVE: The ssd and analysis phase phase needs to be mixed first into the same flow. All lexic refers to flows after merging is done.

In order to ensure our learning path works succesfully we need to figure out first:

Easy improvements:

- 1 Source of true need to colect the git commit if is in a git folder id so then you can later refer properly the evidence in the claims.
- 2 If i am not wrong. Source of true artifacts contain dates fields. But they are not being properly filled. This data may be relevant for no git folders, later may be used for merge source of true pipeline.
- 3 If the lerning was colected out of sync we should mark that somehow in order to make easier future merging for the source of true. (The PR may contains data already collected in source of true)

Complex improvements:

- 1 We need a way to merge source of true patch artifacs (knowledge-source/patches/pending to final folder). We need probably another pipeline that will be triggered trought slash command in the UI console. This pipeline will be in charge to resolve source of true conflicts, verify the evidences and if not clear, send ask to human request.
- 2 Source of true to local DB: We need a way to delete local db and migrate it from the source of true. We need a slash command but also as pipeline step: Pipeline must detect and show a selection menu that allow user to update or continue the run (as source of true is now in git. probably git ids comparasion should work). 
- 3 Source of true to humman learning files: Human needs better way to understand the ideas than the machines. Hummans needs readable files about the system, human needs to see the core concepts, how they relate, human needs diagrams, etc... This is actually a huge scope but we can start with one idea and progresively going to implement the rest of them. But we need at least one for this initiative.

With all the complex initiatives we can start somehow to measusre and figuere out how to proceed to improve the learning path.