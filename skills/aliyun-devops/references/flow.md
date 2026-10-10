# Flow pipelines with the official CLI

Discover pipeline operations and their required flags through `codeup devops`:

```text
codeup devops --help
codeup devops flow-list-pipelines --help
codeup devops flow-list-pipeline-runs --help
```

Find a pipeline by name, use the returned ID for details and run history, and follow the command's pagination flags. Prefer read-only `flow-list-*` and `flow-get-*` commands when inspecting status.

Starting, stopping, retrying, or otherwise changing a pipeline run can affect deployments. Before starting a run, show the pipeline and parameters and obtain explicit confirmation immediately before invoking the CLI command.
