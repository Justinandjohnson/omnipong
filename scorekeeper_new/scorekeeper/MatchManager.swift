import Foundation
import AVFoundation
import SwiftUI


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
    
    // MARK: - Audio
    private var audioRecorder: AVAudioRecorder?
    private var recordingSession: AVAudioSession!
    
    // MARK: - API Configuration
    private var baseURL: String {
        // Change this to your production URL when deployed
        return UserDefaults.standard.string(forKey: "backend_url") ?? "http://localhost:8000"
    }
    
    override init() {
        super.init()
        setupAudioSession()
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
    
    // MARK: - Recording Control
    func startRecording() {
        print("🎤 Starting recording...")
        let audioFilename = getDocumentsDirectory().appendingPathComponent("recording.m4a")

        // Define settings for high-quality voice recording
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

            print("✅ Recording started at: \(audioFilename.path)")

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
        // processing continues in delegate
        withAnimation {
            isRecording = false
            isProcessing = true
        }
    }
    
    // MARK: - AVAudioRecorderDelegate
    func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        if flag {
            print("✅ Recording finished successfully")
            let audioFilename = getDocumentsDirectory().appendingPathComponent("recording.m4a")
            sendAudioToBackend(url: audioFilename)
        } else {
            print("❌ Recording failed")
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
            print("❌ Failed to load audio data")
            isProcessing = false
            return
        }

        print("🚀 Sending audio to backend: \(baseURL)/arcade/transcribe")
        
        let targetURL = URL(string: "\(baseURL)/arcade/transcribe")!
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
                    return
                }

                guard let data = data else {
                    print("❌ No data received from backend")
                    return
                }

                if let jsonString = String(data: data, encoding: .utf8) {
                    print("📝 Backend Response: \(jsonString)")
                }

                self?.processBackendResponse(data)
            }
        }.resume()
    }
    
    private func processBackendResponse(_ data: Data) {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let status = json["status"] as? String, status == "success",
              let transcript = json["transcript"] as? String,
              let intent = json["intent"] as? [String: Any] else {
            print("❌ Failed to parse backend response")
            return
        }

        withAnimation(.spring(response: 0.5, dampingFraction: 0.7)) {
            self.lastTranscript = transcript
            
            let messageType = intent["message_type"] as? String ?? "query"
            
            if messageType == "match_report" {
                print("📊 Backend: Match Report")
                
                // Update player 1
                if let score = intent["user_score"] as? Int {
                    self.player1Score = score
                }
                
                // Update player 2
                if let name = intent["opponent_name"] as? String {
                    if self.player2Name == "Player 2" || name.lowercased() == self.player2Name.lowercased() {
                        self.player2Name = name
                    }
                }
                if let score = intent["opponent_score"] as? Int {
                    self.player2Score = score
                }
            } else if messageType == "action" {
                if let action = intent["action"] as? String {
                    switch action {
                    case "reset_game":
                        print("🔄 Backend: Reset game")
                        resetGame()
                    case "finish_set":
                        print("🏁 Backend: Finish set")
                        finishSet()
                    case "send_message":
                        print("📱 Backend: Send message")
                        showSMSSheet = true
                    case "save_match":
                        print("💾 Backend: Save match")
                        saveMatch()
                    default:
                        print("❓ Backend: Unknown action \(action)")
                    }
                }
            } else {
                print("❓ Backend returned query: \(messageType)")
            }
        }
    }
    
    func resetGame() {
        player1Score = 0
        player2Score = 0
        player1Sets = 0
        player2Sets = 0
        // Optional: Reset names? Maybe keep them.
        // player1Name = "Player 1"
        // player2Name = "Player 2"
    }
    
    func finishSet() {
        if player1Score > player2Score {
            player1Sets += 1
        } else if player2Score > player1Score {
            player2Sets += 1
        }
        player1Score = 0
        player2Score = 0
    }
    
    func saveMatch() {
        print("🚀 Saving match to backend...")
        
        let targetURL = URL(string: "\(baseURL)/arcade/submit_score")!
        var request = URLRequest(url: targetURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: Any] = [
            "opponent_name": player2Name,
            "manual_score": "\(player1Score)-\(player2Score)",
            "date": ISO8601DateFormatter().string(from: Date()).prefix(10) // YYYY-MM-DD
        ]
        
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                print("❌ Save failed: \(error.localizedDescription)")
                return
            }
            print("✅ Match saved successfully")
        }.resume()
    }
    
    func generateMessageBody() -> String {
        return "Current Score: \(player1Name): \(player1Score) - \(player2Name): \(player2Score). Sets: \(player1Sets)-\(player2Sets)."
    }
}

