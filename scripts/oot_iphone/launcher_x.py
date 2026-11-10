#!/usr/bin/env python3
"""The launcher's Play from a controller: the south face button (✕ on a DualSense, A on an Xbox pad, B on a Switch pad's
layout) presses Play while the launcher shows, once; then the game has the controller (dm/ios/Sources/Launcher.swift).
Run from the repo root: python3 scripts/oot_iphone/launcher_x.py"""
import pathlib, sys
p = pathlib.Path("dm/ios/Sources/Launcher.swift"); s = p.read_text()
if "PadPlayKey" in s: print("already applied"); sys.exit(0)

old = "                    playButton\n"
if s.count(old) != 1: sys.exit("the launcher's playButton line is not as expected; nothing changed")
s = s.replace(old, "                    playButton.background(PadPlayKey(play: play))   // a controller's ✕ / A presses Play too (PadPlayKey)\n")

if "import GameController" not in s:
    if "import SwiftUI\n" not in s: sys.exit("no 'import SwiftUI' line to put 'import GameController' after; nothing changed")
    s = s.replace("import SwiftUI\n", "import SwiftUI\nimport GameController\n", 1)

s = s.rstrip("\n") + """

// A controller's south face button (✕ on a DualSense, A on an Xbox pad) presses Play while the launcher shows, once (Mighty Green Kokiri Kid).
// It takes the button's own pressed handler, not the gamepad's value handler DmGamepad.m sets for the game, and lets go of it when Play is
// pressed or the launcher goes away, so the button does nothing more here once the game starts. Controllers connected while the launcher shows count too.
private struct PadPlayKey: View {
    let play: () -> Void
    var body: some View {
        Color.clear.frame(width: 0, height: 0).accessibilityHidden(true)
            .onAppear { PadPlayKeys.shared.arm(play) }
            .onDisappear { PadPlayKeys.shared.disarm() }
    }
}

@MainActor private final class PadPlayKeys {
    static let shared = PadPlayKeys()
    private var play: (() -> Void)?
    private var observer: NSObjectProtocol?

    func arm(_ p: @escaping () -> Void) {
        play = p
        hookAll()
        if observer == nil {
            observer = NotificationCenter.default.addObserver(forName: .GCControllerDidConnect, object: nil, queue: .main) { _ in
                Task { @MainActor in PadPlayKeys.shared.hookAll() }
            }
        }
    }

    func disarm() {
        play = nil
        for c in GCController.controllers() { c.extendedGamepad?.buttonA.pressedChangedHandler = nil }
        if let o = observer { NotificationCenter.default.removeObserver(o); observer = nil }
    }

    private func hookAll() {
        guard play != nil else { return }
        for c in GCController.controllers() {
            c.extendedGamepad?.buttonA.pressedChangedHandler = { _, _, pressed in
                guard pressed else { return }
                Task { @MainActor in PadPlayKeys.shared.fire() }
            }
        }
    }

    private func fire() {
        guard let p = play else { return }
        disarm()
        p()
    }
}
"""
p.write_text(s)
print("Launcher.swift: a controller's ✕ / A presses Play")
