import Foundation
import HealthKit

/// Shared HealthKit ↔ canonical mapping used by both targets.
///
/// Reminder (ADR-002): every signal here originates on the Apple Watch via HealthKit. Bee is
/// never a source of vitals.
enum HealthKitSupport {
    /// The HealthKit types we read. Sleep is a category type; the rest are quantity types.
    static var readTypes: Set<HKObjectType> {
        var types = Set<HKObjectType>()
        for id in [HKQuantityTypeIdentifier.heartRate,
                   .heartRateVariabilitySDNN,
                   .respiratoryRate] {
            if let t = HKObjectType.quantityType(forIdentifier: id) { types.insert(t) }
        }
        if let sleep = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) {
            types.insert(sleep)
        }
        if let temp = HKObjectType.quantityType(forIdentifier: .appleSleepingWristTemperature) {
            types.insert(temp)
        }
        return types
    }

    /// Quantity identifier → (our Kind, HKUnit, unit string the core expects).
    static func quantityMapping(
        for id: HKQuantityTypeIdentifier
    ) -> (kind: VitalSample.Kind, unit: HKUnit, unitString: String)? {
        switch id {
        case .heartRate:
            return (.heartRate, HKUnit.count().unitDivided(by: .minute()), "count/min")
        case .heartRateVariabilitySDNN:
            return (.hrvSDNN, HKUnit.secondUnit(with: .milli), "ms")
        case .respiratoryRate:
            return (.respiratoryRate, HKUnit.count().unitDivided(by: .minute()), "count/min")
        case .appleSleepingWristTemperature:
            return (.wristTemperature, HKUnit.degreeCelsius(), "degC")
        default:
            return nil
        }
    }

    /// Convert an `HKQuantitySample` into our canonical `VitalSample`.
    static func sample(from q: HKQuantitySample) -> VitalSample? {
        guard let id = quantityIdentifier(of: q.quantityType),
              let m = quantityMapping(for: id) else { return nil }
        return VitalSample(
            type: m.kind,
            start: q.startDate,
            end: q.endDate,
            value: q.quantity.doubleValue(for: m.unit),
            unit: m.unitString
        )
    }

    /// Convert a sleep `HKCategorySample` into our canonical `VitalSample` (1.0 = asleep).
    static func sample(from c: HKCategorySample) -> VitalSample? {
        guard c.categoryType.identifier == HKCategoryTypeIdentifier.sleepAnalysis.rawValue
        else { return nil }
        let asleep: Bool
        if #available(iOS 16.0, watchOS 9.0, *) {
            asleep = [HKCategoryValueSleepAnalysis.asleepCore.rawValue,
                      HKCategoryValueSleepAnalysis.asleepDeep.rawValue,
                      HKCategoryValueSleepAnalysis.asleepREM.rawValue,
                      HKCategoryValueSleepAnalysis.asleepUnspecified.rawValue].contains(c.value)
        } else {
            asleep = c.value == HKCategoryValueSleepAnalysis.asleep.rawValue
        }
        return VitalSample(type: .sleep, start: c.startDate, end: c.endDate,
                           value: asleep ? 1.0 : 0.0, unit: "category")
    }

    private static func quantityIdentifier(of type: HKQuantityType) -> HKQuantityTypeIdentifier? {
        HKQuantityTypeIdentifier(rawValue: type.identifier)
    }
}
