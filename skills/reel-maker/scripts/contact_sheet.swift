import AVFoundation
import AppKit

// usage: sheets.swift <outDir> <video>...
let args = CommandLine.arguments
let outDir = args[1]
let cell: CGFloat = 300
let cols = 4

for path in args[2...] {
    let url = URL(fileURLWithPath: path)
    let asset = AVURLAsset(url: url)
    let dur = CMTimeGetSeconds(asset.duration)
    let gen = AVAssetImageGenerator(asset: asset)
    gen.appliesPreferredTrackTransform = true
    gen.maximumSize = CGSize(width: 600, height: 600)
    gen.requestedTimeToleranceBefore = .positiveInfinity
    gen.requestedTimeToleranceAfter = .positiveInfinity
    let n = min(16, max(4, Int(ceil(dur / 2.0))))
    var imgs: [(Double, CGImage)] = []
    for i in 0..<n {
        let t = dur * (Double(i) + 0.5) / Double(n)
        if let cg = try? gen.copyCGImage(at: CMTime(seconds: t, preferredTimescale: 600), actualTime: nil) {
            imgs.append((t, cg))
        }
    }
    let rows = Int(ceil(Double(imgs.count) / Double(cols)))
    let W = Int(cell) * cols, H = Int(cell) * rows
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: W, pixelsHigh: H, bitsPerSample: 8,
                               samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                               colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    NSColor.black.setFill(); NSRect(x: 0, y: 0, width: W, height: H).fill()
    for (idx, (t, cg)) in imgs.enumerated() {
        let r = idx / cols, c = idx % cols
        let iw = CGFloat(cg.width), ih = CGFloat(cg.height)
        let s = min(cell / iw, cell / ih)
        let w = iw * s, h = ih * s
        let x = CGFloat(c) * cell + (cell - w) / 2
        let y = CGFloat(H) - CGFloat(r + 1) * cell + (cell - h) / 2
        NSImage(cgImage: cg, size: NSSize(width: w, height: h)).draw(in: NSRect(x: x, y: y, width: w, height: h))
        let label = String(format: "%.1fs", t) as NSString
        label.draw(at: NSPoint(x: CGFloat(c) * cell + 6, y: CGFloat(H) - CGFloat(r + 1) * cell + 6),
                   withAttributes: [.foregroundColor: NSColor.yellow, .font: NSFont.boldSystemFont(ofSize: 18),
                                    .backgroundColor: NSColor.black.withAlphaComponent(0.6)])
    }
    NSGraphicsContext.restoreGraphicsState()
    let name = url.deletingPathExtension().lastPathComponent
    let data = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.7])!
    try! data.write(to: URL(fileURLWithPath: "\(outDir)/\(name).jpg"))
    print("\(name) dur=\(String(format: "%.1f", dur)) frames=\(imgs.count)")
}
