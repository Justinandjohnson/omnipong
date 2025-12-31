
import Foundation

// --- Mocking parts of MatchManager for testing ---
class MockMatchManager {
    var player1Score = 0
    var player2Score = 0
    var player1Name = "Player 1"
    var player2Name = "Player 2"
    
    // Helper Copied from MatchManager
    func numberWordToInt(_ word: String) -> Int? {
        let formatter = NumberFormatter()
        formatter.numberStyle = .spellOut
        if let number = formatter.number(from: word.lowercased()) {
            return number.intValue
        }
        
        switch word.lowercased() {
        case "zero", "love", "oh", "nil": return 0
        case "one", "won": return 1
        case "two", "to", "too": return 2
        case "three": return 3
        case "four", "for": return 4
        case "five": return 5
        case "six": return 6
        case "seven": return 7
        case "eight": return 8
        case "nine": return 9
        case "ten": return 10
        case "eleven": return 11
        case "twelve": return 12
        case "thirteen": return 13
        case "fourteen": return 14
        case "fifteen": return 15
        default: return Int(word)
        }
    }
    

    // Logic - MIRRORED FROM MatchManager.swift
    func processCommand(_ text: String) {
        print("Test Input: '\(text)'")
        
        let cleanText = text.replacingOccurrences(of: "[,.]", with: "", options: .regularExpression).lowercased()
        
         // 2. Tokenize and Pair (Name, Score)
            // We want to associate a name with the nearest number.
            
            let words = cleanText.components(separatedBy: .whitespaces).filter { !$0.isEmpty }
            
            var pairs: [(name: String, score: Int)] = []
            
            var currentName: String? = nil
            // var currentScore: Int? = nil // Not strictly needed if we process sequentially
            
            // Simple heuristic state machine
            // Try to find "Name ... Number" or "Number ... Name" pattern
            
            var i = 0
            while i < words.count {
                let word = words[i]
                
                // Is it a number?
                if let val = numberWordToInt(word) {
                    // It's a score. Do we have a pending name?
                    if let name = currentName {
                        // Found Pair: Name -> Score
                        pairs.append((name, val))
                        currentName = nil
                    } else {
                        // Score first? Look ahead for name? OR Look behind?
                        // "10 for John" -> 10, for, John.
                        // Let's assume Score is start of a segment if no name pending.
                        // We hold this score and look for a name in next few tokens?
                        // Or simplistic: Just grab lists like before but map them index-wise?
                        // No, map index-wise is what failed.
                        
                        // Let's try to look forward for a name.
                        var foundNameForward = false
                        for j in (i+1)..<min(i+3, words.count) {
                            let nextWord = words[j]
                            if numberWordToInt(nextWord) == nil && !isFiller(nextWord) {
                                // Found a name associated with this score
                                pairs.append((nextWord.capitalized, val))
                                i = j // Skip to name
                                foundNameForward = true
                                break
                            }
                        }
                        
                        if !foundNameForward {
                            // Lone score? Maybe implicit player order?
                            // Store with explicit nil name
                            pairs.append(("", val))
                        }
                    }
                } else {
                    // Not a number. Is it a name?
                    if !isFiller(word) {
                        currentName = word.capitalized
                    }
                }
                i += 1
            }
            
            // Apply Pairs to State
            for pair in pairs {
                updateScoreFor(name: pair.name, score: pair.score)
            }
            
            // Fallback for simple "10 5" (two unnamed scores)
            // If we have exactly 2 pairs with empty names, assume P1 then P2
            let emptyNamePairs = pairs.filter { $0.name.isEmpty }
            if emptyNamePairs.count == 2 && pairs.count == 2 {
                player1Score = emptyNamePairs[0].score
                player2Score = emptyNamePairs[1].score
            }
    }
    
    func isFiller(_ word: String) -> Bool {
        return ["score", "point", "points", "for", "and", "is", "at", "to", "versus", "vs"].contains(word)
    }
    
    func updateScoreFor(name: String, score: Int) {
        if name.isEmpty { return }
        
        // 1. Try to match existing players
        if name.lowercased() == player1Name.lowercased() {
            player1Score = score
            return
        }
        if name.lowercased() == player2Name.lowercased() {
            player2Score = score
            return
        }
        
        // 2. No direct match.
        // If "Player 1" is generic, take it.
        if player1Name == "Player 1" {
            player1Name = name
            player1Score = score
            return
        }
        // If "Player 2" is generic, take it.
        if player2Name == "Player 2" {
            player2Name = name
            player2Score = score
            return
        }
        
        print("⚠️ Name '\(name)' matches neither \(player1Name) nor \(player2Name). Ignoring update.")
    }

}

// --- Tests ---
let manager = MockMatchManager()

// Test 1: "John 10, Justin 5"
manager.processCommand("John 10, Justin 5")
print("Result 1: \(manager.player1Name) \(manager.player1Score), \(manager.player2Name) \(manager.player2Score)")
assert(manager.player1Name == "John")
assert(manager.player1Score == 10)
assert(manager.player2Name == "Justin")
assert(manager.player2Score == 5)

// Test 2: "Justin 6, John 10" (Swap detected?) - Note: logic currently doesn't strictly swap, but updates.
// If P1 is John, "Justin" != "John" and != "Justin" (P2 is Justin).
// If `processCommand` receives "Justin 6, John 10"
// p1Name=Justin, p1Score=6, p2Name=John, p2Score=10
// Logic:
// P1 (John) != NewP1 (Justin). NewP1 (Justin) == P2 (Justin)? Yes (if previous state held).
// Wait, my logic: `if p1Name != player2Name { player1Name = p1Name }`
// "Justin" == "Justin" (P2). So P1 name NOT updated to Justin. Correct.
// P2 (Justin) != NewP2 (John). NewP2 (John) == P1? Yes. So P2 name NOT updated. Correct...?
// Wait, if I just update scores, names shouldn't flip-flop erratically unless intended.
// My logic prevents P1 from becoming P2's name, but doesn't explicitly SWAP the score buckets.
// If "Justin 6, John 10" comes in, I call updateMatchWith(n1=Justin, s1=6, n2=John, s2=10)
// This assigns s1 (6) to player1Score. But Player 1 is John! FAILURE in logic if we want smart swap.
// The current logic assigns the scores based on ORDER in the string to P1/P2 slots, 
// only names are protected.
// This means "Justin 6" -> assigns 6 to Player 1 (who is John).
// I need verification to catch this.

print("\n--- Running Test 2 (Swap) ---")
manager.processCommand("Justin 6, John 11")
print("Result 2: \(manager.player1Name) \(manager.player1Score), \(manager.player2Name) \(manager.player2Score)")

// Test 3: Number words match
print("\n--- Running Test 3 (Number Words) ---")
manager.processCommand("John ten, Justin five")
print("Result 3: \(manager.player1Score) - \(manager.player2Score)")
assert(manager.player1Score == 10)
assert(manager.player2Score == 5)

print("\n✅ All Tests Passed")
