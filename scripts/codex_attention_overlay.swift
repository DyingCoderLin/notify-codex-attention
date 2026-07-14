import AppKit

final class ClickView: NSVisualEffectView {
    var onClick: (() -> Void)?

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        true
    }

    override func mouseDown(with event: NSEvent) {
        onClick?()
    }

    override func resetCursorRects() {
        addCursorRect(bounds, cursor: .pointingHand)
    }
}

func argument(_ name: String, default fallback: String) -> String {
    guard let index = CommandLine.arguments.firstIndex(of: name),
          CommandLine.arguments.indices.contains(index + 1) else {
        return fallback
    }
    return CommandLine.arguments[index + 1]
}

func label(_ text: String, size: CGFloat, weight: NSFont.Weight, color: NSColor, lines: Int = 1) -> NSTextField {
    let field = NSTextField(labelWithString: text)
    field.font = .systemFont(ofSize: size, weight: weight)
    field.textColor = color
    field.lineBreakMode = lines == 1 ? .byTruncatingTail : .byWordWrapping
    field.maximumNumberOfLines = lines
    return field
}

let titleText = argument("--title", default: "Codex")
let subtitleText = argument("--subtitle", default: "需要你处理")
let messageText = argument("--message", default: "Codex 需要你返回处理当前任务")
let iconPath = argument("--icon", default: "/Applications/ChatGPT.app/Contents/Resources/icon-codex-dark-color.png")
let activateBundle = argument("--activate", default: "com.googlecode.iterm2")
let group = argument("--group", default: "current").replacingOccurrences(
    of: "[^0-9A-Za-z_-]",
    with: "-",
    options: .regularExpression
)
let timeout = Double(argument("--timeout", default: "18")) ?? 18

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

let dismissName = Notification.Name("com.openai.codex-attention.dismiss.\(group)")
DistributedNotificationCenter.default().post(
    name: dismissName,
    object: nil,
    userInfo: nil
)
let dismissObserver = DistributedNotificationCenter.default().addObserver(
    forName: dismissName,
    object: nil,
    queue: .main
) { _ in
    app.terminate(nil)
}

let panelSize = NSSize(width: 390, height: 122)
let panel = NSPanel(
    contentRect: NSRect(origin: .zero, size: panelSize),
    styleMask: [.borderless, .nonactivatingPanel],
    backing: .buffered,
    defer: false
)
panel.level = .floating
panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
panel.isOpaque = false
panel.backgroundColor = .clear
panel.hasShadow = true
panel.hidesOnDeactivate = false
panel.ignoresMouseEvents = false
panel.becomesKeyOnlyIfNeeded = true

let card = ClickView(frame: NSRect(origin: .zero, size: panelSize))
card.material = .hudWindow
card.blendingMode = .behindWindow
card.state = .active
card.wantsLayer = true
card.layer?.cornerRadius = 16
card.layer?.masksToBounds = true
panel.contentView = card

let icon = NSImageView()
icon.translatesAutoresizingMaskIntoConstraints = false
icon.imageScaling = .scaleProportionallyUpOrDown
icon.image = NSImage(contentsOfFile: iconPath) ?? NSWorkspace.shared.icon(forFile: "/Applications/ChatGPT.app")

let title = label(titleText, size: 14, weight: .bold, color: .labelColor)
let subtitle = label(subtitleText, size: 12, weight: .semibold, color: .secondaryLabelColor)
let body = label(messageText, size: 13, weight: .regular, color: .labelColor, lines: 2)

let textStack = NSStackView(views: [title, subtitle, body])
textStack.translatesAutoresizingMaskIntoConstraints = false
textStack.orientation = .vertical
textStack.alignment = .leading
textStack.spacing = 5

card.addSubview(icon)
card.addSubview(textStack)
NSLayoutConstraint.activate([
    icon.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 16),
    icon.centerYAnchor.constraint(equalTo: card.centerYAnchor),
    icon.widthAnchor.constraint(equalToConstant: 50),
    icon.heightAnchor.constraint(equalToConstant: 50),
    textStack.leadingAnchor.constraint(equalTo: icon.trailingAnchor, constant: 14),
    textStack.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -16),
    textStack.centerYAnchor.constraint(equalTo: card.centerYAnchor),
])

card.onClick = {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
    process.arguments = ["-b", activateBundle]
    try? process.run()
    app.terminate(nil)
}

let mouse = NSEvent.mouseLocation
let screen = NSScreen.screens.first { NSMouseInRect(mouse, $0.frame, false) }
    ?? NSScreen.main
    ?? NSScreen.screens.first!
let visible = screen.visibleFrame
panel.setFrameOrigin(NSPoint(
    x: visible.maxX - panelSize.width - 18,
    y: visible.maxY - panelSize.height - 18
))
panel.alphaValue = 0
panel.orderFrontRegardless()
NSAnimationContext.runAnimationGroup { context in
    context.duration = 0.18
    panel.animator().alphaValue = 1
}

Timer.scheduledTimer(withTimeInterval: timeout, repeats: false) { _ in
    app.terminate(nil)
}
app.run()
DistributedNotificationCenter.default().removeObserver(dismissObserver)
