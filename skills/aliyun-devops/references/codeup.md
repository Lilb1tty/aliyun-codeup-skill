# Codeup with the official CLI

Use `codeup devops` to run the official Alibaba CLI. Discover the exact operation and flags with:

```text
codeup devops --help
codeup devops codeup-list-repositories --help
```

Common read workflows include repository listing/details, branches, commits, and merge request listing/details. Use the corresponding `codeup-list-*` and `codeup-get-*` plugin commands, and resolve repository names or paths to IDs before requesting details.

Branch creation, file changes, comments, merge requests, and repository settings change shared state. Inspect the operation help, summarize the target and change, then get confirmation before running it. Do not delete repositories.
