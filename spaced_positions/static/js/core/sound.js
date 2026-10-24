// Sound (spec 05 · Sound, off by default: Settings → Sound and motion): a short click on a move, a soft tone on a
// correct answer, a low one on a wrong answer, a chord on a record. Made with WebAudio, so there are no files.

let audio = null

const enabled = () => window.SPOS.settings?.["sound.on"] === true

function tone(freq, { at = 0, length = 0.12, type = "sine", gain = 0.06 } = {}) {
  const now = audio.currentTime + at
  const osc = audio.createOscillator()
  const env = audio.createGain()
  osc.type = type
  osc.frequency.value = freq
  env.gain.setValueAtTime(0, now)
  env.gain.linearRampToValueAtTime(gain, now + 0.005)
  env.gain.exponentialRampToValueAtTime(0.0001, now + length)
  osc.connect(env).connect(audio.destination)
  osc.start(now)
  osc.stop(now + length + 0.02)
}

const SOUNDS = {
  move: () => tone(1400, { length: 0.035, type: "square", gain: 0.025 }),
  capture: () => tone(950, { length: 0.06, type: "square", gain: 0.04 }),
  good: () => { tone(660, { length: 0.12 }); tone(880, { at: 0.09, length: 0.18 }) },
  bad: () => tone(196, { length: 0.3, type: "triangle", gain: 0.08 }),
  record: () => [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => tone(f, { at: i * 0.05, length: 0.6, gain: 0.04 })),
}

/** Play one of the sounds, if sounds are on. */
export function sound(kind) {
  if (!enabled() || !SOUNDS[kind]) return
  try {
    audio ||= new AudioContext()
    if (audio.state === "suspended") audio.resume()
    SOUNDS[kind]()
  } catch {
    // no audio here (a browser without WebAudio, or no device): stay quiet
  }
}
