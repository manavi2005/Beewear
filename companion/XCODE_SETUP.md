# Xcode setup — build the companion app and stream from a real Apple Watch

A copy-paste walkthrough from the Swift source files in this folder to a running app on your
iPhone + Apple Watch, streaming vitals into the Attune core. Takes ~15 minutes the first time.

> **Why there's no `.xcodeproj` to open:** a hand-authored project file is fragile and often
> won't open; creating it in Xcode takes 30 seconds and these files are organized to make that
> trivial (ADR-018). Follow the steps once and you're done.

**Two data paths — the iPhone path is the reliable one:**
- **iPhone app (do this first):** reads HR/HRV/sleep from the iPhone's Health store, which the
  Watch syncs to automatically. Most reliable; works even if the Watch's own networking is
  flaky.
- **Watch app (the cool live demo):** streams on-wrist heart rate during a session, posting
  straight from the wrist. More impressive, but watch→laptop networking can be finicky — get
  the iPhone path working first.

---

## 0. Prerequisites

- **Xcode 16+** installed (from the Mac App Store), opened once so it finishes installing
  components.
- An **Apple ID** added to Xcode: **Xcode ▸ Settings ▸ Accounts ▸ +** (a free account is fine
  for on-device testing).
- A **real iPhone and a paired Apple Watch** on the **same Wi-Fi as your Mac**. HealthKit and
  live heart rate do **not** work in the Simulator.
- The **core running** on your Mac (you'll start it in step 7):

```bash
cd core
python3 -m venv .venv && source .venv/bin/activate   # if you haven't already
pip install -e ".[dev]"
```

---

## 1. Create the iOS app project

1. **Xcode ▸ File ▸ New ▸ Project… ▸ iOS ▸ App ▸ Next.**
2. Set:
   - **Product Name:** `Attune`
   - **Team:** your Apple ID
   - **Organization Identifier:** something reverse-DNS, e.g. `com.yourname`
   - **Interface:** SwiftUI  ·  **Language:** Swift  ·  Storage: None  ·  leave tests unchecked
3. **Next**, and save it **outside** this repo (e.g. `~/Developer/Attune`) — you'll point it at
   these source files, not copy the repo into it.

Xcode generates `AttuneApp.swift` and `ContentView.swift`. **You'll replace both in step 3.**

---

## 2. Add the watchOS target

1. **File ▸ New ▸ Target… ▸ watchOS ▸ Watch App ▸ Next.**
2. Set **Product Name:** `AttuneWatch`, Interface **SwiftUI**, and make sure **"Embed in
   Companion Application"** is the `Attune` iOS app. Finish.
3. If Xcode asks to **"Activate the AttuneWatch scheme?"**, click **Activate**.

Xcode generates `AttuneWatchApp.swift` and a `ContentView.swift` inside the watch target —
**you'll replace these in step 3** too.

---

## 3. Add the source files (and delete the generated ones)

**First delete the four files Xcode generated** (right-click ▸ Delete ▸ *Move to Trash*), or
you'll get "Invalid redeclaration of 'AttuneApp'":
- the iOS target's `AttuneApp.swift` and `ContentView.swift`
- the watch target's `AttuneWatchApp.swift` and `ContentView.swift`

**Now add this folder's files.** In Finder, open `companion/` and drag the folders into the
Xcode Project navigator. In the dialog, tick **"Copy items if needed"** and **"Create groups"**,
then set **target membership** exactly:

| Drag this | Add to target(s) |
|---|---|
| `Shared/` (all 4 files) | **both** — `Attune` **and** `AttuneWatch Watch App` |
| `AttuneiOS/` (3 files) | `Attune` **only** |
| `AttuneWatch/` (3 files) | `AttuneWatch Watch App` **only** |

> To check membership later: select a file ▸ open the **File Inspector** (right panel) ▸
> **Target Membership**. The `Shared/*` files must have **both** boxes ticked. This is the #1
> cause of "Cannot find 'VitalSample' in scope" in the watch target.

---

## 4. Enable HealthKit (both targets)

For **each** target (`Attune`, then `AttuneWatch Watch App`):

1. Select the **project** in the navigator ▸ pick the target ▸ **Signing & Capabilities** tab.
2. **+ Capability** ▸ double-click **HealthKit**.
3. *(Optional, for background HR on the watch)* on the watch target add **Background Modes** and
   tick **Workout processing**. Not needed while the watch app is open in the foreground.

---

## 5. Add the Info keys (usage strings + allow local HTTP)

Still on each target, open the **Info** tab (next to Signing & Capabilities). Hover any row ▸
click **+** ▸ add these. (Type the friendly name; Xcode maps it to the raw key.)

**Both targets — Health permission strings (required or the app crashes on launch):**

| Key | Value (paste) |
|---|---|
| `Privacy - Health Share Usage Description` | `Attune reads your heart rate, HRV, respiratory rate and sleep to align them with your conversations for private self-coaching.` |
| `Privacy - Health Update Usage Description` | `Attune reads your health data; it does not write any.` |

**iOS target only — local network prompt string:**

| Key | Value (paste) |
|---|---|
| `Privacy - Local Network Usage Description` | `Attune sends your vitals to the Attune core running on your computer on your local network.` |

**Both targets — allow plain HTTP to your laptop (DEV ONLY).** The core serves `http://` on your
LAN, so add an **App Transport Security** exception:

1. Add key **`App Transport Security Settings`** (type: **Dictionary**).
2. Inside it add **`Allow Arbitrary Loads`** = **YES** (Boolean).
3. Inside it also add **`Allow Local Networking`** = **YES** (Boolean).

> Remove this before anything resembling production. If you prefer an `Info.plist` file, the
> equivalent XML is in the **Appendix** at the bottom.

---

## 6. Signing

For each target ▸ **Signing & Capabilities**:
- **Automatically manage signing** ✓
- **Team:** your Apple ID
- If you see a bundle-identifier error, make each unique (e.g. `com.yourname.Attune` and
  `com.yourname.Attune.watchkitapp`).

The **first** time you run on the phone, it'll say *"Untrusted Developer."* On the phone:
**Settings ▸ General ▸ VPN & Device Management ▸ [your Apple ID] ▸ Trust.**

---

## 7. Point the app at your Mac, then start the core

On your Mac, find the URL and start the server bound to the LAN:

```bash
cd core && source .venv/bin/activate
attune doctor                                   # prints your LAN URL, e.g. http://192.168.1.23:8000
ATTUNE_VITALS_SOURCE=api attune serve --lan     # receives pushes; prints the same URL
```

Put that URL into the app:
- **iPhone app:** just type it into the app's **backend URL field** and tap **Save URL**
  (persists on the phone). No code edit needed.
- **Watch app:** the watch can't share the phone's setting, so set the default in code — open
  `Shared/BackendConfig.swift` and change:
  ```swift
  static let defaultBaseURL = URL(string: "http://192.168.1.23:8000")!   // ← your LAN URL
  ```

> `127.0.0.1` on the phone/watch is the *device itself* — always use the Mac's LAN IP.

---

## 8. Run it

**iPhone first (reliable path):**
1. In Xcode's toolbar pick the **`Attune`** scheme and **your iPhone** as the destination ▸ **▶
   Run**.
2. On the phone, the **Health access** sheet appears — turn the categories **on** ▸ Allow.
3. Tap **Sync now** (or toggle **Live sync**). The status line shows how many samples were sent.

**Watch (live demo):**
1. Pick the **`AttuneWatch`** scheme and **your Apple Watch** ▸ **▶ Run**.
2. On the watch, allow Health access, then tap **Start** — your live BPM appears and streams.

**Watch it land, on your Mac:**
```bash
open http://127.0.0.1:8000/     # dashboard → click ● Live
# or:
attune run --vitals api         # prints the aligned moments + recommendations
```
With **Live** on, the BPM tile and heart-rate chart update the instant the Watch sends a reading
(Server-Sent Events, ADR-025).

For **real conversations too**, in another terminal: `bee login && bee proxy`, then add
`ATTUNE_CONVERSATION_SOURCE=bee` to `core/.env`. Otherwise conversations stay synthetic and only
the vitals are real.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| **"Invalid redeclaration of 'AttuneApp'"** (or `ContentView`) | You didn't delete Xcode's generated `AttuneApp.swift` / `ContentView.swift` (step 3). Move them to Trash. |
| **"Cannot find 'VitalSample' / 'AttuneClient' in scope"** in the watch | A `Shared/*` file isn't in the watch target. File Inspector ▸ Target Membership ▸ tick the watch box. |
| **App crashes immediately on launch** | Missing `NSHealthShareUsageDescription` (step 5). Add it to *that* target. |
| **Health sheet never appears** | Running on Simulator (use a real device), or HealthKit capability missing (step 4). |
| **"App Transport Security policy requires a secure connection"** | ATS exception missing (step 5). Add `Allow Arbitrary Loads` = YES to *that* target. |
| **"Could not connect to the server" from the device** | Wrong IP, phone/watch on a different Wi-Fi, or the server bound to 127.0.0.1 — start it with `attune serve --lan`. If macOS prompts to allow incoming connections for Python, click **Allow**. |
| **No live HR on the watch** | You must tap **Start** (it runs a workout session to get high-frequency HR). Simulator won't produce HR. Grant Health on the watch too. |
| **Watch posts fail but iPhone works** | Watch networking — keep the watch near the phone / on Wi-Fi. The iPhone path alone is enough to demo. |
| **"Untrusted Developer"** on first run | Phone ▸ Settings ▸ General ▸ VPN & Device Management ▸ trust your Apple ID. |

---

## Appendix — raw `Info.plist` values

If you'd rather manage a physical `Info.plist`, these are the keys from step 5:

```xml
<key>NSHealthShareUsageDescription</key>
<string>Attune reads your heart rate, HRV, respiratory rate and sleep to align them with your conversations for private self-coaching.</string>
<key>NSHealthUpdateUsageDescription</key>
<string>Attune reads your health data; it does not write any.</string>
<key>NSLocalNetworkUsageDescription</key>
<string>Attune sends your vitals to the Attune core running on your computer on your local network.</string>
<key>NSAppTransportSecurity</key>
<dict>
  <key>NSAllowsArbitraryLoads</key><true/>
  <key>NSAllowsLocalNetworking</key><true/>
</dict>
```

## Appendix — test the whole loop before any of this

You don't need the Watch (or even Xcode) to see the system work end to end:

```bash
ATTUNE_VITALS_SOURCE=api attune serve --lan   # terminal 1
attune simulate-watch                          # terminal 2 — streams fake Watch vitals
open http://127.0.0.1:8000/                     # dashboard → ● Live
```
