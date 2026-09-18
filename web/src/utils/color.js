/**
 * Extract a representative accent color from an image URL (cover).
 * Returns { r, g, b, css, soft, deep } or null.
 */
export function extractAccentFromImage(url, { size = 32, samples = 12 } = {}) {
  return new Promise((resolve) => {
    if (!url || typeof window === 'undefined') {
      resolve(null)
      return
    }
    const img = new Image()
    // same-origin cover URLs with token should be fine; avoid tainting
    img.crossOrigin = 'anonymous'
    img.decoding = 'async'
    const done = (val) => resolve(val)
    img.onerror = () => done(null)
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        const w = size
        const h = size
        canvas.width = w
        canvas.height = h
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        if (!ctx) return done(null)
        ctx.drawImage(img, 0, 0, w, h)
        const data = ctx.getImageData(0, 0, w, h).data
        // weighted average, skip near-white / near-black / low-alpha
        let r = 0
        let g = 0
        let b = 0
        let weight = 0
        const step = Math.max(1, Math.floor((w * h) / Math.max(samples * samples, 64)))
        for (let i = 0; i < data.length; i += 4 * step) {
          const ar = data[i]
          const ag = data[i + 1]
          const ab = data[i + 2]
          const aa = data[i + 3]
          if (aa < 200) continue
          const max = Math.max(ar, ag, ab)
          const min = Math.min(ar, ag, ab)
          const lum = (ar * 0.2126 + ag * 0.7152 + ab * 0.0722) / 255
          const sat = max === 0 ? 0 : (max - min) / max
          if (lum < 0.08 || lum > 0.92) continue
          const wgt = 0.35 + sat * 1.4 + (lum > 0.25 && lum < 0.75 ? 0.35 : 0)
          r += ar * wgt
          g += ag * wgt
          b += ab * wgt
          weight += wgt
        }
        if (weight < 1e-3) {
          // fallback: center pixel-ish average without filters
          let rr = 0
          let gg = 0
          let bb = 0
          let n = 0
          for (let i = 0; i < data.length; i += 16) {
            rr += data[i]
            gg += data[i + 1]
            bb += data[i + 2]
            n += 1
          }
          if (!n) return done(null)
          r = rr / n
          g = gg / n
          b = bb / n
        } else {
          r /= weight
          g /= weight
          b /= weight
        }
        r = Math.round(clamp(r, 0, 255))
        g = Math.round(clamp(g, 0, 255))
        b = Math.round(clamp(b, 0, 255))
        // boost saturation a bit for nicer ambience
        const boosted = boostSat(r, g, b, 1.18)
        done({
          r: boosted.r,
          g: boosted.g,
          b: boosted.b,
          css: `rgb(${boosted.r}, ${boosted.g}, ${boosted.b})`,
          soft: `rgba(${boosted.r}, ${boosted.g}, ${boosted.b}, 0.42)`,
          deep: `rgba(${Math.round(boosted.r * 0.35)}, ${Math.round(boosted.g * 0.35)}, ${Math.round(boosted.b * 0.35)}, 0.9)`,
          glow: `rgba(${boosted.r}, ${boosted.g}, ${boosted.b}, 0.55)`,
          // 叠加在强调色之上的可读前景色（白/深取对比更高者）：主题色明度不固定，
          // 播放键这类"实心主题色 + 图标"的元素必须用它，不能写死白或黑。
          on: pickOnColor(boosted.r, boosted.g, boosted.b),
        })
      } catch {
        done(null)
      }
    }
    img.src = url
  })
}

function clamp(n, a, b) {
  return Math.min(b, Math.max(a, n))
}

function boostSat(r, g, b, amount = 1.15) {
  // simple mix away from gray
  const avg = (r + g + b) / 3
  return {
    r: Math.round(clamp(avg + (r - avg) * amount, 0, 255)),
    g: Math.round(clamp(avg + (g - avg) * amount, 0, 255)),
    b: Math.round(clamp(avg + (b - avg) * amount, 0, 255)),
  }
}

/** 相对亮度（WCAG） */
function relativeLuminance(r, g, b) {
  const f = (c) => {
    const v = c / 255
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

/** 在给定底色上取对比度更高的前景色（深色文字用与页面底色同族的 #0B0C10） */
function pickOnColor(r, g, b) {
  const lum = relativeLuminance(r, g, b)
  const onWhite = 1.05 / (lum + 0.05)
  const onDark = (lum + 0.05) / 0.0537
  return onWhite >= onDark ? '#FFFFFF' : '#0B0C10'
}

export function ambientBackground(accent, { dark = true } = {}) {
  if (dark) {
    if (!accent) {
      return {
        background: `
          radial-gradient(120% 80% at 85% 10%, rgba(88, 86, 214, 0.35), transparent 55%),
          radial-gradient(90% 70% at 20% 90%, color-mix(in srgb, var(--sp-ui-primary) 12%, transparent), transparent 50%),
          linear-gradient(180deg, #12141a 0%, #0b0c10 100%)
        `,
      }
    }
    const { r, g, b } = accent
    return {
      background: `
        radial-gradient(120% 90% at 88% 8%, rgba(${r}, ${g}, ${b}, 0.55), transparent 58%),
        radial-gradient(80% 70% at 15% 95%, rgba(${r}, ${g}, ${b}, 0.18), transparent 55%),
        linear-gradient(165deg, rgba(${Math.round(r * 0.22)}, ${Math.round(g * 0.22)}, ${Math.round(b * 0.22)}, 0.95) 0%, #0a0b0f 62%, #07080b 100%)
      `,
    }
  }

  // light mode: soft page-friendly wash, keep accent without forcing a dark stage
  if (!accent) {
    return {
      background: `
        radial-gradient(120% 90% at 90% 0%, color-mix(in srgb, var(--sp-ui-primary) 12%, transparent), transparent 58%),
        radial-gradient(90% 70% at 8% 100%, rgba(64, 128, 255, 0.08), transparent 55%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.92) 0%, rgba(246, 248, 252, 0.98) 100%)
      `,
    }
  }
  const { r, g, b } = accent
  return {
    background: `
      radial-gradient(120% 90% at 92% 0%, rgba(${r}, ${g}, ${b}, 0.22), transparent 60%),
      radial-gradient(80% 70% at 10% 100%, rgba(${r}, ${g}, ${b}, 0.10), transparent 55%),
      linear-gradient(180deg, rgba(255, 255, 255, 0.94) 0%, rgba(246, 248, 252, 0.98) 100%)
    `,
  }
}
