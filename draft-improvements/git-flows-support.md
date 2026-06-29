One way to make better analysis output could be use the git and gitlab flows.

Both are main codebase stores that work with git.

Both support some kind of pypelines that allows you test system.

Ex, the current ci.yml

So the idea is:

- The harness will create a branch each time triggers the pipeline.
- We create templates for the ci ymls (create a copy like the one we current have)
- We include a slash bar to install ci that will install the last ci templates.
- Each run we ensure the last matches with THIS_REPO_URL last origin/main
- In case if some ci files already exist we show a no sync warning.
- In case empty ci folder and files we show no cli pipline is instaled warning.
- We detail something like: the info is colected by the pipeline to run test a lot of test. Not installing will reduce drasticaly the initial input and the decisions taken by the harness. We use this system to avoid you to install hell of packages in your computer not to collect info about you.