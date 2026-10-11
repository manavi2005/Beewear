import SwiftUI

@main
struct AttuneWatchApp: App {
    @StateObject private var reader = WorkoutHeartRateReader()

    var body: some Scene {
        WindowGroup {
            WatchContentView()
                .environmentObject(reader)
                .task { await reader.requestAuthorization() }
        }
    }
}
