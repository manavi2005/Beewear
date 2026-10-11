import Foundation
import HealthKit

/// watchOS live heart-rate reader. Getting *high-frequency* HR on the wrist requires an
/// `HKWorkoutSession` + `HKLiveWorkoutBuilder`; a plain query only returns periodic samples.
/// We start a low-impact "mind & body" session purely to stream HR, and POST each new reading
/// to the core directly from the watch (watchOS can use URLSession over the LAN).
@MainActor
final class WorkoutHeartRateReader: NSObject, ObservableObject {
    @Published var currentHR: Double = 0
    @Published var status: String = "Idle"

    private let store = HKHealthStore()
    private var session: HKWorkoutSession?
    private var builder: HKLiveWorkoutBuilder?
    private var client = AttuneClient(baseURL: BackendConfig.baseURL)

    private let hrType = HKQuantityType.quantityType(forIdentifier: .heartRate)!
    private let hrUnit = HKUnit.count().unitDivided(by: .minute())

    func requestAuthorization() async {
        guard HKHealthStore.isHealthDataAvailable() else { status = "HealthKit unavailable"; return }
        do {
            try await store.requestAuthorization(toShare: [], read: HealthKitSupport.readTypes)
            status = "Authorized"
        } catch {
            status = "Auth failed: \(error.localizedDescription)"
        }
    }

    func start() {
        let config = HKWorkoutConfiguration()
        config.activityType = .mindAndBody
        config.locationType = .indoor
        do {
            let session = try HKWorkoutSession(healthStore: store, configuration: config)
            let builder = session.associatedWorkoutBuilder()
            builder.dataSource = HKLiveWorkoutDataSource(
                healthStore: store, workoutConfiguration: config
            )
            session.delegate = self
            builder.delegate = self
            self.session = session
            self.builder = builder

            let begin = Date()
            session.startActivity(with: begin)
            builder.beginCollection(withStart: begin) { _, _ in }
            client = AttuneClient(baseURL: BackendConfig.baseURL)
            status = "Reading live HR"
        } catch {
            status = "Start failed: \(error.localizedDescription)"
        }
    }

    func stop() {
        session?.end()
        builder?.endCollection(withEnd: Date()) { [weak self] _, _ in
            self?.builder?.finishWorkout { _, _ in }
        }
        status = "Stopped"
    }

    fileprivate func ingest(hr: Double, at date: Date) {
        currentHR = hr
        let sample = VitalSample(type: .heartRate, start: date, value: hr, unit: "count/min")
        Task {
            do { try await client.ingest([sample]) }
            catch { status = "Send failed: \(error.localizedDescription)" }
        }
    }
}

extension WorkoutHeartRateReader: HKWorkoutSessionDelegate {
    nonisolated func workoutSession(
        _ session: HKWorkoutSession,
        didChangeTo toState: HKWorkoutSessionState,
        from fromState: HKWorkoutSessionState,
        date: Date
    ) {}

    nonisolated func workoutSession(
        _ session: HKWorkoutSession, didFailWithError error: Error
    ) {
        Task { @MainActor in self.status = "Session error: \(error.localizedDescription)" }
    }
}

extension WorkoutHeartRateReader: HKLiveWorkoutBuilderDelegate {
    nonisolated func workoutBuilderDidCollectEvent(_ workoutBuilder: HKLiveWorkoutBuilder) {}

    nonisolated func workoutBuilder(
        _ workoutBuilder: HKLiveWorkoutBuilder,
        didCollectDataOf collectedTypes: Set<HKSampleType>
    ) {
        let hrType = HKQuantityType.quantityType(forIdentifier: .heartRate)!
        guard collectedTypes.contains(hrType),
              let stats = workoutBuilder.statistics(for: hrType),
              let quantity = stats.mostRecentQuantity() else { return }
        let unit = HKUnit.count().unitDivided(by: .minute())
        let hr = quantity.doubleValue(for: unit)
        let date = stats.mostRecentQuantityDateInterval()?.end ?? Date()
        Task { @MainActor in self.ingest(hr: hr, at: date) }
    }
}
