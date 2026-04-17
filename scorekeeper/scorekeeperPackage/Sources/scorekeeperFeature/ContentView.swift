import SwiftUI
import MessageUI

@MainActor
public struct ContentView: View {
    @State private var manager = MatchManager()
    @State private var glowAnimation = false
    @State private var showHistory = false
    @State private var showSettings = false
    @State private var backendURLInput = ""
    @State private var showSwipeHint = false
    @State private var showUndoHint = false

    public init() {}

    public var body: some View {
        // @Bindable lets us derive Binding<T> from an @Observable stored in @State
        @Bindable var manager = manager

        GeometryReader { geometry in
            ZStack {
                // MARK: - Video Background
                VideoBackgroundView()
                    .overlay(Color.black.opacity(0.3))
                    .ignoresSafeArea()

                // MARK: - UI Layer
                VStack(spacing: 12) {
                    topBar

                    scoreCards

                    Spacer()

                    transcriptBanner

                    Spacer()

                    micHint
                        .padding(.bottom, 60)
                }

                // MARK: - Gesture Zone
                gestureZone(geometry: geometry)

                // Recording border
                if manager.isRecording {
                    RoundedRectangle(cornerRadius: 45)
                        .strokeBorder(Color.red, lineWidth: 4)
                        .shadow(color: .red.opacity(0.8), radius: 20)
                        .ignoresSafeArea()
                        .allowsHitTesting(false)
                }

                swipeHintOverlay
                undoHintOverlay
            }
        }
        .alert("Backend Configuration", isPresented: $showSettings) {
            TextField("Server URL", text: $backendURLInput)
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)
            Button("Save") {
                UserDefaults.standard.set(backendURLInput, forKey: "backend_url")
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Enter your production Render URL.")
        }
        .sheet(isPresented: $manager.showSMSSheet) {
            if MFMessageComposeViewController.canSendText() {
                SMSView(recipients: [], messageBody: manager.generateMessageBody())
            } else {
                Text("SMS not available on this device")
                    .padding()
                    .background(.ultraThinMaterial)
            }
        }
        .sheet(isPresented: $manager.showMatchComplete) {
            MatchCompleteView(manager: manager)
        }
        .sheet(isPresented: $showHistory) {
            MatchHistoryView(manager: manager)
        }
    }

    // MARK: - Subviews

    private var topBar: some View {
        HStack(alignment: .center) {
            Button {
                manager.startNewMatch()
                UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            } label: {
                Image(systemName: "plus.circle.fill")
                    .font(.system(size: 32))
                    .foregroundColor(.white.opacity(0.9))
            }
            .accessibilityLabel("New Match")

            Spacer()

            VStack(spacing: 4) {
                Text("TABLE TENNIS")
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                    .onLongPressGesture {
                        backendURLInput = UserDefaults.standard.string(forKey: "backend_url")
                            ?? "https://omnipong-backend.onrender.com"
                        showSettings = true
                    }

                Text("SET \(manager.currentMatch?.currentSetNumber ?? 1)")
                    .font(.system(size: 16, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.8))
            }

            Spacer()

            HStack(spacing: 16) {
                Button {
                    showHistory = true
                    UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                } label: {
                    Image(systemName: "clock.arrow.circlepath")
                        .font(.system(size: 28))
                        .foregroundColor(.white.opacity(0.9))
                }
                .accessibilityLabel("Match History")

                Button {
                    manager.showSMSSheet = true
                    UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                } label: {
                    Image(systemName: "square.and.arrow.up.circle.fill")
                        .font(.system(size: 32))
                        .foregroundColor(.white.opacity(0.9))
                }
                .accessibilityLabel("Share Score")
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 5)
    }

    private var scoreCards: some View {
        HStack(spacing: 16) {
            // When a set is in progress show live points; otherwise show sets won
            let setInProgress = manager.player1Score > 0 || manager.player2Score > 0
            let display1 = setInProgress ? manager.player1Score : manager.player1Sets
            let display2 = setInProgress ? manager.player2Score : manager.player2Sets

            PlayerCardView(
                name: manager.player1Name,
                score: display1,
                isLeading: display1 > display2,
                playerSide: .player1,
                sets: manager.currentMatch?.sets ?? []
            )
            PlayerCardView(
                name: manager.player2Name,
                score: display2,
                isLeading: display2 > display1,
                playerSide: .player2,
                sets: manager.currentMatch?.sets ?? []
            )
        }
        .padding(.horizontal)
    }

    @ViewBuilder
    private var transcriptBanner: some View {
        if !manager.lastTranscript.isEmpty {
            Text(manager.lastTranscript)
                .font(.caption)
                .foregroundColor(.white.opacity(0.85))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(.ultraThinMaterial)
                .cornerRadius(10)
                .transition(.opacity)
                .padding(.horizontal, 24)
        }
    }

    private var micHint: some View {
        VStack(spacing: 8) {
            Image(systemName: manager.isRecording ? "mic.fill" : "mic")
                .font(.system(size: 30))
                .foregroundColor(manager.isRecording ? .red : .white.opacity(0.5))
                .scaleEffect(manager.isRecording ? 1.2 : 1.0)
                .animation(.easeInOut(duration: 0.3), value: manager.isRecording)

            Group {
                if manager.isProcessing {
                    Text("Processing...")
                } else if manager.isRecording {
                    Text("Listening...")
                } else {
                    Text("Hold anywhere to speak")
                }
            }
            .font(.system(.caption, design: .rounded))
            .foregroundColor(.white.opacity(0.5))
        }
    }

    private func gestureZone(geometry: GeometryProxy) -> some View {
        VStack {
            Spacer()
            Color.clear
                .frame(height: geometry.size.height / 2)
                .contentShape(Rectangle())
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { value in
                            handleDragChanged(value)
                        }
                        .onEnded { value in
                            handleDragEnded(value)
                        }
                )
        }
    }

    private func handleDragChanged(_ value: DragGesture.Value) {
        let dy = value.translation.height
        if dy < -80 {
            if manager.isRecording { manager.stopRecording() }
            if !showSwipeHint {
                showSwipeHint = true
                showUndoHint = false
                UIImpactFeedbackGenerator(style: .light).impactOccurred()
            }
        } else if dy > 80 && manager.canUndo {
            if manager.isRecording { manager.stopRecording() }
            if !showUndoHint {
                showUndoHint = true
                showSwipeHint = false
                UIImpactFeedbackGenerator(style: .light).impactOccurred()
            }
        } else if abs(dy) < 50 && !showSwipeHint && !showUndoHint {
            if !manager.isRecording {
                manager.startRecording()
                UIImpactFeedbackGenerator(style: .heavy).impactOccurred()
                withAnimation { glowAnimation = true }
            }
        }
    }

    private func handleDragEnded(_ value: DragGesture.Value) {
        let dy = value.translation.height
        if dy < -120 {
            manager.startNewMatch()
            UIImpactFeedbackGenerator(style: .heavy).impactOccurred()
        } else if dy > 120 && manager.canUndo {
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

    @ViewBuilder
    private var swipeHintOverlay: some View {
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
            }
            .padding(.top, 100)
            .allowsHitTesting(false)
        }
    }

    @ViewBuilder
    private var undoHintOverlay: some View {
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
            }
            .allowsHitTesting(false)
        }
    }
}

// MARK: - PlayerCardView

public struct PlayerCardView: View {
    public var name: String
    public var score: Int
    public var isLeading: Bool
    public var playerSide: PlayerSide
    public var sets: [SetRecord]

    public init(name: String, score: Int, isLeading: Bool, playerSide: PlayerSide, sets: [SetRecord]) {
        self.name = name
        self.score = score
        self.isLeading = isLeading
        self.playerSide = playerSide
        self.sets = sets
    }

    public var body: some View {
        VStack(spacing: 10) {
            Text(name)
                .font(.system(size: 22, weight: .semibold, design: .rounded))
                .foregroundColor(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.7)

            Text("\(score)")
                .font(.system(size: 85, weight: .bold, design: .rounded))
                .foregroundColor(.white)
                .contentTransition(.numericText())
                .accessibilityLabel("\(name) score: \(score)")

            setHistoryRow
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .background(.ultraThinMaterial)
        .overlay(
            RoundedRectangle(cornerRadius: 30)
                .stroke(isLeading ? Color.green.opacity(0.7) : Color.clear, lineWidth: 3)
        )
        .cornerRadius(30)
    }

    private var setHistoryRow: some View {
        HStack(spacing: 6) {
            ForEach(0..<5, id: \.self) { index in
                VStack(spacing: 3) {
                    if index < sets.count {
                        let set = sets[index]
                        let won = set.winner == playerSide
                        let myScore = playerSide == .player1 ? set.player1Score : set.player2Score
                        let theirScore = playerSide == .player1 ? set.player2Score : set.player1Score
                        Circle()
                            .fill(won ? Color.green : Color.red)
                            .frame(width: 12, height: 12)
                        Text("\(myScore)-\(theirScore)")
                            .font(.system(size: 11, weight: .bold, design: .rounded))
                            .foregroundColor(won ? .green : .red)
                    } else {
                        Circle()
                            .fill(Color.white.opacity(0.25))
                            .frame(width: 12, height: 12)
                    }
                }
            }
        }
    }
}

// MARK: - MatchCompleteView

public struct MatchCompleteView: View {
    @Bindable var manager: MatchManager
    @Environment(\.dismiss) private var dismiss

    public init(manager: MatchManager) {
        self.manager = manager
    }

    public var body: some View {
        ZStack {
            Color.black.opacity(0.9).ignoresSafeArea()
            VStack(spacing: 30) {
                Text("Match Complete!")
                    .font(.system(.largeTitle, design: .rounded))
                    .fontWeight(.bold)
                    .foregroundColor(.white)

                if let match = manager.currentMatch {
                    matchSummary(match: match)
                }

                HStack(spacing: 20) {
                    Button("Share") {
                        manager.showSMSSheet = true
                    }
                    .padding()
                    .background(.ultraThinMaterial)
                    .cornerRadius(15)
                    .foregroundColor(.white)

                    Button("New Match") {
                        manager.startNewMatch()
                        dismiss()
                    }
                    .padding()
                    .background(Color.green)
                    .cornerRadius(15)
                    .foregroundColor(.white)
                }

                Button("Done") {
                    dismiss()
                }
                .foregroundColor(.white.opacity(0.6))
            }
            .padding()
        }
    }

    private func matchSummary(match: MatchRecord) -> some View {
        VStack(spacing: 8) {
            let winnerName = match.winner == .player1 ? match.player1Name : match.player2Name
            Text(winnerName)
                .font(.system(.title, design: .rounded))
                .fontWeight(.bold)
                .foregroundColor(.green)

            Text("Wins \(match.player1SetCount) – \(match.player2SetCount)")
                .font(.system(.title2, design: .rounded))
                .foregroundColor(.white)

            if !match.sets.isEmpty {
                VStack(spacing: 4) {
                    ForEach(match.sets) { set in
                        Text("Set \(set.setNumber): \(set.player1Score) – \(set.player2Score)")
                            .font(.system(.caption, design: .rounded))
                            .foregroundColor(.white.opacity(0.7))
                    }
                }
                .padding(.top, 4)
            }
        }
        .padding()
        .background(.ultraThinMaterial)
        .cornerRadius(20)
    }
}

// MARK: - MatchHistoryView

public struct MatchHistoryView: View {
    let manager: MatchManager
    @Environment(\.dismiss) private var dismiss

    public init(manager: MatchManager) {
        self.manager = manager
    }

    public var body: some View {
        NavigationView {
            ZStack {
                Color.black.ignoresSafeArea()
                if manager.matchHistory.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "tablecells")
                            .font(.system(size: 48))
                            .foregroundColor(.gray.opacity(0.5))
                        Text("No Match History")
                            .foregroundColor(.gray)
                            .font(.system(.headline, design: .rounded))
                    }
                } else {
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(manager.matchHistory) { match in
                                MatchHistoryCard(match: match)
                            }
                        }
                        .padding()
                    }
                }
            }
            .navigationTitle("Match History")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                        .foregroundColor(.white)
                }
            }
        }
    }
}

// MARK: - MatchHistoryCard

public struct MatchHistoryCard: View {
    public let match: MatchRecord

    public init(match: MatchRecord) {
        self.match = match
    }

    public var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text(match.date, style: .date)
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.6))
                Spacer()
                Text("Sets: \(match.player1SetCount) – \(match.player2SetCount)")
                    .font(.headline)
                    .foregroundColor(.green)
            }

            HStack {
                Text(match.player1Name)
                    .foregroundColor(match.winner == .player1 ? .green : .white)
                    .fontWeight(match.winner == .player1 ? .bold : .regular)
                Spacer()
                Text("vs")
                    .foregroundColor(.gray)
                Spacer()
                Text(match.player2Name)
                    .foregroundColor(match.winner == .player2 ? .green : .white)
                    .fontWeight(match.winner == .player2 ? .bold : .regular)
            }

            if !match.sets.isEmpty {
                HStack(spacing: 8) {
                    ForEach(match.sets) { set in
                        Text("\(set.player1Score)-\(set.player2Score)")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundColor(set.winner == .player1 ? .green : .red)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill((set.winner == .player1 ? Color.green : Color.red).opacity(0.15))
                            )
                    }
                }
            }
        }
        .padding()
        .background(.ultraThinMaterial)
        .cornerRadius(16)
    }
}
