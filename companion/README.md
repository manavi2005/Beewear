# Attune companion app (watchOS + iOS)

A thin Swift app that reads **Apple Watch** vitals from HealthKit and POSTs them to the
Attune core's `/ingest/vitals` endpoint (ADR-006/009). All intelligence lives in the core;
this app only *moves data*.

> ### ▶ Building it? `brew install xcodegen && cd companion && xcodegen generate && open Attune.xcodeproj`
> `project.yml` encodes both targets, file membership, HealthKit capability, Info.plist keys and
> the ATS exception, so one command gives you a ready project (verified building in Xcode 27 with
> the iOS app + HealthKit running in the Simulator). Full details, signing, and troubleshooting
> in **[XCODE_SETUP.md](XCODE_SETUP.md)**. The sections below are background on what each file does.

> **Why source files + a setup guide instead of a ready `.xcodeproj`?** See ADR-018 in
> [`../docs/DECISIONS.md`](../docs/DECISIONS.md). A hand-authored `project.pbxproj` is
> fragile and often won't open; the reliable path is to create the project in Xcode (30
> seconds) and add these files. They're organized so that's trivial.

## What each piece does

```
Shared/            ← add to BOTH targets' membership
  VitalSample.swift      Codable wire model — mirrors the core's canonical VitalSample
  AttuneClient.swift     async URLSession POST to /ingest/vitals
  BackendConfig.swift    where the core is reachable (edit this!)
  HealthKitSupport.swift HealthKit ↔ canonical mapping + read-type set
AttuneiOS/         ← iOS app target
  AttuneApp.swift        @main entry
  ContentView.swift      SwiftUI: set backend URL, authorize, Sync now / Live sync
  HealthKitService.swift pulls HR/HRV/respiratory/sleep (incl. Watch data synced to iPhone)
AttuneWatch/       ← watchOS app target
  AttuneWatchApp.swift   @main entry
  WatchContentView.swift live BPM + Start/Stop
  WorkoutHeartRateReader.swift  HKWorkoutSession → live HR → POST from the wrist
```

**Two complementary data paths** (either satisfies the vitals pipeline):
- **iPhone app** pulls recent HR/HRV/respiratory/sleep. The Watch syncs these to the
  iPhone's Health store automatically, so this is the simplest reliable path.
- **Watch app** streams *live* on-wrist heart rate during a session — the most "real-time"
  demo moment.

## Xcode setup (once)

1. **Create the project.** Xcode → New → Project → **iOS App** (SwiftUI, Swift). Name it
   `Attune`. Then File → New → Target → **Watch App** (for the existing iOS app), name it
   `Attune Watch`. You now have an iOS target and a watchOS target.
2. **Add the source files.** Drag the `Shared/`, `AttuneiOS/`, `AttuneWatch/` folders into
   the project. For each file in `Shared/`, tick **both** targets under *Target Membership*;
   put `AttuneiOS/*` in the iOS target only and `AttuneWatch/*` in the watch target only.
   Delete Xcode's auto-generated `ContentView`/`App` files that clash.
3. **Enable HealthKit.** Select the project → each target → *Signing & Capabilities* → **+
   Capability → HealthKit**. (Optional: tick *Background Delivery* on iOS for live updates
   when backgrounded.) This writes the `com.apple.developer.healthkit` entitlement.
4. **Add Info.plist keys** (both targets — Target → Info, or edit Info.plist):
   - `NSHealthShareUsageDescription` → "Attune reads your heart rate, HRV, respiratory rate,
     and sleep to align them with your conversations for private self-coaching."
   - `NSHealthUpdateUsageDescription` → same text (Xcode sometimes requires it even for
     read-only).
   - `NSLocalNetworkUsageDescription` → "Attune sends your vitals to the Attune core running
     on your computer on your local network."
5. **Allow HTTP to your laptop (dev only).** The core serves plain HTTP on your LAN, so add
   App Transport Security exceptions in Info.plist. Simplest for a hackathon:
   ```xml
   <key>NSAppTransportSecurity</key>
   <dict>
     <key>NSAllowsLocalNetworking</key> <true/>
     <key>NSAllowsArbitraryLoads</key> <true/>
   </dict>
   ```
   (Tighten or remove before anything resembling production.)
6. **Signing.** Set your Apple ID team on both targets. HealthKit + real sensors require
   **real devices** (a paired iPhone + Apple Watch); the Simulator has no live Watch data and
   can't run a workout session.
7. **Point the app at the core.** Edit `Shared/BackendConfig.swift` → `defaultBaseURL` to your
   laptop's LAN IP, or set it in the iOS app's text field at runtime. Find the IP with:
   ```bash
   ipconfig getifaddr en0
   ```

## Run the end-to-end demo

```bash
# 1. On your laptop — start the core in "receive vitals from the app" mode:
cd ../core
source .venv/bin/activate
echo "ATTUNE_VITALS_SOURCE=api"   >> .env     # read vitals the app pushes (ADR-009)
echo "ATTUNE_CONVERSATION_SOURCE=bee" >> .env  # or leave as synthetic to test the app alone
attune serve --host 0.0.0.0                   # bind so phone/watch can reach it on the LAN
```

```
# 2. On the devices (same Wi-Fi as the laptop):
#    • iPhone: open Attune → Request access → set URL → "Sync now" or toggle "Live sync".
#    • Watch:  open Attune → Start → watch BPM stream to the core.
```

```bash
# 3. Back on the laptop — run the pipeline over what arrived:
attune run --vitals api
```

You should see the vitals you just streamed show up in the aligned moments. Combine with a
real `bee proxy` (see `../core/README.md`) to align them against actual conversations.

## Notes & gotchas

- **Simulator limits:** HealthKit reads work against sample data you add in the Simulator's
  Health app, but live workout HR needs a physical Apple Watch.
- **LAN only:** phone/watch and laptop must share a network; `127.0.0.1` on the device is the
  device itself — always use the laptop's LAN IP (ADR-009, `BackendConfig`).
- **Privacy:** vitals go only to *your* core at the URL you set (default `127.0.0.1`-family /
  your LAN), never to us (ETHICS: local-first).
