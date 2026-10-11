import SwiftUI

@main
struct AttuneApp: App {
    @StateObject private var health = HealthKitService()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(health)
                .task { await health.requestAuthorization() }
        }
    }
}
