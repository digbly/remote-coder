interface PowChallengeMessage {
  challenge: string
  difficulty: number
}

interface PowSolutionMessage {
  nonce: string
}

const encoder = new TextEncoder()

const BATCH_SIZE = 1024

function hasLeadingZeroNibbles(bytes: Uint8Array, difficulty: number): boolean {
  const wholeBytes = Math.floor(difficulty / 2)
  for (let index = 0; index < wholeBytes; index += 1) {
    if (bytes[index] !== 0) {
      return false
    }
  }
  if (difficulty % 2 === 1 && (bytes[wholeBytes] >> 4) !== 0) {
    return false
  }
  return true
}

self.onmessage = async (event: MessageEvent<PowChallengeMessage>) => {
  const { challenge, difficulty } = event.data
  let base = 0
  for (;;) {
    // Hash a batch concurrently: awaiting one digest at a time is dominated by
    // per-call overhead, so batching cuts wall-clock time substantially.
    const digests = await Promise.all(
      Array.from({ length: BATCH_SIZE }, (_, offset) =>
        crypto.subtle.digest('SHA-256', encoder.encode(`${challenge}${base + offset}`)),
      ),
    )
    for (let offset = 0; offset < BATCH_SIZE; offset += 1) {
      if (hasLeadingZeroNibbles(new Uint8Array(digests[offset]), difficulty)) {
        const solution: PowSolutionMessage = { nonce: String(base + offset) }
        self.postMessage(solution)
        return
      }
    }
    base += BATCH_SIZE
  }
}
