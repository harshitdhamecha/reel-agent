import AppKit
// usage: grid <out.jpg> <image>...
let args = CommandLine.arguments
let out = args[1]
let cell: CGFloat = 360
let paths = Array(args[2...])
let cols = 4
let rows = Int(ceil(Double(paths.count) / Double(cols)))
let W = Int(cell) * cols, H = Int(cell) * rows
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: W, pixelsHigh: H, bitsPerSample: 8,
                           samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                           colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
NSColor.black.setFill(); NSRect(x: 0, y: 0, width: W, height: H).fill()
for (i, p) in paths.enumerated() {
    guard let img = NSImage(contentsOfFile: p) else { continue }
    let r = i / cols, c = i % cols
    let s = min(cell / img.size.width, cell / img.size.height)
    let w = img.size.width * s, h = img.size.height * s
    let x = CGFloat(c) * cell + (cell - w) / 2
    let y = CGFloat(H) - CGFloat(r + 1) * cell + (cell - h) / 2
    img.draw(in: NSRect(x: x, y: y, width: w, height: h))
    let label = (URL(fileURLWithPath: p).lastPathComponent) as NSString
    label.draw(at: NSPoint(x: CGFloat(c) * cell + 6, y: CGFloat(H) - CGFloat(r + 1) * cell + 6),
               withAttributes: [.foregroundColor: NSColor.yellow, .font: NSFont.boldSystemFont(ofSize: 18),
                                .backgroundColor: NSColor.black.withAlphaComponent(0.6)])
}
NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .jpeg, properties: [.compressionFactor: 0.7])!.write(to: URL(fileURLWithPath: out))
print("ok", paths.count)
