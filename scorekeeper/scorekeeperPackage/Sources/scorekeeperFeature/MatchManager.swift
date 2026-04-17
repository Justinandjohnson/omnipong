import Foundation
import AVFoundation
import SwiftUI
import Speech

// MARK: - Data Models

public enum PlayerSide: String, Codable, Sendable {
    case player1
    case player2
}

public struct SetRecord: Codable, Identifiable, Sendable {
    public let id: UUID
    public let setNumber: Int
    public let player1Score: Int
    public let player2Score: Int
    public let winner: PlayerSide
    public let timestamp: Date

    public init(setNumber: Int, player1Score: Int, player2Score: Int) {
        self.id = UUID()
        self.setNumber = setNumber
        self.player1Score = player1Score
        self.player2Score = player2Score
        self.winner = player1Score > player2Score ? .player1 : .player2
        self.timestamp = Date()
    }
}

public struct MatchRecord: Codable, Identifiable, Sendable {
    public let id: UUID
    public var player1Name: String
    public var player2Name: String
    public var sets: [SetRecord]
    public var winner: PlayerSide?
    public var isComplete: Bool
    public var date: Date

    public init(player1Name: String, player2Name: String) {
        self.id = UUID()
        self.player1Name = player1Name
        self.player2Name = player2Name
        self.sets = []
        self.winner = nil
        self.isComplete = false
        self.date = Date()
    }

    public var player1SetCount: Int {
        sets.filter { $0.winner == .player1 }.count
    }

    public var player2SetCount: Int {
        sets.filter { $0.winner == .player2 }.count
    }

    public var currentSetNumber: Int {
        sets.count + 1
    }

    public mutating func addSet(_ setRecord: SetRecord) {
        sets.append(setRecord)
        checkMatchCompletion()
    }

    public mutating func checkMatchCompletion() {
        // Best of 5: first to 3 sets wins
        if player1SetCount >= 3 {
            winner = .player1
            isComplete = true
        } else if player2SetCount >= 3 {
            winner = .player2
            isComplete = true
        }
    }
}

// MARK: - MatchManager

@MainActor
@Observable
public final class MatchManager: NSObject {
    // MARK: - Game State
    public var player1Score = 0
    public var player2Score = 0
    public var player1Sets = 0
    public var player2Sets = 0
    public var isRecording = false
    public var isProcessing = false
    public var lastTranscript = ""
    public var showSMSSheet = false

    // Dynamic Player Names
    public var player1Name = "Player 1"
    public var player2Name = "Player 2"

    // MARK: - Match Journal State
    public var currentMatch: MatchRecord?
    public var matchHistory: [MatchRecord] = []
    public var showMatchComplete = false

    // MARK: - Audio & Speech (nonisolated storage, only accessed via methods)
    private let audioSession = AVAudioSession.sharedInstance()
    private let speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let audioEngine = AVAudioEngine()

    // MARK: - Persistence Keys
    private let matchHistoryKey = "TableTennisMatchHistory"
    private let currentMatchKey = "TableTennisCurrentMatch"

    // MARK: - API Configuration
    private var baseURL: String {
        UserDefaults.standard.string(forKey: "backend_url") ?? "https://omnipong-backend.onrender.com"
    }

    public override init() {
        super.init()
        setupAudioSession()
        loadMatchHistory()

        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleAudioRouteChange),
            name: AVAudioSession.routeChangeNotification,
            object: nil
        )
    }

    @objc private nonisolated func handleAudioRouteChange(notification: Notification) {
        guard let userInfo = notification.userInfo,
              let reasonValue = userInfo[AVAudioSessionRouteChangeReasonKey] as? UInt,
              let reason = AVAudioSession.RouteChangeReason(rawValue: reasonValue) else {
            return
        }
        switch reason {
        case .newDeviceAvailable, .oldDeviceUnavailable:
            Task { @MainActor in
                self.updatePreferredInput()
            }
        default:
            break
        }
    }

    private func updatePreferredInput() {
        do {
            let availableInputs = audioSession.availableInputs ?? []
            if let bluetoothInput = availableInputs.first(where: {
                $0.portType == .bluetoothHFP || $0.portType == .bluetoothA2DP || $0.portType == .bluetoothLE
            }) {
                try audioSession.setPreferredInput(bluetoothInput)
            } else {
                try audioSession.setPreferredInput(nil)
            }
        } catch {
            print("⚠️ Failed to update audio input: \(error)")
        }
    }

    private func setupAudioSession() {
        do {
            try audioSession.setCategory(
                .playAndRecord,
                mode: .spokenAudio,
                options: [.allowBluetooth, .allowBluetoothA2DP, .defaultToSpeaker, .duckOthers]
            )
            try audioSession.setPreferredIOBufferDuration(0.005)
            try audioSession.setPreferredSampleRate(44100)
            try audioSession.setActive(true)
            updatePreferredInput()

            if #available(iOS 17.0, *) {
                AVAudioApplication.requestRecordPermission { _ in }
            } else {
                audioSession.requestRecordPermission { _ in }
            }

            SFSpeechRecognizer.requestAuthorization { _ in }
        } catch {
            print("Failed to set up audio session: \(error)")
        }
    }

    // MARK: - Table Tennis Validation

    public static func isValidSetScore(score1: Int, score2: Int) -> Bool {
        let maxScore = max(score1, score2)
        let minScore = min(score1, score2)
        return maxScore >= 11 && maxScore - minScore >= 2
    }

    // MARK: - Match Management

    public func startNewMatch() {
        player1Name = "Player 1"
        player2Name = "Player 2"
        currentMatch = MatchRecord(player1Name: player1Name, player2Name: player2Name)
        player1Score = 0
        player2Score = 0
        player1Sets = 0
        player2Sets = 0
        lastTranscript = "New match started"
        saveMatchHistory()
    }

    public func recordSet(player1Score p1Score: Int, player2Score p2Score: Int) {
        if currentMatch == nil {
            currentMatch = MatchRecord(player1Name: player1Name, player2Name: player2Name)
        }

        guard var match = currentMatch else { return }

        match.player1Name = player1Name
        match.player2Name = player2Name

        let setRecord = SetRecord(
            setNumber: match.currentSetNumber,
            player1Score: p1Score,
            player2Score: p2Score
        )

        match.addSet(setRecord)
        currentMatch = match

        player1Sets = match.player1SetCount
        player2Sets = match.player2SetCount
        player1Score = 0
        player2Score = 0

        if match.isComplete {
            completeMatch()
        }
        saveMatchHistory()
    }

    public func completeMatch() {
        guard let match = currentMatch else { return }
        matchHistory.insert(match, at: 0)
        showMatchComplete = true
        saveMatchHistory()
        saveMatchToBackend()
    }

    // MARK: - Recording Control

    public func startRecording() {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionTask?.cancel()
        recognitionTask = nil

        let inputNode = audioEngine.inputNode
        try? inputNode.setVoiceProcessingEnabled(true)

        recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
        guard let recognitionRequest else { return }
        recognitionRequest.shouldReportPartialResults = true
        recognitionRequest.addsPunctuation = true
        recognitionRequest.requiresOnDeviceRecognition = true

        recognitionTask = speechRecognizer?.recognitionTask(with: recognitionRequest) { [weak self] result, error in
            guard let self else { return }
            if let result {
                Task { @MainActor in
                    self.lastTranscript = result.bestTranscription.formattedString
                }
            }
            if error != nil || result?.isFinal == true {
                Task { @MainActor in
                    self.stopAudioEngine()
                }
            }
        }

        let recordingFormat = inputNode.outputFormat(forBus: 0)
        // Capture the request directly — append() is safe to call from the audio thread.
        let capturedRequest = recognitionRequest
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { buffer, _ in
            capturedRequest?.append(buffer)
        }

        audioEngine.prepare()

        do {
            try audioEngine.start()
            withAnimation(.spring(response: 0.4, dampingFraction: 0.6)) {
                self.isRecording = true
                self.isProcessing = false
            }
        } catch {
            print("❌ Could not start audio engine: \(error)")
            stopAudioEngine()
        }
    }

    public func stopRecording() {
        stopAudioEngine()

        withAnimation {
            isRecording = false
            isProcessing = true
        }

        let transcript = lastTranscript
        Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(800))
            self?.sendTranscriptToBackend(text: transcript)
        }
    }

    private func stopAudioEngine() {
        if audioEngine.isRunning {
            audioEngine.stop()
        }
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionRequest?.endAudio()
        recognitionRequest = nil
        recognitionTask = nil
    }

    // MARK: - API Integration

    private func sendTranscriptToBackend(text: String) {
        guard !text.isEmpty else {
            isProcessing = false
            return
        }

        guard let targetURL = URL(string: "\(baseURL)/arcade/process") else {
            isProcessing = false
            return
        }

        var request = URLRequest(url: targetURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["text": text])

        Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let (data, _) = try await URLSession.shared.data(for: request)
                self.isProcessing = false
                self.processBackendResponse(data)
            } catch {
                self.isProcessing = false
                self.lastTranscript = "Network error: \(error.localizedDescription)"
            }
        }
    }

    private func processBackendResponse(_ data: Data) {
        let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]

        guard let response = json,
              let status = response["status"] as? String, status == "success",
              let transcript = response["transcript"] as? String,
              let intent = response["intent"] as? [String: Any] else {
            if let response = json {
                if let errorMsg = response["error"] as? String {
                    lastTranscript = "Server Error: \(errorMsg)"
                } else if let detail = response["detail"] as? String {
                    lastTranscript = "Backend Error: \(detail) (Check URL)"
                } else {
                    lastTranscript = "Invalid Response (Check URL)"
                }
            } else if let raw = String(data: data, encoding: .utf8) {
                print("📄 Raw non-JSON output: \(raw)")
                lastTranscript = "Backend error (not JSON)"
            }
            return
        }

        withAnimation(.spring(response: 0.5, dampingFraction: 0.7)) {
            lastTranscript = transcript
            let messageType = intent["message_type"] as? String ?? "query"

            if messageType == "match_report" {
                if let p1Name = intent["player1_name"] as? String, !p1Name.isEmpty {
                    player1Name = p1Name
                }
                if let p2Name = intent["player2_name"] as? String, !p2Name.isEmpty {
                    player2Name = p2Name
                }
                if let score1 = intent["player1_score"] as? Int,
                   let score2 = intent["player2_score"] as? Int {
                    player1Score = score1
                    player2Score = score2
                    if MatchManager.isValidSetScore(score1: score1, score2: score2) {
                        recordSet(player1Score: score1, player2Score: score2)
                    }
                }
            } else if messageType == "action" {
                if let action = intent["action"] as? String {
                    switch action {
                    case "reset_game":   resetGame()
                    case "finish_set":   finishSet()
                    case "send_message": showSMSSheet = true
                    case "save_match":   saveMatchToBackend()
                    default:             break
                    }
                }
            }
        }
    }

    public func resetGame() {
        player1Score = 0
        player2Score = 0
        player1Sets = 0
        player2Sets = 0
        player1Name = "Player 1"
        player2Name = "Player 2"
        currentMatch = nil
        lastTranscript = "Game reset"
        saveMatchHistory()
    }

    public func finishSet() {
        if MatchManager.isValidSetScore(score1: player1Score, score2: player2Score) {
            recordSet(player1Score: player1Score, player2Score: player2Score)
        } else {
            // Force-record even if scores don't meet strict validation
            if player1Score > player2Score { player1Sets += 1 } else { player2Sets += 1 }
            player1Score = 0
            player2Score = 0
        }
    }

    public func saveMatchToBackend() {
        guard let targetURL = URL(string: "\(baseURL)/arcade/submit_score") else { return }
        var request = URLRequest(url: targetURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let transcript = generateMessageBody()
        let body: [String: Any] = [
            "player1_name": player1Name,
            "player2_name": player2Name,
            "manual_score": "\(player1Sets)-\(player2Sets)",
            "transcript": transcript,
            "date": ISO8601DateFormatter().string(from: Date())
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let (data, _) = try await URLSession.shared.data(for: request)
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let status = json["status"] as? String, status == "success",
                   let confirm = json["confirmation"] as? String, !confirm.isEmpty {
                    withAnimation {
                        self.lastTranscript = "🤖 \(confirm)"
                    }
                }
            } catch {
                print("❌ Save failed: \(error.localizedDescription)")
            }
        }
    }

    public func undoLastSet() -> Bool {
        guard var match = currentMatch, !match.sets.isEmpty else { return false }
        let removedSet = match.sets.removeLast()
        if match.isComplete {
            match.isComplete = false
            match.winner = nil
            matchHistory.removeAll { $0.id == match.id }
            showMatchComplete = false
        }
        currentMatch = match
        player1Sets = match.player1SetCount
        player2Sets = match.player2SetCount
        player1Score = 0
        player2Score = 0
        lastTranscript = "Undid Set \(removedSet.setNumber)"
        saveMatchHistory()
        return true
    }

    public var canUndo: Bool {
        currentMatch?.sets.isEmpty == false
    }

    public func generateMessageBody() -> String {
        if let match = currentMatch {
            var msg = "Match: \(match.player1Name) vs \(match.player2Name)\n"
            msg += "Sets: \(match.player1SetCount)-\(match.player2SetCount)\n"
            for set in match.sets {
                msg += "Set \(set.setNumber): \(set.player1Score)-\(set.player2Score)\n"
            }
            if match.isComplete {
                let winnerName = match.winner == .player1 ? match.player1Name : match.player2Name
                msg += "Winner: \(winnerName)"
            }
            return msg
        }
        return "Current Score: \(player1Name): \(player1Score) - \(player2Name): \(player2Score). Sets: \(player1Sets)-\(player2Sets)."
    }

    // MARK: - Persistence

    public func saveMatchHistory() {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        if let encoded = try? encoder.encode(matchHistory) {
            UserDefaults.standard.set(encoded, forKey: matchHistoryKey)
        }
        if let match = currentMatch, let encoded = try? encoder.encode(match) {
            UserDefaults.standard.set(encoded, forKey: currentMatchKey)
        } else {
            UserDefaults.standard.removeObject(forKey: currentMatchKey)
        }
    }

    public func loadMatchHistory() {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        if let data = UserDefaults.standard.data(forKey: matchHistoryKey),
           let history = try? decoder.decode([MatchRecord].self, from: data) {
            matchHistory = history
        }
        if let data = UserDefaults.standard.data(forKey: currentMatchKey),
           let match = try? decoder.decode(MatchRecord.self, from: data) {
            currentMatch = match
            player1Name = match.player1Name
            player2Name = match.player2Name
            player1Sets = match.player1SetCount
            player2Sets = match.player2SetCount
        }
    }
}
