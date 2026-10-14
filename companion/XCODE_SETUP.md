# Xcode setup — build the companion app and stream from a real Apple Watch

From the Swift sources in this folder to the app running on your iPhone + Apple Watch. The
fiddly parts (creating targets, file membership, HealthKit capability, Info.plist keys, the ATS
exception) are all encoded in **`project.yml`**, so you generate a ready project with **one
command** — no manual target wiring.

> ✅ **Verified:** both targets build in Xcode 27, and the iOS app runs in the Simulator with
> HealthKit authorization working (the permission sheet shows Heart Rate, HRV, Wrist
> Temperature, Respiratory, Sleep — exactly what the code requests). What still needs *you*: a
> real Apple Watch for live HR (the Simulator has no sensors) and your Apple ID for signing to a
> physical device.

**Two data paths — the iPhone path is the reliable one:**
- **iPhone app:** reads HR/HRV/sleep from the iPhone's Health store (the Watch syncs to it
  automatically). Most reliable.
- **Watch app:** streams on-wrist heart rate during a session, straight from the wrist. More
  impressive, but watch→laptop networking can be finicky — get the iPhone path working first.

---

## 0. Prerequisites

- **Xcode 16+** (tested on 27), opened once so it finishes installing components.
- A real **iPhone + paired Apple Watch** on the **same Wi-Fi as your Mac** (HealthKit and live
  HR do **not** work in the Simulator).
- The **core** installed: `cd core && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.

---

## 1. Generate the Xcode project (one command)

```bash
brew install xcodegen          # one-time (https://github.com/yonaskolb/XcodeGen)
cd companion
xcodegen generate              # reads project.yml → Attune.xcodeproj
open Attune.xcodeproj
```

That's it — the generated project already has:
- **Two targets**, `Attune` (iOS) and `AttuneWatch` (watchOS), with all the Swift files added
  and the `Shared/` files in **both** targets.
- **HealthKit** capability on both targets.
- The **Info.plist usage strings** (`NSHealthShareUsageDescription`, local-network) and the
  **App Transport Security** exception that allows plain-HTTP to your Mac on the LAN.

> Re-run `xcodegen generate` any time you add a file or change `project.yml`. The generated
> `Attune.xcodeproj` and the per-target `Info.plist` / `*.entitlements` are gitignored — the
> source of truth is `project.yml`.

---

## 2. Signing (only needed for a real device)

The **Simulator runs with no team**. For a **real iPhone/Watch**, in Xcode select the project ▸
each target ▸ **Signing & Capabilities**:
- **Automatically manage signing** ✓  ·  **Team:** your Apple ID (add it in **Xcode ▸ Settings
  ▸ Accounts** if needed).
- If a bundle id collides, the defaults are `com.attune.hackathon.ios` and `…watch` — make them
  unique to you if Xcode complains.

First run on the phone shows *"Untrusted Developer"* → on the phone: **Settings ▸ General ▸ VPN
& Device Management ▸ [your Apple ID] ▸ Trust.**

---

## 3. Point the app at your Mac, then start the core

```bash
cd core && source .venv/bin/activate
attune doctor                                   # prints your LAN URL, e.g. http://192.168.1.23:8000
ATTUNE_VITALS_SOURCE=api attune serve --lan     # receives pushes; prints the same URL
```

- **iPhone app:** type that URL into the app's **backend URL field** and tap **Save URL**
  (persists on the phone). On the **Simulator**, use `http://127.0.0.1:8000` — the Simulator
  shares your Mac's network.
- **Watch app:** the watch can't read the phone's setting, so set the default in code — open
  `Shared/BackendConfig.swift` and set `defaultBaseURL` to your LAN URL, then regenerate /
  rebuild.

> `127.0.0.1` on a *real* phone/watch is the device itself — use the Mac's LAN IP there.

---

## 4. Run

**iPhone (reliable path):** pick the **`Attune`** scheme + your iPhone (or an iPhone Simulator)
▸ **▶ Run**. Allow Health access when the sheet appears, then tap **Sync now** (or toggle **Live
sync**). The status line shows how many samples were sent.

**Watch (live demo, real device):** pick the **`AttuneWatch`** scheme + your Apple Watch ▸ **▶
Run**. Allow Health, tap **Start** — live BPM streams to the core.

**Watch it land, on your Mac:**
```bash
open http://127.0.0.1:8000/     # dashboard → click ● Live (updates via SSE as samples arrive)
```

> **No Watch yet?** You can still see the whole system work — `attune simulate-watch` streams
> fake vitals into the dashboard (see the last appendix). The Simulator has no sensors, so the
> iOS app in the Simulator is for verifying the build/UI/permissions, not live vitals.

For real **conversations** too: in another terminal `bee login && bee proxy`, then set
`ATTUNE_CONVERSATION_SOURCE=bee` in `core/.env`. Otherwise conversations stay synthetic and only
the vitals are real.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| **`xcodegen: command not found`** | `brew install xcodegen` (step 1). |
| **"resource fork, Finder information, or similar detritus not allowed"** during signing | Your **DerivedData is in an iCloud-synced folder** (Desktop/Documents). This repo lives on the Desktop, so **don't** point DerivedData into it. Use Xcode's default: **Xcode ▸ Settings ▸ Locations ▸ Derived Data = Default** (it lives in `~/Library`, outside iCloud). |
| **"Signing requires a development team"** on a real device | Set your Team (step 2). The Simulator doesn't need one. |
| **App crashes immediately on launch** | Missing Health usage string — but `project.yml` sets it; make sure you ran `xcodegen generate` after any change. |
| **Health sheet never appears** | Running on Simulator with no prior data is fine (the sheet still appears on first request); on a device, ensure HealthKit capability is present (it is, via `project.yml`). |
| **"Could not connect to the server" from a device** | Wrong IP, phone/watch on a different Wi-Fi, or the server bound to 127.0.0.1 — start it with `attune serve --lan`. If macOS prompts to allow incoming connections for Python, click **Allow**. |
| **No live HR on the watch** | Tap **Start** (it runs a workout session for high-frequency HR). The Simulator won't produce HR — use a real Apple Watch. |
| **"Untrusted Developer"** on first run | Phone ▸ Settings ▸ General ▸ VPN & Device Management ▸ trust your Apple ID. |

---

## Appendix — what `project.yml` configures (so you don't have to)

Per target: the HealthKit entitlement (`com.apple.developer.healthkit`), these Info.plist keys,
and the ATS exception (**dev only** — remove before production):

```
NSHealthShareUsageDescription, NSHealthUpdateUsageDescription,
NSLocalNetworkUsageDescription (iOS),
NSAppTransportSecurity → { NSAllowsArbitraryLoads: YES, NSAllowsLocalNetworking: YES }
```

Prefer to build it by hand instead of XcodeGen? The equivalent manual steps (create targets, set
file membership, add the capability and these keys) are in this file's git history; XcodeGen just
automates them.

## Appendix — see the whole system work before touching Xcode

```bash
ATTUNE_VITALS_SOURCE=api attune serve --lan   # terminal 1
attune simulate-watch                          # terminal 2 — streams fake Watch vitals
open http://127.0.0.1:8000/                     # dashboard → ● Live
```
