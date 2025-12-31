import SwiftUI
import MessageUI

struct SMSView: UIViewControllerRepresentable {
    var recipients: [String]
    var messageBody: String
    var completion: ((MessageComposeResult) -> Void)?
    
    func makeUIViewController(context: Context) -> MFMessageComposeViewController {
        let controller = MFMessageComposeViewController()
        controller.body = messageBody
        controller.recipients = recipients
        controller.messageComposeDelegate = context.coordinator
        return controller
    }
    
    func updateUIViewController(_ uiViewController: MFMessageComposeViewController, context: Context) {}
    
    func makeCoordinator() -> Coordinator {
        Coordinator(completion: completion)
    }
    
    class Coordinator: NSObject, MFMessageComposeViewControllerDelegate {
        var completion: ((MessageComposeResult) -> Void)?
        
        init(completion: ((MessageComposeResult) -> Void)?) {
            self.completion = completion
        }
        
        func messageComposeViewController(_ controller: MFMessageComposeViewController, didFinishWith result: MessageComposeResult) {
            completion?(result)
            controller.dismiss(animated: true)
        }
    }
}
