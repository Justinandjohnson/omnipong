import SwiftUI
import AVKit

public struct VideoBackgroundView: View {
    @State private var player: AVQueuePlayer?
    @State private var looper: AVPlayerLooper?
    @State private var errorMessage: String?

    public init() {}

    public var body: some View {
        GeometryReader { geo in
            ZStack {
                if let player {
                    VideoPlayer(player: player)
                        .aspectRatio(contentMode: .fill)
                        .frame(width: geo.size.width, height: geo.size.height)
                        .disabled(true)
                        .ignoresSafeArea()
                }

                if let errorMessage {
                    Text(errorMessage)
                        .foregroundColor(.red)
                        .padding()
                        .background(Color.black.opacity(0.8))
                        .cornerRadius(10)
                }
            }
        }
        .onAppear {
            setupLoopingVideo()
        }
        .onDisappear {
            player?.pause()
        }
    }

    private func setupLoopingVideo() {
        guard player == nil else { return }
        guard let url = Bundle.main.url(forResource: "background", withExtension: "mp4") else {
            errorMessage = "Background video not found."
            return
        }
        let playerItem = AVPlayerItem(url: url)
        let queuePlayer = AVQueuePlayer(playerItem: playerItem)
        let playerLooper = AVPlayerLooper(player: queuePlayer, templateItem: playerItem)
        queuePlayer.isMuted = true
        queuePlayer.volume = 0
        queuePlayer.play()
        player = queuePlayer
        looper = playerLooper
    }
}
