import PowWorker from './powWorker?worker'

export interface PowChallenge {
  algorithm: string
  challenge: string
  difficulty: number
}

interface PowWorkerMessage {
  nonce: string
}

const POW_TIMEOUT_MS = 60_000

export function solvePowChallenge(challenge: PowChallenge): Promise<string> {
  return new Promise((resolve, reject) => {
    if (challenge.algorithm !== 'sha256') {
      reject(new Error(`Unsupported proof-of-work algorithm: ${challenge.algorithm}`))
      return
    }

    const worker = new PowWorker()
    const timer = setTimeout(() => {
      worker.terminate()
      reject(new Error('Proof-of-work timed out'))
    }, POW_TIMEOUT_MS)
    const settle = (callback: () => void) => {
      clearTimeout(timer)
      worker.terminate()
      callback()
    }

    worker.onmessage = (event: MessageEvent<PowWorkerMessage>) => {
      settle(() => resolve(event.data.nonce))
    }
    worker.onerror = () => {
      settle(() => reject(new Error('Proof-of-work worker failed')))
    }

    worker.postMessage({ challenge: challenge.challenge, difficulty: challenge.difficulty })
  })
}
