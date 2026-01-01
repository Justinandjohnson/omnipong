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
                    .disabled(true)
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
        guard let url = Bundle.main.url(forResource: "background", withExtension: "mp4") else {
            print("❌ Could not find background.mp4 in bundle")
            errorMessage = "❌ Debug: background.mp4 not found in Bundle.main"
            return
        }
        let playerItem = AVPlayerItem(url: url)
        let queuePlayer = AVQueuePlayer(playerItem: playerItem)
        let playerLooper = AVPlayerLooper(player: queuePlayer, templateItem: playerItem)
        self.player = queuePlayer
        self.looper = playerLooper
        queuePlayer.play()
        queuePlayer.isMuted = true
    }
}

struct ContentView: View {
    @StateObject var manager = MatchManager()
    @State private var glowAnimation = false
    @State private var showHistory = false
    @State private var swipeOffset: CGFloat = 0
    @State private var showSwipeHint = false
    @State private var showUndoHint = false
    @State private var showSettings = false
    @State private var backendURLInput = ""

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // MARK: - Video Background
                VideoBackgroundView()
                    .overlay(Color.black.opacity(0.3))
                    .ignoresSafeArea()

                // MARK: - UI Layer
                VStack(spacing: 12) {
                    // Top bar
                    HStack(alignment: .center) {
                        Button(action: {
                            manager.startNewMatch()
                            let impact = UIImpactFeedbackGenerator(style: .medium)
                            impact.impactOccurred()
                        }) {
                            Image(systemName: "plus.circle.fill")
                                .font(.system(size: 32))
                                .foregroundColor(.white.opacity(0.9))
                        }

                        Spacer()

                        // Match Status Header
                        VStack(spacing: 4) {
                            Text("TABLE TENNIS")
                                .font(.system(size: 24, weight: .bold, design: .rounded))
                                .foregroundStyle(.white)
                                .onLongPressGesture {
                                    backendURLInput = UserDefaults.standard.string(forKey: "backend_url") ?? "https://omnipong-backend.onrender.com"
                                    showSettings = true
                                }
                            
                            Text("SET \(manager.currentMatch?.currentSetNumber ?? 1)")
                                .font(.system(size: 16, weight: .medium, design: .rounded))
                                .foregroundStyle(.white.opacity(0.8))
                        }

                        Spacer()

                        HStack(spacing: 16) {
                            Button(action: {
                                showHistory = true
                                let impact = UIImpactFeedbackGenerator(style: .medium)
                                impact.impactOccurred()
                            }) {
                                Image(systemName: "clock.arrow.circlepath")
                                    .font(.system(size: 28))
                                    .foregroundColor(.white.opacity(0.9))
                            }

                            Button(action: {
                                manager.showSMSSheet = true
                                let impact = UIImpactFeedbackGenerator(style: .medium)
                                impact.impactOccurred()
                            }) {
                                Image(systemName: "square.and.arrow.up.circle.fill")
                                    .font(.system(size: 32))
                                    .foregroundColor(.white.opacity(0.9))
                            }
                        }
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, 5)

                    // Scores Container
                    HStack(spacing: 16) {
                        // Show match score (sets won) when between sets, otherwise show current set score
                        let setInProgress = manager.player1Score > 0 || manager.player2Score > 0
                        let displayScore1 = setInProgress ? manager.player1Score : manager.player1Sets
                        let displayScore2 = setInProgress ? manager.player2Score : manager.player2Sets

                        PlayerCardView(
                            name: manager.player1Name,
                            score: displayScore1,
                            setsWon: manager.player1Sets,
                            isLeading: displayScore1 > displayScore2,
                            playerSide: .player1,
                            sets: manager.currentMatch?.sets ?? []
                        )
                        PlayerCardView(
                            name: manager.player2Name,
                            score: displayScore2,
                            setsWon: manager.player2Sets,
                            isLeading: displayScore2 > displayScore1,
                            playerSide: .player2,
                            sets: manager.currentMatch?.sets ?? []
                        )
                    }
                    .padding(.horizontal)

                    Spacer()

                    if !manager.lastTranscript.isEmpty {
                        Text(manager.lastTranscript)
                            .font(.caption)
                            .foregroundColor(.white.opacity(0.7))
                            .padding(.horizontal, 16)
                            .padding(.vertical, 10)
                            .background(.ultraThinMaterial)
                            .cornerRadius(10)
                            .transition(.opacity)
                    }

                    Spacer()

                    // Recording hint
                    VStack(spacing: 8) {
                        Image(systemName: manager.isRecording ? "mic.fill" : "mic")
                            .font(.system(size: 30))
                            .foregroundColor(manager.isRecording ? .red : .white.opacity(0.5))
                            .scaleEffect(manager.isRecording ? 1.2 : 1.0)
                            .animation(.easeInOut(duration: 0.3), value: manager.isRecording)

                        Text(manager.isRecording ? "Listening..." : "Hold anywhere to speak")
                            .font(.system(.caption, design: .rounded))
                            .foregroundColor(.white.opacity(0.5))
                    }
                    .padding(.bottom, 60)
                }

                // MARK: - Gesture Zone
                VStack {
                    Spacer()
                    Color.clear
                        .frame(height: geometry.size.height / 2)
                        .contentShape(Rectangle())
                        .gesture(
                            DragGesture(minimumDistance: 0)
                                .onChanged { value in
                                    let verticalMovement = value.translation.height
                                    if verticalMovement < -80 {
                                        if manager.isRecording { manager.stopRecording() }
                                        if !showSwipeHint {
                                            showSwipeHint = true
                                            showUndoHint = false
                                            UIImpactFeedbackGenerator(style: .light).impactOccurred()
                                        }
                                    } else if verticalMovement > 80 && manager.canUndo {
                                        if manager.isRecording { manager.stopRecording() }
                                        if !showUndoHint {
                                            showUndoHint = true
                                            showSwipeHint = false
                                            UIImpactFeedbackGenerator(style: .light).impactOccurred()
                                        }
                                    } else if abs(verticalMovement) < 50 && !showSwipeHint && !showUndoHint {
                                        if !manager.isRecording {
                                            manager.startRecording()
                                            UIImpactFeedbackGenerator(style: .heavy).impactOccurred()
                                            withAnimation { glowAnimation = true }
                                        }
                                    }
                                }
                                .onEnded { value in
                                    let verticalMovement = value.translation.height
                                    if verticalMovement < -120 {
                                        manager.startNewMatch()
                                        UIImpactFeedbackGenerator(style: .heavy).impactOccurred()
                                    } else if verticalMovement > 120 && manager.canUndo {
                                        if manager.undoLastSet() {
                                            UIImpactFeedbackGenerator(style: .heavy).impactOccurred()
                                        }
                                    } else if manager.isRecording {
                                        manager.stopRecording()
                                        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                                    }
                                    withAnimation {
                                        glowAnimation = false
                                        showSwipeHint = false
                                        showUndoHint = false
                                    }
                                }
                        )
                }

                if manager.isRecording {
                    RoundedRectangle(cornerRadius: 45)
                        .strokeBorder(Color.red, lineWidth: 4)
                        .shadow(color: .red.opacity(0.8), radius: 20)
                        .ignoresSafeArea()
                        .allowsHitTesting(false)
                }

                if showSwipeHint {
                    VStack {
                        VStack(spacing: 8) {
                            Image(systemName: "arrow.up.circle.fill")
                                .font(.system(size: 40))
                                .foregroundColor(.green)
                            Text("Release for New Match")
                                .font(.system(.headline, design: .rounded))
                                .foregroundColor(.white)
                        }
                        .padding()
                        .background(.ultraThinMaterial)
                        .cornerRadius(20)
                        Spacer()
                    }.padding(.top, 100).allowsHitTesting(false)
                }

                if showUndoHint {
                    VStack {
                        Spacer()
                        VStack(spacing: 8) {
                            Image(systemName: "arrow.uturn.backward.circle.fill")
                                .font(.system(size: 40))
                                .foregroundColor(.orange)
                            Text("Release to Undo Last Set")
                                .font(.system(.headline, design: .rounded))
                                .foregroundColor(.white)
                        }
                        .padding()
                        .background(.ultraThinMaterial)
                        .cornerRadius(20)
                        Spacer()
                    }.allowsHitTesting(false)
                }
            }
        }
        .alert("Backend Configuration", isPresented: $showSettings) {
            TextField("Server URL", text: $backendURLInput).textInputAutocapitalization(.never).keyboardType(.URL)
            Button("Save") { UserDefaults.standard.set(backendURLInput, forKey: "backend_url") }
            Button("Cancel", role: .cancel) { }
        } message: { Text("Enter your production Render URL.") }
        .sheet(isPresented: $manager.showSMSSheet) {
            if MFMessageComposeViewController.canSendText() {
                SMSView(recipients: [], messageBody: manager.generateMessageBody()) { _ in }
            } else {
                Text("SMS not available").padding().background(.ultraThinMaterial)
            }
        }
        .sheet(isPresented: $manager.showMatchComplete) { MatchCompleteView(manager: manager) }
        .sheet(isPresented: $showHistory) { MatchHistoryView(manager: manager) }
    }
}

// MARK: - Subcomponents

struct PlayerCardView: View {
    var name: String
    var score: Int
    var setsWon: Int
    var isLeading: Bool
    var playerSide: PlayerSide
    var sets: [SetRecord]

    var body: some View {
        VStack(spacing: 10) {
            Text(name)
                .font(.system(size: 22, weight: .semibold, design: .rounded))
                .foregroundColor(.white)

            Text("\(score)")
                .font(.system(size: 85, weight: .bold, design: .rounded))
                .foregroundColor(.white)
                .contentTransition(.numericText())

            HStack(spacing: 6) {
                ForEach(0..<5, id: \.self) { index in
                    VStack(spacing: 3) {
                        if index < sets.count {
                            let set = sets[index]
                            let won = set.winner == playerSide
                            // Show score from player's perspective (their score first)
                            let myScore = playerSide == .player1 ? set.player1Score : set.player2Score
                            let theirScore = playerSide == .player1 ? set.player2Score : set.player1Score
                            Circle().fill(won ? Color.green : Color.red).frame(width: 12, height: 12)
                            Text("\(myScore)-\(theirScore)")
                                .font(.system(size: 11, weight: .bold, design: .rounded))
                                .foregroundColor(won ? .green : .red)
                        } else {
                            Circle().fill(Color.white.opacity(0.3)).frame(width: 12, height: 12)
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .background(.ultraThinMaterial)
        .overlay(RoundedRectangle(cornerRadius: 30).stroke(isLeading ? Color.green.opacity(0.6) : Color.clear, lineWidth: 3))
        .cornerRadius(30)
    }
}

struct MatchCompleteView: View {
    @ObservedObject var manager: MatchManager
    @Environment(\.dismiss) var dismiss
    var body: some View {
        ZStack {
            Color.black.opacity(0.9).ignoresSafeArea()
            VStack(spacing: 30) {
                Text("Match Complete!").font(.system(.largeTitle, design: .rounded)).fontWeight(.bold).foregroundColor(.white)
                if let match = manager.currentMatch {
                    VStack(spacing: 8) {
                        Text(match.winner == .player1 ? match.player1Name : match.player2Name).font(.system(.title, design: .rounded)).fontWeight(.bold).foregroundColor(.green)
                        Text("\(match.player1SetCount) - \(match.player2SetCount)").font(.system(.title2, design: .rounded)).foregroundColor(.white)
                    }.padding().background(.ultraThinMaterial).cornerRadius(20)
                }
                HStack(spacing: 20) {
                    Button("Share") { manager.showSMSSheet = true }.padding().background(.ultraThinMaterial).cornerRadius(15)
                    Button("New Match") { manager.startNewMatch(); dismiss() }.padding().background(Color.green).cornerRadius(15)
                }
                Button("Done") { dismiss() }.foregroundColor(.white.opacity(0.6))
            }.padding()
        }
    }
}

struct MatchHistoryView: View {
    @ObservedObject var manager: MatchManager
    @Environment(\.dismiss) var dismiss
    var body: some View {
        NavigationView {
            ZStack {
                Color.black.ignoresSafeArea()
                if manager.matchHistory.isEmpty {
                    Text("No Match History").foregroundColor(.gray)
                } else {
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(manager.matchHistory) { match in
                                MatchHistoryCard(match: match)
                            }
                        }.padding()
                    }
                }
            }
            .navigationTitle("Match History")
            .toolbar { Button("Done") { dismiss() }.foregroundColor(.white) }
        }
    }
}

struct MatchHistoryCard: View {
    let match: MatchRecord
    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text(match.date, style: .date).font(.caption).foregroundColor(.white.opacity(0.6))
                Spacer()
                Text("\(match.player1SetCount) - \(match.player2SetCount)").font(.headline).foregroundColor(.green)
            }
            HStack {
                Text(match.player1Name).foregroundColor(match.winner == .player1 ? .green : .white)
                Spacer()
                Text("vs").foregroundColor(.gray)
                Spacer()
                Text(match.player2Name).foregroundColor(match.winner == .player2 ? .green : .white)
            }
        }.padding().background(.ultraThinMaterial).cornerRadius(16)
    }
}
