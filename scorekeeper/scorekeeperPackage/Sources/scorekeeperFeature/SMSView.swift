import SwiftUI
import MessageUI

public struct SMSView: UIViewControllerRepresentable {
    public var recipients: [String]
    public var messageBody: String
    public var completion: (@MainActor (MessageComposeResult) -> Void)?

    public init(recipients: [String], messageBody: String, completion: (@MainActor (MessageComposeResult) -> Void)? = nil) {
        self.recipients = recipients
        self.messageBody = messageBody
        self.completion = completion
    }

    public func makeUIViewController(context: Context) -> MFMessageComposeViewController {
        let controller = MFMessageComposeViewController()
        controller.body = messageBody
        controller.recipients = recipients
        controller.messageComposeDelegate = context.coordinator
        return controller
    }

    public func updateUIViewController(_ uiViewController: MFMessageComposeViewController, context: Context) {}

    public func makeCoordinator() -> Coordinator {
        Coordinator(completion: completion)
    }

    public final class Coordinator: NSObject, MFMessageComposeViewControllerDelegate {
        var completion: (@MainActor (MessageComposeResult) -> Void)?

        init(completion: (@MainActor (MessageComposeResult) -> Void)?) {
            self.completion = completion
        }

        public func messageComposeViewController(
            _ controller: MFMessageComposeViewController,
            didFinishWith result: MessageComposeResult
        ) {
            let cb = completion
            controller.dismiss(animated: true) {
                if let cb {
                    Task { @MainActor in cb(result) }
                }
            }
        }
    }
}
