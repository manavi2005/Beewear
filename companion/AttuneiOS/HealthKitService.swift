import Foundation
import HealthKit

/// iOS-side HealthKit reader. The iPhone's HealthKit store already contains the Apple Watch's
/// heart rate, HRV, respiratory rate, and sleep samples (they sync automatically), so the
/// phone is the simplest reliable place to pull and forward them (ADR-006).
///
/// Two modes:
///   • `syncRecent(minutes:)` — one-shot pull of the last N minutes (the "Sync now" button).
///   • `startLiveSync()`      — HKAnchoredObjectQuery per type for incremental live updates.
@MainActor
final class HealthKitService: ObservableObject {
    @Published var lastStatus: String = "Idle"
    @Published var isAuthorized = false

    private let store = HKHealthStore()
    private var anchors: [HKSampleType: HKQueryAnchor] = [:]
    private var liveQueries: [HKQuery] = []

    var client = AttuneClient(baseURL: BackendConfig.baseURL)

    // MARK: Authorization

    func requestAuthorization() async {
        guard HKHealthStore.isHealthDataAvailable() else {
            lastStatus = "HealthKit unavailable on this device"
            return
        }
        do {
            try await store.requestAuthorization(toShare: [], read: HealthKitSupport.readTypes)
            isAuthorized = true
            lastStatus = "Authorized"
        } catch {
            lastStatus = "Authorization failed: \(error.localizedDescription)"
        }
    }

    // MARK: One-shot sync

    func syncRecent(minutes: Int = 60) async {
        let end = Date()
        let start = end.addingTimeInterval(-Double(minutes) * 60)
        var collected: [VitalSample] = []

        for type in HealthKitSupport.readTypes {
            if let qt = type as? HKQuantityType {
                collected += await fetchQuantity(qt, start: start, end: end)
            } else if let ct = type as? HKCategoryType {
                collected += await fetchSleep(ct, start: start, end: end)
            }
        }

        await post(collected, label: "Synced last \(minutes) min")
    }

    private func fetchQuantity(_ type: HKQuantityType, start: Date, end: Date) async -> [VitalSample] {
        await withCheckedContinuation { cont in
            let predicate = HKQuery.predicateForSamples(withStart: start, end: end)
            let query = HKSampleQuery(
                sampleType: type, predicate: predicate, limit: HKObjectQueryNoLimit,
                sortDescriptors: [NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)]
            ) { _, samples, _ in
                let out = (samples as? [HKQuantitySample] ?? [])
                    .compactMap(HealthKitSupport.sample(from:))
                cont.resume(returning: out)
            }
            store.execute(query)
        }
    }

    private func fetchSleep(_ type: HKCategoryType, start: Date, end: Date) async -> [VitalSample] {
        await withCheckedContinuation { cont in
            let predicate = HKQuery.predicateForSamples(withStart: start, end: end)
            let query = HKSampleQuery(
                sampleType: type, predicate: predicate, limit: HKObjectQueryNoLimit,
                sortDescriptors: nil
            ) { _, samples, _ in
                let out = (samples as? [HKCategorySample] ?? [])
                    .compactMap(HealthKitSupport.sample(from:))
                cont.resume(returning: out)
            }
            store.execute(query)
        }
    }

    // MARK: Live incremental sync (anchored queries)

    func startLiveSync() {
        for type in HealthKitSupport.readTypes {
            guard let st = type as? HKSampleType else { continue }
            let query = HKAnchoredObjectQuery(
                type: st, predicate: nil, anchor: anchors[st], limit: HKObjectQueryNoLimit
            ) { [weak self] _, samples, _, newAnchor, _ in
                self?.handleLive(type: st, samples: samples, newAnchor: newAnchor)
            }
            query.updateHandler = { [weak self] _, samples, _, newAnchor, _ in
                self?.handleLive(type: st, samples: samples, newAnchor: newAnchor)
            }
            store.execute(query)
            liveQueries.append(query)
        }
        lastStatus = "Live sync running"
    }

    func stopLiveSync() {
        liveQueries.forEach(store.stop)
        liveQueries.removeAll()
        lastStatus = "Live sync stopped"
    }

    private func handleLive(type: HKSampleType, samples: [HKSample]?, newAnchor: HKQueryAnchor?) {
        if let a = newAnchor { anchors[type] = a }
        let mapped: [VitalSample] = (samples ?? []).compactMap { s in
            if let q = s as? HKQuantitySample { return HealthKitSupport.sample(from: q) }
            if let c = s as? HKCategorySample { return HealthKitSupport.sample(from: c) }
            return nil
        }
        Task { await post(mapped, label: "Live: +\(mapped.count)") }
    }

    // MARK: Networking

    private func post(_ samples: [VitalSample], label: String) async {
        guard !samples.isEmpty else { lastStatus = "\(label): nothing new"; return }
        do {
            client = AttuneClient(baseURL: BackendConfig.baseURL)  // pick up URL changes
            try await client.ingest(samples)
            lastStatus = "\(label): sent \(samples.count)"
        } catch {
            lastStatus = "Send failed: \(error.localizedDescription)"
        }
    }
}
