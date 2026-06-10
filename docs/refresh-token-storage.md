# Bridge refresh-token storage at rest (audit fix 2.7b)

**Status**: Windows DPAPI shipped 2026-06-10; macOS/Linux keychain pending.

## Problem

The bridge persists its OIDC session (`BridgeStoredSession`, including the
**refresh token**) to `BridgeSession/bridge-session.json` for silent
session restore. It was plaintext JSON, so on a shared render box any local
user/process could read a long-lived credential and impersonate the artist.

## What shipped

`BridgeSessionStore` now writes a small envelope `{ Protected, Payload }`:

- **Windows**: `Payload` is the session JSON encrypted with **DPAPI**
  (`ProtectedData.Protect`, `DataProtectionScope.CurrentUser`) — only the
  same Windows user account can decrypt it. No new key material to manage.
- **macOS / Linux**: `Payload` is currently base64 of the plaintext JSON
  (`Protected=false`) — **no real protection yet**, same exposure as before
  but now explicitly flagged.
- Fail-closed: a `Protected=true` file loaded on a non-Windows platform (or
  a corrupt/foreign file) returns `null` → the artist simply re-logs in,
  rather than crashing or mis-reading.

Covered by `BridgeSessionStoreTests` (round-trip, Windows-no-plaintext,
corrupt→null, clear).

## Remaining work — macOS / Linux secure storage

DPAPI has no cross-platform equivalent; each OS needs its own backend.
Define an `IBridgeSecretProtector` with platform implementations selected at
startup, and route `BridgeSessionStore`'s protect/unprotect through it:

- **macOS**: Keychain Services. Either P/Invoke `Security.framework`
  (`SecItemAdd`/`SecItemCopyMatching`, `kSecClassGenericPassword`) or shell
  out to `/usr/bin/security add-generic-password` / `find-generic-password`.
  Store the session blob as a generic password under a stable service name
  (e.g. `com.omnibuscloud.bridge`).
- **Linux**: Secret Service API via libsecret (D-Bus). P/Invoke
  `libsecret-1` (`secret_password_store_sync` / `secret_password_lookup_sync`)
  with a schema, or shell out to `secret-tool store/lookup`. Headless boxes
  without a Secret Service daemon must degrade gracefully (keep the
  base64-plaintext fallback with a loud warning, or refuse persistence and
  require login each launch — operator's choice).

### Acceptance

- Refresh token never appears in plaintext in any on-disk file on any of the
  three platforms (the `SavedFileDoesNotContainRefreshTokenInPlaintext` test
  un-`Ignore`d for macOS/Linux).
- A session written on one machine/user cannot be read by another.

## Trigger

Before public artist distribution of the Blender addon (signing /
notarization is the gating milestone — same release). Windows is the
dominant artist platform and is covered now; macOS/Linux land with that
release.
