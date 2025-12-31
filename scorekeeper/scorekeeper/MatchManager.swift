import Foundation
import AVFoundation
import SwiftUI

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
    
    // MARK: - Audio
    private var audioRecorder: AVAudioRecorder?
    private var recordingSession: AVAudioSession!
    
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
    }
    
    private func setupAudioSession() {
        recordingSession = AVAudioSession.sharedInstance()
        do {
            try recordingSession.setCategory(.playAndRecord, mode: .default)
            try recordingSession.setActive(true)
            
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

        if player1Name != "Player 1" { match.player1Name = player1Name }
        if player2Name != "Player 2" { match.player2Name = player2Name }

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
        print("🎤 Starting recording...")
        let audioFilename = getDocumentsDirectory().appendingPathComponent("recording.m4a")
        let settings = [
            AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey: 12000,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
        ]
        do {
            audioRecorder = try AVAudioRecorder(url: audioFilename, settings: settings)
            audioRecorder?.delegate = self
            audioRecorder?.record()
            withAnimation(.spring(response: 0.4, dampingFraction: 0.6)) {
                isRecording = true
            }
        } catch {
            print("❌ Could not start recording: \(error)")
        }
    }
    
    func stopRecording() {
        print("⏹️ Stopping recording...")
        audioRecorder?.stop()
        withAnimation {
            isRecording = false
            isProcessing = true
        }
    }
    
    func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        if flag {
            let audioFilename = getDocumentsDirectory().appendingPathComponent("recording.m4a")
            sendAudioToBackend(url: audioFilename)
        } else {
            isProcessing = false
        }
        audioRecorder = nil
    }
    
    private func getDocumentsDirectory() -> URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    }
    
    // MARK: - API Integration
    private func sendAudioToBackend(url: URL) {
        guard let data = try? Data(contentsOf: url) else {
            isProcessing = false
            return
        }
        
        let targetURL = URL(string: "\(baseURL)/arcade/transcribe")!
        print("🚀 Sending audio to backend: \(targetURL)")
        var request = URLRequest(url: targetURL)
        request.httpMethod = "POST"
        
        let boundary = "Boundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"recording.m4a\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: audio/m4a\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                self?.isProcessing = false
                if let error = error {
                    print("❌ Network error: \(error.localizedDescription)")
                    self?.lastTranscript = "Network error: \(error.localizedDescription)"
                    return
                }
                
                if let data = data {
                    if let rawResponse = String(data: data, encoding: .utf8) {
                        print("📡 Raw Response: \(rawResponse)")
                    }
                    self?.processBackendResponse(data)
                }
            }
        }.resume()
    }
    
    private func processBackendResponse(_ data: Data) {
        let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        
        guard let response = json,
              let status = response["status"] as? String, status == "success",
              let transcript = response["transcript"] as? String,
              let intent = response["intent"] as? [String: Any] else {
            
            print("❌ Failed to parse backend response")
            if let response = json {
                if let error = response["error"] as? String {
                    print("🛑 Server Error: \(error)")
                    self.lastTranscript = "Server Error: \(error)"
                } else {
                    print("⚠️ Response Keys: \(response.keys)")
                    self.lastTranscript = "Invalid Backend Response"
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
                if let score1 = intent["user_score"] as? Int,
                   let score2 = intent["opponent_score"] as? Int {
                    // Update live scores
                    self.player1Score = score1
                    self.player2Score = score2
                }
                if let name = intent["opponent_name"] as? String {
                    if self.player2Name == "Player 2" || name.lowercased() == self.player2Name.lowercased() {
                        self.player2Name = name
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
            "opponent_name": player2Name,
            "manual_score": "\(player1Sets)-\(player2Sets)", // Send sets won, not current points
            "transcript": transcript,
            "date": ISO8601DateFormatter().string(from: Date()).prefix(10)
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error { 
                print("❌ Save failed: \(error.localizedDescription)")
            } else {
                print("✅ Match saved successfully to backend/AI agent")
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
