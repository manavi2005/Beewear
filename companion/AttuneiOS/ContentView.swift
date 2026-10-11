import SwiftUI

struct ContentView: View {
    @EnvironmentObject var health: HealthKitService
    @State private var urlText = BackendConfig.baseURL.absoluteString
    @State private var lookback = 60
    @State private var liveOn = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Backend") {
                    TextField("http://<laptop-ip>:8000", text: $urlText)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                    Button("Save URL") {
                        if let u = URL(string: urlText) { BackendConfig.baseURL = u }
                    }
                }

                Section("HealthKit") {
                    LabeledContent("Authorized", value: health.isAuthorized ? "Yes" : "No")
                    if !health.isAuthorized {
                        Button("Request access") { Task { await health.requestAuthorization() } }
                    }
                }

                Section("Sync") {
                    Stepper("Look back: \(lookback) min", value: $lookback, in: 10...240, step: 10)
                    Button("Sync now") { Task { await health.syncRecent(minutes: lookback) } }
                    Toggle("Live sync", isOn: $liveOn)
                        .onChange(of: liveOn) { _, on in
                            on ? health.startLiveSync() : health.stopLiveSync()
                        }
                }

                Section("Status") {
                    Text(health.lastStatus).font(.footnote).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Attune")
        }
    }
}

#Preview {
    ContentView().environmentObject(HealthKitService())
}
