import Foundation

/// Minimal HTTP client that POSTs canonical vitals to the Attune core (ADR-009).
///
/// The base URL is where `attune serve` is listening. On a phone/watch talking to a laptop
/// over the LAN, use the laptop's LAN IP (e.g. http://192.168.1.42:8000), not 127.0.0.1.
/// Configure it once in `BackendConfig` (see BackendConfig.swift).
struct AttuneClient {
    let baseURL: URL

    init(baseURL: URL) { self.baseURL = baseURL }

    /// POST /ingest/vitals with a batch of samples. The core accepts an array directly.
    func ingest(_ samples: [VitalSample]) async throws {
        guard !samples.isEmpty else { return }
        var request = URLRequest(url: baseURL.appendingPathComponent("ingest/vitals"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(samples)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw AttuneError.badResponse(body)
        }
    }

    /// GET /health — handy for a "can I reach the backend?" check in the UI.
    func health() async throws -> Bool {
        let (_, response) = try await URLSession.shared.data(
            from: baseURL.appendingPathComponent("health")
        )
        return (response as? HTTPURLResponse).map { (200..<300).contains($0.statusCode) } ?? false
    }

    enum AttuneError: Error { case badResponse(String) }
}
