# Project Control

## Sources of truth

VitaminBot uses two authoritative systems with distinct responsibilities:

- **Linear** is the source of truth for assignment/control, issue status, scope, blockers, dependencies, gates, and exit criteria.
- **GitHub** is the source of truth for code, branches, commits, pull requests, CI, and releases.

Repository documentation may summarize governance, but it does not override the current live state in Linear or GitHub.

## Engineering workflow

1. An engineer starts only an issue explicitly placed in **Needs Assignment** for that engineer's lane.
2. Before implementation, the engineer re-fetches the issue, blockers/dependencies, and current repository state.
3. The issue is moved to **In Progress**.
4. Work is performed on an issue-scoped branch. No feature implementation is committed directly to `main`.
5. Tests and relevant documentation are part of the issue scope.
6. A pull request is opened with the Linear identifier in its title.
7. CI must complete successfully.
8. The issue is moved to **In Review**.
9. The implementation engineer stops. Project Control performs independent review, merge, and the final **Done** transition.

## Branch and pull request convention

Engineer 1 branches follow:

```text
eng1/<LINEAR-ID>-<slug>
```

Pull request titles include the Linear identifier, for example:

```text
KIR-108 Bootstrap Python project and baseline CI
```

## Safety-critical boundary

Engineering implementation does not create scientific norms, dosage rules, safety thresholds, or medical constants by inference. Safety-critical changes must be tied to explicitly governed source material and must fail closed when required data or applicability is missing.
