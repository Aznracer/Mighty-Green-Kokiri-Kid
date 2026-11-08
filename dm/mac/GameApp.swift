// The game as an app of its own (Contents/Helpers/Game.app, dm/mac/pack_app.py), started through LaunchServices. A host the launcher started with posix_spawn was an anonymous
// process to macOS (anon<dmhost> in gamepolicyd's log): its window, its GPU work and Game Mode never met an app, whatever the bundle's LSSupportsGameMode said, and the host that
// replaced the launcher with execv was taken for the app's exit (RunningBoard: none-NotVisible). Started this way it is an app with its own identity, which Game Mode can take.
// launcher.c calls this after the settings window, with the environment it built (setenv) and the host's argument, and waits for the pid it returns to exit
import AppKit

@_cdecl("dm_launch_game_app")
public func dm_launch_game_app(_ app: UnsafePointer<CChar>, _ arg: UnsafePointer<CChar>) -> Int32 {
    let cfg = NSWorkspace.OpenConfiguration()
    cfg.arguments = [String(cString: arg)]
    var env: [String: String] = [:]
    var p = environ
    while let kv = p.pointee {   // the launcher's environment as it is now: setenv after the start is not in ProcessInfo's copy
        let s = String(cString: kv)
        if let eq = s.firstIndex(of: "=") {
            let k = String(s[..<eq])
            if !k.hasPrefix("__CF") && !k.hasPrefix("XPC_") { env[k] = String(s[s.index(after: eq)...]) }   // the launcher's own LaunchServices identity is not the game's
        }
        p += 1
    }
    cfg.environment = env
    cfg.createsNewApplicationInstance = true
    cfg.activates = true
    cfg.addsToRecentItems = false
    cfg.promptsUserIfNeeded = false
    NSApplication.shared.setActivationPolicy(.accessory)   // one Dock icon while playing: the game's
    let done = DispatchSemaphore(value: 0)
    var pid: Int32 = -1
    var failure: String?
    NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: String(cString: app)), configuration: cfg) { running, error in
        pid = running?.processIdentifier ?? -1
        failure = error?.localizedDescription
        done.signal()
    }
    let limit = Date().addingTimeInterval(60)   // the main run loop turns while waiting, in case LaunchServices answers through it
    while done.wait(timeout: .now()) == .timedOut {
        if Date() > limit { failure = "no answer from LaunchServices in 60 s"; break }
        RunLoop.main.run(until: Date().addingTimeInterval(0.02))
    }
    if let f = failure { fputs("launcher: the game app did not start: \(f)\n", stderr) }
    return pid
}
