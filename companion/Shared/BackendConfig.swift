import Foundation

/// Where the Attune core is reachable. Edit `defaultBaseURL` to your laptop's LAN address
/// before building, or set it at runtime in the app's text field (persisted to UserDefaults).
///
/// Why not 127.0.0.1? On a real iPhone/Apple Watch, localhost is the device itself. Use the
/// machine running `attune serve` — find its LAN IP with `ipconfig getifaddr en0` (macOS).
enum BackendConfig {
    static let defaultBaseURL = URL(string: "http://192.168.1.42:8000")!

    private static let key = "attune.baseURL"

    static var baseURL: URL {
        get {
            if let s = UserDefaults.standard.string(forKey: key), let u = URL(string: s) {
                return u
            }
            return defaultBaseURL
        }
        set { UserDefaults.standard.set(newValue.absoluteString, forKey: key) }
    }
}
