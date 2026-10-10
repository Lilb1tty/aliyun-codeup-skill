# Projects and work items with the official CLI

Use the official plugin's `projex-*` commands through `codeup devops`. Discover supported operations and arguments with:

```text
codeup devops --help
codeup devops projex-search-projects --help
codeup devops projex-search-workitems --help
```

Search projects and work items before requesting details. Use returned IDs with the matching `projex-get-*` or other documented command, and honor the command's pagination options. Fetch work item type and field metadata when needed before creating or updating an item.

Creating, updating, deleting, associating, or commenting on work items changes shared state. Explain the target and effect and get confirmation before performing a write. Never delete projects.
