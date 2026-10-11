import SwiftUI

struct WatchContentView: View {
    @EnvironmentObject var reader: WorkoutHeartRateReader
    @State private var running = false

    var body: some View {
        VStack(spacing: 8) {
            Text("\(Int(reader.currentHR))")
                .font(.system(size: 44, weight: .bold, design: .rounded))
                .monospacedDigit()
            Text("BPM").font(.caption2).foregroundStyle(.secondary)

            Button(running ? "Stop" : "Start") {
                running.toggle()
                running ? reader.start() : reader.stop()
            }
            .tint(running ? .red : .green)

            Text(reader.status).font(.system(size: 10)).foregroundStyle(.secondary)
        }
        .padding()
    }
}

#Preview {
    WatchContentView().environmentObject(WorkoutHeartRateReader())
}
