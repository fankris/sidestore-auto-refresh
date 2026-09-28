# Issue #18 (Apple ID 503/429) and SideStore service-readiness failure

Investigation record. The earlier candidate was `64713a1b465749b6a06bd25b7b1198aad8fb596f`
(v3.0.2 line; v3.0.1 is frozen and untouched); it did not establish
resolution of Issue #18 on affected devices. A later client-identity finding
and source-level follow-up are documented below.
Historical CI: `livecontainer-build.yml` run `35450558929` — success.
https://github.com/NRG-Wardog/sidestore-auto-refresh/actions/runs/35450558929

The two investigations were kept separate: Issue #18 is an
authentication/networking problem; the service-readiness failure happens
before or while establishing the internal backend service. One is not used
to explain the other.

---

## Part A — Issue #18: Apple ID login 503/429

### Runtime path (traced in source, not inferred from SHAs)

Host 2FA/credential prompts → `authRespond` → parked `SignInOperation`
(`scripts/templates/v3_headless_runtime.swift`) →
`AuthManager.signIn(appleID:password:anisetteData:...)` →
`DeveloperPortalProxy.signIn` → GrandSlam `sendAuthenticationRequest`;
2FA (trusted-device / SMS / voice / code submission) →
`makeTwoFactorAuthRequest` senders. The v3 adapter implements only the
upstream `SignInHandler` / `AnisetteServerHandler` decision surface. There
is no second authentication stack: no GSA HTTP is implemented outside the
pinned SideSign sources.

### `Connection: close` proof in the final prepared build tree

CI test `test_gsa_connection_close_in_prepared_tree` executes against the
real prepared sources (`work/EmbeddedSideStore/Dependencies/SideSign`)
and asserts:

* exactly 2 occurrences of `"Connection": "close"` in
  `Sources/DeveloperPortal/Authentication.swift` at pinned SideSign
  `a731c0d5a9a6617c7b385ae493e07ffb7f81cd5d`,
* enclosed in `sendAuthenticationRequest` (initial credentials auth) and
  `makeTwoFactorAuthRequest` (all four 2FA send sites: trusted device,
  phone SMS/voice, code validation),
* exactly 2 `URLRequest(` builders in that file — no third GSA path,
* this is the unmodified pinned upstream baseline; the follow-up build adds
  one version-checked transform to `Authentication.swift` for the client-info
  token only, with replay/diff checks in CI.

The pinned ref is 16 commits ahead of the official fix
`35993d7f68950ce00d6bf1fd0fbcaa7bef51dc9c` ("close connection for gsa
after each call coz otherwise it triggers 5XX due to connection reuse")
and 0 behind. Developer-portal (post-auth) requests use a different host
and are unaffected by the GSA fix, as intended.

### 503 analysis — two distinct causes

The pinned upstream `Connection: close` fix addresses GSA connection reuse,
but it does not address a separate client-identity rejection. [AltStore PR
#1790](https://github.com/altstoreio/AltStore/pull/1790) and [Issue #8 in
Sank6/iCloud-Keychain-for-Linux](https://github.com/Sank6/iCloud-Keychain-for-Linux/issues/8)
report controlled requests where `X-MMe-Client-Info` containing
`com.apple.dt.Xcode` returned an HTML 503, while replacing that token with
`com.apple.akd/1.0` returned a valid GSA plist. These are third-party
observations, not an Apple policy statement; the AltStore PR is not merged.

The pinned SideSign builders pass `anisetteData.clientInfo` to the initial
GSA request and `a.clientInfo` to 2FA. The build now applies a version-checked,
fail-closed transform to those two header values only: if the sub-identity is
`com.apple.dt.Xcode[/version]`, it becomes `com.apple.akd/1.0`. Other client
identities, User-Agent, anisette fields, credentials and request bodies are
unchanged. This fixes the observed header condition in the prepared source;
physical login/2FA acceptance remains unverified. A 503 after this transform
still requires the actual stage and sanitized HTTP response details before
attributing it to a cause.

### 429 analysis

No uncontrolled retry exists in the v3 auth path: every submit is
user-driven, `V3AuthCenter` is single-flight (a new begin cancels the
previous session), the bridge mutation gate serializes concurrent auth
attempts, and poll loops are cheap reads. Upstream `authenticationLoop`
waits on `credentials()` (user-paced); nothing auto-resubmits. HTTP 429 and
GrandSlam throttling codes map to `rateLimited`, with guidance to wait before
trying again. The app intentionally does not add a retry/backoff request
that could amplify Apple's rate limit.

### Fixes made

* `[V3_AUTH]` / `[V3_OP]` console markers (session, kind, attempt,
  terminal stage/code only — never credentials, codes, tokens, headers).
* Build-time GSA client identity normalization for initial auth and 2FA,
  alongside upstream `Connection: close`; pinned-source and idempotence
  regression tests cover the request builders and token transformation.
* Prompt-kind closed set, single-flight and no-retry-loop regression
  tests (`GsaPreparedTreeTests`, wire-contract session tests, prompt-gate
  execution test).

---

## Part B — Service-readiness failure

Reported error:

```text
The SideStore process has not finished preparing its service.
Reconnect explicitly and reload authoritative status before repeating a mutation.
schema=1 operation=connect stage=serviceReadiness code=failed correlation=A7F4E80F-08D9-4ECC-BB63-096187EC29C3 underlying_domain=redacted underlying_code=1 retryable=unknown
```

### Root cause: structured errors were double-wrapped

`operation=connect` proves the failure happened pre-mutation. `redacted/1`
proves the underlying error was an already-structured `CombinedFailure`
bridged to `NSError` (unknown domain → `redacted`, Swift bridging code 1)
— i.e. the readiness probe's `serviceReadiness/timedOut` (or
`invalidResponse`) was rebuilt by `failed()` with default `code: .failed`,
destroying the original code, retryable flag and correlation. Fixed with
`CombinedFailure.preserving()`, which forwards structured failures
untouched; plain errors keep the previous behavior.

### Startup transition trace (verified in source)

`connect` → host container → storage preparation → bookmark creation →
LiveProcess/extension discovery → process launch (PID) → XPC accept →
`applicationReady` → 30s snapshot poll → `snapshot` /
`DatabaseManager.shared.isStarted` → terminal. The reported error reached
step 8/9: the snapshot never returned `ok` (most plausibly an unstarted
database, alternatively a malformed reply or process death — previously
indistinguishable, which is exactly what the fix addresses).

### Fixes made

* `failed()` preserves structured failures (same correlation ID).
* Correlated `[V3_SERVICE_START]` markers: launch begin/PID, XPC connect,
  application ready, snapshot ready, database-not-ready, malformed
  snapshot, timeout, process exit, start failure (stage/code).
* Probe captures the last snapshot error vocabulary for timeout/invalid
  reports. The 30s poll semantics are unchanged: a persistent database
  failure still terminates as retryable timeout, never false success.
* Verified reconnect safety: single attempt (`attemptID == nil` gate),
  waiters coalesce, late callbacks rejected by attempt guards, retire
  kills the failed process before replacement, no mutation precedes
  readiness (`v3RefreshToken` gate), retries replay nothing.

### Tests added

* Executable `test_shipped_failure_preservation` (timedOut/invalidResponse/
  notReady pass through; correlation kept; plain errors still wrapped).
* `ReadinessRegressionTests`: no-rewrap token, marker correlation,
  reconnect/mutation invariants.
* Existing suites untouched and green.

---

## Artifact (v3.0.2 candidate)

* Builder: `64713a1b465749b6a06bd25b7b1198aad8fb596f`
* LiveContainer `12377cf3b91d51739a33f14a302e5f522b238593`, SideStore
  `ff25922e5c13ccfafd83bda5092910d848ebd409`, SideSign `a731c0d`,
  minimuxer `98c3c79`
* IPA SHA-256:
  `F09A311E23DB06E89F625CFCBB07871EAADE6B38B3FF323CAC487BA661C05D54`
* Local: `C:\Users\Cyber_User\Downloads\LiveContainer-SideStore-v3.0.2-candidate.ipa`

## CI

* 164 repository tests OK (1 skipped); all new A/B tests executed.
* 512 layout measurements, 0 failures; builds + transport PASS.

## Device acceptance (honest split)

* Proven by source/tests/CI: fix presence in the prepared tree, error
  preservation, single-flight auth, reconnect safety, no auto-retry.
* Proven on maintainer device: sign-in works there (does not generalize).
* Still required: Issue #18 reproduction on affected accounts, and device
  console captures of `[V3_SERVICE_START]` / `[V3_AUTH]` markers during a
  real readiness/auth failure. Do not mark #18 fixed from this work.
