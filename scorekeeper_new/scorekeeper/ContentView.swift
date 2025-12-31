import SwiftUI
import MessageUI
import AVKit

struct VideoBackgroundView: View {
    @State private var player: AVQueuePlayer?
    @State private var looper: AVPlayerLooper?
    @State private var errorMessage: String?
    
    var body: some View {
        GeometryReader { geo in
            ZStack {
                VideoPlayer(player: player)
                    .aspectRatio(contentMode: .fill)
                    .frame(width: geo.size.width, height: geo.size.height)
                    .onAppear {
                        setupLoopingVideo()
                    }
                    .disabled(true) // Disable controls interaction
                    .ignoresSafeArea()
                
                if let errorMessage = errorMessage {
                    Text(errorMessage)
                        .foregroundColor(.red)
                        .padding()
                        .background(Color.black.opacity(0.8))
                        .cornerRadius(10)
                }
            }
        }
    }
    
    private func setupLoopingVideo() {
        // Look for the file in the main bundle
        guard let url = Bundle.main.url(forResource: "background", withExtension: "mp4") else {
            print("❌ Could not find background.mp4 in bundle")
            errorMessage = "❌ Debug: background.mp4 not found in Bundle.main"
            return
        }
        
        // Setup Looper
        let playerItem = AVPlayerItem(url: url)
        let queuePlayer = AVQueuePlayer(playerItem: playerItem)
        let playerLooper = AVPlayerLooper(player: queuePlayer, templateItem: playerItem)
        
        self.player = queuePlayer
        self.looper = playerLooper
        
        queuePlayer.play()
        queuePlayer.isMuted = true // Mute by default for background
    }
}


struct ContentView: View {
    @StateObject var manager = MatchManager()
    
    // Animation States
    @State private var animateBlob1 = false
    @State private var animateBlob2 = false
    @State private var animateBlob3 = false
    @State private var showSettings = false
    @State private var backendURLInput = ""
    
    var body: some View {
        ZStack {
            // MARK: - Video Background
            ZStack {
                VideoBackgroundView()
                    .overlay(Color.black.opacity(0.4)) // Darken for readability
                    .onTapGesture {
                        // Dismiss keyboard if tap on background
                        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                    }
            }
            .ignoresSafeArea()
            
            // MARK: - UI Layer
            VStack(spacing: 30) {
                Text("Table Tennis")
                    .font(.system(.title3, design: .rounded))
                    .fontWeight(.medium)
                    .foregroundStyle(.white.opacity(0.7))
                    .padding(.top, 10)
                    .onLongPressGesture {
                        backendURLInput = UserDefaults.standard.string(forKey: "backend_url") ?? "http://localhost:8000"
                        showSettings = true
                    }
                
                // Scores Container
                HStack(spacing: 20) {
                    PlayerCard(name: manager.player1Name, score: manager.player1Score, sets: manager.player1Sets)
                    PlayerCard(name: manager.player2Name, score: manager.player2Score, sets: manager.player2Sets)
                }
                .padding(.horizontal)
                
                Spacer()
                
                // Transcript text (subtle)
                if !manager.lastTranscript.isEmpty {
                    Text(manager.lastTranscript)
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.5))
                        .padding()
                        .background(.ultraThinMaterial)
                        .cornerRadius(10)
                        .transition(.opacity)
                }
                
                Spacer()
                
                // Liquid Talk Button
                ZStack {
                    // Pulsing Ring
                    if manager.isRecording {
                        Circle()
                            .stroke(Color.white.opacity(0.3), lineWidth: 2)
                            .frame(width: 120, height: 120)
                            .scaleEffect(1.5)
                            .opacity(0)
                            .animation(.easeOut(duration: 1.0).repeatForever(autoreverses: false), value: manager.isRecording)
                    }
                    
                    Button(action: { }) {
                        Image(systemName: "mic.fill")
                            .font(.system(size: 40))
                            .foregroundColor(.white)
                            .frame(width: 100, height: 100)
                            .background(
                                ZStack {
                                    Circle().fill(.ultraThinMaterial)
                                    Circle().fill(manager.isRecording ? Color.red.opacity(0.8) : Color.white.opacity(0.2))
                                }
                            )
                            .overlay(
                                Circle().stroke(Color.white.opacity(0.5), lineWidth: 1)
                            )
                            .shadow(color: .black.opacity(0.2), radius: 10, x: 0, y: 5)
                            .scaleEffect(manager.isRecording ? 1.1 : 1.0)
                    }
                    .simultaneousGesture(
                        DragGesture(minimumDistance: 0)
                            .onChanged { _ in
                                if !manager.isRecording {
                                    manager.startRecording()
                                    // Heavy Haptic
                                    let impact = UIImpactFeedbackGenerator(style: .heavy)
                                    impact.impactOccurred()
                                }
                            }
                            .onEnded { _ in
                                manager.stopRecording()
                                // Light Haptic
                                let impact = UIImpactFeedbackGenerator(style: .medium)
                                impact.impactOccurred()
                            }
                    )
                }
                .padding(.bottom, 50)
            }
        }
        .alert("Backend Configuration", isPresented: $showSettings) {
            TextField("Server URL", text: $backendURLInput)
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)
            Button("Save") {
                UserDefaults.standard.set(backendURLInput, forKey: "backend_url")
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("Enter your production Render URL or local IP address.")
        }
        .sheet(isPresented: $manager.showSMSSheet) {
            if MFMessageComposeViewController.canSendText() {
                SMSView(recipients: [], messageBody: manager.generateMessageBody()) { _ in
                    // Handle completion
                }
            } else {
                Text("SMS not available on this device")
                    .padding()
                    .background(.ultraThinMaterial)
            }
        }
    }
}

// MARK: - Subcomponents

struct PlayerCard: View {
    var name: String
    var score: Int
    var sets: Int
    
    var body: some View {
        VStack(spacing: 15) {
            Text(name)
                .font(.system(.headline, design: .rounded))
                .foregroundColor(.white.opacity(0.8))
            
            Text("\(score)")
                .font(.system(size: 80, weight: .bold, design: .rounded))
                .foregroundColor(.white)
                // Score Change Animation
                .contentTransition(.numericText(countsDown: false))
                .transaction { t in
                    t.animation = .spring(response: 0.6, dampingFraction: 0.7)
                }
            
            Text("Sets: \(sets)")
                .font(.system(.subheadline, design: .rounded))
                .foregroundColor(.white.opacity(0.6))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
        .background(.ultraThinMaterial)
        .cornerRadius(30)
        .shadow(color: .black.opacity(0.1), radius: 10, x: 0, y: 5)
    }
}
