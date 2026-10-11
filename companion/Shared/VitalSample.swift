import Foundation

/// The wire model shared by the iOS and watchOS targets.
///
/// This is a 1:1 mirror of the core's canonical `VitalSample` and of the
/// `POST /ingest/vitals` request body (see `docs/DATA_MODEL.md`, ADR-009). The JSON keys
/// and the `type` string values MUST match the Python `VitalType` enum exactly, or the core
/// will reject the payload.
///
/// Golden rule (ADR-008): `tsMs` is UTC epoch **milliseconds**.
struct VitalSample: Codable {
    enum Kind: String, Codable {
        case heartRate = "heart_rate"
        case hrvSDNN = "hrv_sdnn"
        case respiratoryRate = "respiratory_rate"
        case wristTemperature = "wrist_temperature"
        case sleep = "sleep"
        case movement = "movement"
    }

    let type: Kind
    let tsMs: Int
    let endMs: Int?
    let value: Double
    let unit: String
    let source: String

    enum CodingKeys: String, CodingKey {
        case type
        case tsMs = "ts_ms"
        case endMs = "end_ms"
        case value
        case unit
        case source
    }

    init(type: Kind, start: Date, end: Date? = nil, value: Double, unit: String,
         source: String = "apple_watch") {
        self.type = type
        self.tsMs = Int(start.timeIntervalSince1970 * 1000)
        self.endMs = end.map { Int($0.timeIntervalSince1970 * 1000) }
        self.value = value
        self.unit = unit
        self.source = source
    }
}
