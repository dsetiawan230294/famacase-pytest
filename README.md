# famacase-pytest

Drop-in **transport swap** for [`qase-pytest`][qase-pytest]. You keep writing
tests with the upstream `@qase.*` decorators and the upstream pytest plugin
\u2014 we just redirect the HTTP calls to the **Famacase Reporter Ingestion
API** instead of `qase.io`.

- Zero source-level changes to existing Qase test suites.
- Same wire format, same decorators, same markers, same BDD plugin.
- Switching back and forth between Qase and Famacase is a single env-var flip.

[qase-pytest]: https://github.com/qase-tms/qase-python

---

## 60-second migration

Already using `qase-pytest`? Three steps:

```bash
# 1. Install us alongside qase-pytest (we depend on it).
pip install famacase-pytest

# 2. Point at the Famacase backend.
export FAMACASE_API_URL=https://famacase.example.com
export FAMACASE_TESTOPS_API_TOKEN=rep_xxxxxxxxxxxxxxxx     # your reporter token
export FAMACASE_TESTOPS_PROJECT=SMOKE                       # your project code
export FAMACASE_MODE=testops

# 3. Run your existing tests \u2014 no code changes.
pytest
```

That's it. Your `@qase.title(...)`, `@qase.suite(...)`, `@qase.id(...)`
decorators still work; results land in Famacase.

---

## Sample test (vanilla qase decorators)

```python
# tests/test_login.py
from qase.pytest import qase

@qase.title("Login works")
@qase.suite("Smoke")
@qase.severity("critical")
def test_login_works():
    assert 1 + 1 == 2
```

Run it:

```bash
FAMACASE_API_URL=https://famacase.example.com \
FAMACASE_TESTOPS_API_TOKEN=rep_xxxxxxxxxxxxxxxx \
FAMACASE_TESTOPS_PROJECT=SMOKE \
FAMACASE_MODE=testops \
FAMACASE_TESTOPS_RUN_TITLE="Local smoke" \
FAMACASE_TESTOPS_RUN_COMPLETE=true \
pytest
```

You'll see the run link printed on completion:

```
[Qase][info] Famacase run link: https://famacase.example.com/runs/123
```

---

## Configuration

Anything that worked with `qase-pytest` works here \u2014 we accept
**both** `QASE_*` and `FAMACASE_*` env vars, and **both** `qase.config.json`
and `famacase.config.json` files. The `FAMACASE_*` form wins when both are
set on the same key.

### Env vars

| FAMACASE_* | QASE_* equivalent | Purpose |
|---|---|---|
| `FAMACASE_MODE` | `QASE_MODE` | `off` / `report` / `testops` |
| `FAMACASE_FALLBACK` | `QASE_FALLBACK` | Fallback mode if testops fails |
| `FAMACASE_DEBUG` | `QASE_DEBUG` | Verbose plugin logs |
| `FAMACASE_API_URL` | (no equivalent) | Famacase backend host. Overrides `testops.api.host` |
| `FAMACASE_REPORTER_TOKEN` | (no equivalent) | Project-scoped reporter token |
| `FAMACASE_TESTOPS_API_TOKEN` | `QASE_TESTOPS_API_TOKEN` | Same token, upstream-style name |
| `FAMACASE_TESTOPS_API_HOST` | `QASE_TESTOPS_API_HOST` | Same as `FAMACASE_API_URL` |
| `FAMACASE_TESTOPS_PROJECT` | `QASE_TESTOPS_PROJECT` | Project code |
| `FAMACASE_TESTOPS_PLAN_ID` | `QASE_TESTOPS_PLAN_ID` | Restrict run to a test plan |
| `FAMACASE_TESTOPS_RUN_ID` | `QASE_TESTOPS_RUN_ID` | Append to an existing run |
| `FAMACASE_TESTOPS_RUN_TITLE` | `QASE_TESTOPS_RUN_TITLE` | Run title |
| `FAMACASE_TESTOPS_RUN_DESCRIPTION` | `QASE_TESTOPS_RUN_DESCRIPTION` | Run description |
| `FAMACASE_TESTOPS_RUN_COMPLETE` | `QASE_TESTOPS_RUN_COMPLETE` | Auto-complete the run at session end |
| `FAMACASE_TESTOPS_RUN_TAGS` | `QASE_TESTOPS_RUN_TAGS` | Comma-separated run tags |
| `FAMACASE_TESTOPS_BATCH_SIZE` | `QASE_TESTOPS_BATCH_SIZE` | Result batch size |
| `FAMACASE_ENVIRONMENT` | `QASE_ENVIRONMENT` | Environment slug |
| `FAMACASE_ROOT_SUITE` | `QASE_ROOT_SUITE` | Root suite override |
| `FAMACASE_REPORT_DRIVER` | `QASE_REPORT_DRIVER` | Local report driver (when `mode=report`) |

Tuning knobs (no upstream equivalent):

| Env var | Default | Purpose |
|---|---|---|
| `FAMACASE_TIMEOUT` | `30` | HTTP timeout (seconds) |
| `FAMACASE_RETRY_ATTEMPTS` | `3` | Retries on transient {502,503,504}/connection errors |
| `FAMACASE_ATTACHMENT_WORKERS` | `4` | Threads for parallel attachment uploads |

### CLI flags

Every upstream `--qase-*` flag has a `--famacase-*` twin. Both are accepted;
the `--qase-*` version wins on conflict (so explicit per-invocation Qase
overrides keep working).

```bash
pytest --famacase-mode=testops --famacase-testops-project=SMOKE
# or equivalently
pytest --qase-mode=testops      --qase-testops-project=SMOKE
```

### `famacase.config.json`

Drop a `famacase.config.json` (or keep your existing `qase.config.json` \u2014
we read it as a fallback) next to where you invoke `pytest`:

```json
{
  "mode": "testops",
  "testops": {
    "api": {
      "host": "https://famacase.example.com",
      "token": "rep_xxxxxxxxxxxxxxxx"
    },
    "project": "SMOKE",
    "run": {
      "title": "Local smoke",
      "complete": true
    }
  }
}
```

---

## How it works

Internally we **monkey-patch** two upstream classes at plugin load time:

- `qase.commons.client.api_v2_client.ApiV2Client` \u2192 `FamacaseClient`
- `qase.commons.TestOpsPlanLoader` \u2192 `FamacasePlanLoader`

The `FamacaseClient` is a `BaseApiClient` subclass that speaks the Famacase
Reporter Ingestion API at `/api/v1/reporter/v1/*` (auth via
`Authorization: Token <raw>`). The wire payload schema is identical to
upstream's `Result` model, so every other piece of `qase-pytest` and
`qase-python-commons` stays unchanged.

Result of this design: **no fork, no maintenance drift**. Every fix or
feature in upstream `qase-pytest` is yours for free on the next pip
upgrade.

---

## Drop-in features inherited from `qase-pytest`

These all work unchanged because we only replace the HTTP transport:

- `@qase.id`, `@qase.title`, `@qase.suite`, `@qase.fields`, `@qase.author`,
  `@qase.description`, `@qase.preconditions`, `@qase.postconditions`,
  `@qase.severity`, `@qase.priority`, `@qase.layer`, `@qase.ignore`,
  `@qase.muted`, `@qase.attach`, `@qase.project_id`, etc.
- `qase.runtime.add_step(...)` / step trees
- BDD via `pytest-bdd`
- Parametrize handling and xfail/xpass mapping
- Local file reporter (`mode=report`)
- Profilers (`--qase-profilers=network,db,sleep`)
- Multi-project mode (`@qase.project_id`)

---

## Status mapping

Upstream `qase-pytest` maps pytest outcomes to status strings. Our backend
accepts both canonical names and upstream synonyms, so nothing has to be
translated client-side:

| Pytest outcome | qase string | Famacase canonical |
|---|---|---|
| pass | `passed` | `passed` |
| fail (assert) | `failed` | `failed` |
| fail (`pytest.fail(...)`) | `invalid` (BROKEN) | `invalid` |
| skip | `skipped` | `skipped` |
| `qase.muted()` block | `blocked` | `blocked` |

---

## Tests

```bash
# Unit tests (offline, mocked HTTP). No backend required.
PYTHONPATH=src python3 -m pytest tests_unit -v

# Live API regression. Requires the Famacase stack running on localhost:8000
# and the SMOKE project seeded (see tests/conftest.py).
python3 -m pytest tests -v

# E2E drop-in proof: spawns a pytest subprocess against `tests_e2e/sample_project/`
# using only vanilla qase decorators, then asserts the run + results landed
# in the backend via the reporter API. Requires the live stack.
PYTHONPATH=src python3 -m pytest tests_e2e -v
```

Full combined regression (unit + live + E2E): **79 tests, ~8 seconds.**

---

## License

Apache-2.0. Same license as upstream `qase-pytest` for ease of merging
fixes.
