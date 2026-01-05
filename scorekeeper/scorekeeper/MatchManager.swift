import Foundation
import AVFoundation
import SwiftUI
import Speech

// MARK: - Data Models

enum PlayerSide: String, Codable {
    case player1
    case player2
}

struct SetRecord: Codable, Identifiable {
    let id: UUID
    let setNumber: Int
    let player1Score: Int
    let player2Score: Int
    let winner: PlayerSide
    let timestamp: Date

    init(setNumber: Int, player1Score: Int, player2Score: Int) {
        self.id = UUID()
        self.setNumber = setNumber
        self.player1Score = player1Score
        self.player2Score = player2Score
        self.winner = player1Score > player2Score ? .player1 : .player2
        self.timestamp = Date()
    }
}

struct MatchRecord: Codable, Identifiable {
    let id: UUID
    var player1Name: String
    var player2Name: String
    var sets: [SetRecord]
    var winner: PlayerSide?
    var isComplete: Bool
    var date: Date

    init(player1Name: String, player2Name: String) {
        self.id = UUID()
        self.player1Name = player1Name
        self.player2Name = player2Name
        self.sets = []
        self.winner = nil
        self.isComplete = false
        self.date = Date()
    }

    var player1SetCount: Int {
        sets.filter { $0.winner == .player1 }.count
    }

    var player2SetCount: Int {
        sets.filter { $0.winner == .player2 }.count
    }

    var currentSetNumber: Int {
        sets.count + 1
    }

    mutating func addSet(_ setRecord: SetRecord) {
        sets.append(setRecord)
        checkMatchCompletion()
    }

    mutating func checkMatchCompletion() {
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

class MatchManager: NSObject, ObservableObject, AVAudioRecorderDelegate {
    // MARK: - Game State
    @Published var player1Score = 0
    @Published var player2Score = 0
    @Published var player1Sets = 0
    @Published var player2Sets = 0
    @Published var isRecording = false
    @Published var isProcessing = false
    @Published var lastTranscript = ""
    @Published var showSMSSheet = false
    
    // Dynamic Player Names
    @Published var player1Name = "Player 1"
    @Published var player2Name = "Player 2"
    
    // MARK: - Match Journal State
    @Published var currentMatch: MatchRecord?
    @Published var matchHistory: [MatchRecord] = []
    @Published var showMatchComplete = false
    
    // MARK: - Audio & Speech
    private var audioRecorder: AVAudioRecorder?
    private var recordingSession: AVAudioSession!
    
    // Speech Recognition
    private let speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let audioEngine = AVAudioEngine()
    
    // MARK: - Persistence Keys
    private let matchHistoryKey = "TableTennisMatchHistory"
    private let currentMatchKey = "TableTennisCurrentMatch"
    
    // MARK: - API Configuration
    private var baseURL: String {
        return UserDefaults.standard.string(forKey: "backend_url") ?? "https://omnipong-backend.onrender.com"
    }
    
    override init() {
        super.init()
        setupAudioSession()
        loadMatchHistory()

        // Monitor for audio route changes (e.g., AirPods connected/disconnected)
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleAudioRouteChange),
            name: AVAudioSession.routeChangeNotification,
            object: nil
        )
    }

    @objc private func handleAudioRouteChange(notification: Notification) {
        // Automatically update preferred input when Bluetooth connects/disconnects
        guard let userInfo = notification.userInfo,
              let reasonValue = userInfo[AVAudioSessionRouteChangeReasonKey] as? UInt,
              let reason = AVAudioSession.RouteChangeReason(rawValue: reasonValue) else {
            return
        }

        switch reason {
        case .newDeviceAvailable, .oldDeviceUnavailable:
            // Bluetooth device connected or disconnected - update preferred input
            updatePreferredInput()
        default:
            break
        }
    }

    private func updatePreferredInput() {
        do {
            let availableInputs = recordingSession.availableInputs ?? []
            if let bluetoothInput = availableInputs.first(where: { $0.portType == .bluetoothHFP || $0.portType == .bluetoothA2DP || $0.portType == .bluetoothLE }) {
                try recordingSession.setPreferredInput(bluetoothInput)
                print("🎧 Switched to Bluetooth microphone: \(bluetoothInput.portName)")
            } else {
                try recordingSession.setPreferredInput(nil) // Use system default (built-in)
                print("🎤 Switched to built-in microphone")
            }
        } catch {
            print("⚠️ Failed to update audio input: \(error)")
        }
    }
    
    private func setupAudioSession() {
        recordingSession = AVAudioSession.sharedInstance()
        do {
            // Enable Bluetooth devices (AirPods, etc.) for recording
            // Use voiceChat mode for optimized speech recognition with built-in noise reduction
            // voiceChat mode enables: automatic noise reduction, echo cancellation, voice enhancement
            try recordingSession.setCategory(
                .playAndRecord,
                mode: .voiceChat,
                options: [
                    .allowBluetooth,
                    .allowBluetoothA2DP,
                    .defaultToSpeaker,
                    .duckOthers  // Reduce volume of other audio during recording
                ]
            )

            // Request highest quality input for better speech recognition
            try recordingSession.setPreferredIOBufferDuration(0.005) // Low latency
            try recordingSession.setPreferredSampleRate(44100) // High quality sample rate

            try recordingSession.setActive(true)

            // Set preferred input (Bluetooth if available, otherwise built-in)
            updatePreferredInput()

            print("✅ Audio session configured with built-in noise reduction via .voiceChat mode")
            
            if #available(iOS 17.0, *) {
                AVAudioApplication.requestRecordPermission { allowed in
                    if !allowed {
                        print("Microphone access denied")
                    }
                }
            } else {
                recordingSession.requestRecordPermission { allowed in
                    if !allowed {
                        print("Microphone access denied")
                    }
                }
            }
            
            // Request Speech Recognition Permission
            SFSpeechRecognizer.requestAuthorization { authStatus in
                DispatchQueue.main.async {
                    switch authStatus {
                    case .authorized:
                        print("✅ Speech recognition authorized")
                    case .denied:
                        print("❌ Speech recognition denied")
                    case .restricted:
                        print("❌ Speech recognition restricted")
                    case .notDetermined:
                        print("❌ Speech recognition not determined")
                    @unknown default:
                        print("❓ Unknown speech recognition status")
                    }
                }
            }
        } catch {
            print("Failed to set up audio session: \(error)")
        }
    }

    // MARK: - Table Tennis Validation
    static func isValidSetScore(score1: Int, score2: Int) -> Bool {
        let maxScore = max(score1, score2)
        let minScore = min(score1, score2)
        return maxScore >= 11 && maxScore - minScore >= 2
    }

    // MARK: - Match Management
    func startNewMatch() {
        print("🆕 Starting new match")
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

    func recordSet(player1Score p1Score: Int, player2Score p2Score: Int) {
        if currentMatch == nil {
            currentMatch = MatchRecord(player1Name: player1Name, player2Name: player2Name)
        }

        guard var match = currentMatch else { return }

        // Always update match with current player names
        match.player1Name = player1Name
        match.player2Name = player2Name

        let setRecord = SetRecord(
            setNumber: match.currentSetNumber,
            player1Score: p1Score,
            player2Score: p2Score
        )

        match.addSet(setRecord)
        currentMatch = match

        self.player1Sets = match.player1SetCount
        self.player2Sets = match.player2SetCount
        self.player1Score = 0
        self.player2Score = 0

        print("📊 Recorded Set \(setRecord.setNumber): \(p1Score)-\(p2Score)")

        if match.isComplete {
            completeMatch()
        }
        saveMatchHistory()
    }

    func completeMatch() {
        guard let match = currentMatch else { return }
        print("🏆 Match complete!")
        matchHistory.insert(match, at: 0)
        showMatchComplete = true
        saveMatchHistory()
        
        // Auto-save to backend AI agent
        saveMatch()
    }

    // MARK: - Recording Control
    func startRecording() {
        print("🎤 Starting local speech recognition...")
        
        // Defensive cleanup: ensure previous tap and task are cleared
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        
        recognitionTask?.cancel()
        recognitionTask = nil
        
        let inputNode = audioEngine.inputNode
        recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
        guard let recognitionRequest = recognitionRequest else { return }
        recognitionRequest.shouldReportPartialResults = true
        
        recognitionTask = speechRecognizer?.recognitionTask(with: recognitionRequest) { [weak self] result, error in
            guard let self = self else { return }
            
            if let result = result {
                DispatchQueue.main.async {
                    self.lastTranscript = result.bestTranscription.formattedString
                }
            }
            
            if error != nil || result?.isFinal == true {
                self.stopAudioEngine()
            }
        }
        
        let recordingFormat = inputNode.outputFormat(forBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { buffer, _ in
            self.recognitionRequest?.append(buffer)
        }
        
        audioEngine.prepare()
        
        do {
            try audioEngine.start()
            withAnimation(.spring(response: 0.4, dampingFraction: 0.6)) {
                isRecording = true
                isProcessing = false
            }
        } catch {
            print("❌ Could not start audio engine: \(error)")
            stopAudioEngine()
        }
    }
    
    func stopRecording() {
        print("⏹️ Stopping recording...")
        
        stopAudioEngine()
        
        withAnimation {
            isRecording = false
            isProcessing = true
        }
        
        // Final transcript processing
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { [weak self] in
            guard let self = self else { return }
            self.sendTranscriptToBackend(text: self.lastTranscript)
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
    
    func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        // No longer used for main STT flow but kept for delegate compliance if needed
    }
    
    private func getDocumentsDirectory() -> URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    }
    
    // MARK: - API Integration
    private func sendTranscriptToBackend(text: String) {
        guard !text.isEmpty else {
            isProcessing = false
            return
        }
        
        let targetURL = URL(string: "\(baseURL)/arcade/process")!
        print("🚀 Sending transcript to backend: \(targetURL)")
        var request = URLRequest(url: targetURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: Any] = ["text": text]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                self?.isProcessing = false
                if let error = error {
                    print("❌ Network error: \(error.localizedDescription)")
                    self?.lastTranscript = "Network error: \(error.localizedDescription)"
                    return
                }
                
                if let data = data {
                    self?.processBackendResponse(data)
                }
            }
        }.resume()
    }
    
    private func sendAudioToBackend(url: URL) {
        // Legacy method, no longer used by default
        isProcessing = false
    }
    
    private func processBackendResponse(_ data: Data) {
        let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        
        guard let response = json,
              let status = response["status"] as? String, status == "success",
              let transcript = response["transcript"] as? String,
              let intent = response["intent"] as? [String: Any] else {
            
            print("❌ Failed to parse backend response")
            if let response = json {
                if let errorMsg = response["error"] as? String {
                    print("🛑 Server Error: \(errorMsg)")
                    self.lastTranscript = "Server Error: \(errorMsg)"
                } else if let detail = response["detail"] as? String {
                    print("🛑 Detail: \(detail)")
                    self.lastTranscript = "Backend Error: \(detail) (Check URL)"
                } else {
                    print("⚠️ Response Keys: \(response.keys)")
                    self.lastTranscript = "Invalid Response (Check URL)"
                }
            } else if let raw = String(data: data, encoding: .utf8) {
                print("📄 Raw non-JSON output: \(raw)")
                self.lastTranscript = "Backend error (not JSON)"
            }
            return
        }

        withAnimation(.spring(response: 0.5, dampingFraction: 0.7)) {
            self.lastTranscript = transcript
            let messageType = intent["message_type"] as? String ?? "query"

            if messageType == "match_report" {
                // Update player names
                if let p1Name = intent["player1_name"] as? String, !p1Name.isEmpty {
                    self.player1Name = p1Name
                }
                if let p2Name = intent["player2_name"] as? String, !p2Name.isEmpty {
                    self.player2Name = p2Name
                }

                // Update scores and auto-record if valid set
                if let score1 = intent["player1_score"] as? Int,
                   let score2 = intent["player2_score"] as? Int {
                    self.player1Score = score1
                    self.player2Score = score2

                    // Auto-record set if it's a valid completed set (11+ and win by 2+)
                    if MatchManager.isValidSetScore(score1: score1, score2: score2) {
                        print("✅ Auto-recording valid set: \(score1)-\(score2)")
                        self.recordSet(player1Score: score1, player2Score: score2)
                    }
                }
            } else if messageType == "action" {
                if let action = intent["action"] as? String {
                    switch action {
                    case "reset_game":
                        resetGame()
                    case "finish_set":
                        finishSet()
                    case "send_message":
                        showSMSSheet = true
                    case "save_match":
                        saveMatch()
                    default:
                        print("❓ Unknown action \(action)")
                    }
                }
            }
        }
    }
    
    func resetGame() {
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
    
    func finishSet() {
        if MatchManager.isValidSetScore(score1: player1Score, score2: player2Score) {
            recordSet(player1Score: player1Score, player2Score: player2Score)
        } else {
            // Force finish if AI says so but validation fails locally? 
            // Better to trust validation for match record
            if player1Score > player2Score { player1Sets += 1 } else { player2Sets += 1 }
            player1Score = 0
            player2Score = 0
        }
    }
    
    func saveMatch() {
        print("🚀 Saving match to backend...")
        let targetURL = URL(string: "\(baseURL)/arcade/submit_score")!
        var request = URLRequest(url: targetURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Send a rich transcript so the backend AI can parse it accurately
        let transcript = generateMessageBody()

        let body: [String: Any] = [
            "player1_name": player1Name,
            "player2_name": player2Name,
            "manual_score": "\(player1Sets)-\(player2Sets)", // Send sets won, not current points
            "transcript": transcript,
            "date": ISO8601DateFormatter().string(from: Date())
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                if let error = error { 
                    print("❌ Save failed: \(error.localizedDescription)")
                } else if let data = data {
                    if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let status = json["status"] as? String, status == "success" {
                        print("✅ Match saved successfully to backend/AI agent")
                        if let confirm = json["confirmation"] as? String, !confirm.isEmpty {
                            withAnimation {
                                self?.lastTranscript = "🤖 \(confirm)"
                            }
                        }
                    } else {
                        print("⚠️ Backend reached but save failed or format unexpected")
                    }
                }
            }
        }.resume()
    }

    func undoLastSet() -> Bool {
        guard var match = currentMatch, !match.sets.isEmpty else { return false }
        let removedSet = match.sets.removeLast()
        if match.isComplete {
            match.isComplete = false
            match.winner = nil
            if let index = matchHistory.firstIndex(where: { $0.id == match.id }) {
                matchHistory.remove(at: index)
            }
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

    var canUndo: Bool {
        return currentMatch?.sets.isEmpty == false
    }
    
    func generateMessageBody() -> String {
        if let match = currentMatch {
            var msg = "Match: \(match.player1Name) vs \(match.player2Name)\n"
            msg += "Sets: \(match.player1SetCount)-\(match.player2SetCount)\n"
            for set in match.sets {
                msg += "Set \(set.setNumber): \(set.player1Score)-\(set.player2Score)\n"
            }
            if match.isComplete {
                let winner = match.winner == .player1 ? match.player1Name : match.player2Name
                msg += "Winner: \(winner)"
            }
            return msg
        }
        return "Current Score: \(player1Name): \(player1Score) - \(player2Name): \(player2Score). Sets: \(player1Sets)-\(player2Sets)."
    }

    // MARK: - Persistence
    func saveMatchHistory() {
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

    func loadMatchHistory() {
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
