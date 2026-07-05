// 页面还原导出工具：零依赖方案（生产环境健壮版）
// 关键点：
//  1) 样式：Vite 生产会给 <link> 加 crossorigin，导致 styleSheet.cssRules 抛 SecurityError。
//     故改为 fetch 样式文本内联，并把相对 url() 重写为绝对地址，保证离线还原。
//  2) 图表：不再依赖 canvas.toDataURL（易受 dpr/图层影响得到空白），改用 ECharts 官方
//     实例 getDataURL()，由 echarts.getInstanceByDom 从容器取实例。

interface ExportOptions {
  title: string
  filename: string
}

// 把 CSS 文本中的相对 url(...) 重写为基于样式表地址的绝对 URL（字体/图片等）
function rewriteCssUrls(cssText: string, baseHref: string): string {
  return cssText.replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/g, (match, quote: string, url: string) => {
    if (/^(data:|https?:|\/\/|#)/.test(url)) return match
    try {
      const abs = new URL(url, baseHref).href
      return `url(${quote}${abs}${quote})`
    } catch {
      return match
    }
  })
}

// 收集全部样式：外链样式表 fetch 文本内联 + 运行时 <style> 内容
async function collectCss(): Promise<string> {
  const parts: string[] = []

  const links = Array.from(document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]'))
  for (const link of links) {
    if (!link.href) continue
    try {
      const res = await fetch(link.href)
      if (res.ok) {
        const text = await res.text()
        parts.push(rewriteCssUrls(text, link.href))
      }
    } catch {
      // 网络/CORS 失败则跳过该表
    }
  }

  for (const style of Array.from(document.querySelectorAll('style'))) {
    if (style.textContent) parts.push(style.textContent)
  }

  return parts.join('\n')
}

// 用 ECharts 实例把克隆节点内的图表容器替换为 PNG 图片，保证还原
async function snapshotCharts(root: HTMLElement, clone: HTMLElement): Promise<void> {
  const echarts = await import('echarts')
  const srcContainers = Array.from(root.querySelectorAll<HTMLElement>('[_echarts_instance_]'))
  const cloneContainers = Array.from(clone.querySelectorAll<HTMLElement>('[_echarts_instance_]'))

  srcContainers.forEach((container, i) => {
    const target = cloneContainers[i]
    if (!target) return

    let url = ''
    const inst = echarts.getInstanceByDom(container)
    if (inst) {
      url = inst.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: 'transparent' })
    } else {
      const canvas = container.querySelector('canvas')
      if (canvas) {
        try {
          url = canvas.toDataURL('image/png')
        } catch {
          url = ''
        }
      }
    }

    const w = container.clientWidth
    const h = container.clientHeight
    const img = document.createElement('img')
    img.src = url
    img.style.width = w ? `${w}px` : '100%'
    img.style.height = h ? `${h}px` : 'auto'
    img.style.display = 'block'

    target.innerHTML = ''
    target.appendChild(img)
  })
}

// 固化表单控件当前值（cloneNode 不会写入 select 的选中状态）
function persistFormState(root: HTMLElement, clone: HTMLElement): void {
  const srcSelects = Array.from(root.querySelectorAll('select'))
  const cloneSelects = Array.from(clone.querySelectorAll('select'))
  cloneSelects.forEach((sel, i) => {
    const src = srcSelects[i]
    if (!src) return
    for (const opt of Array.from(sel.querySelectorAll('option'))) {
      if (opt.value === src.value) opt.setAttribute('selected', 'selected')
      else opt.removeAttribute('selected')
    }
  })
}

/**
 * 将指定 DOM 节点还原导出为自包含 HTML 文件。
 * @param root  需要导出的根节点（页面主容器）
 * @param opts  标题与文件名
 */
export async function exportNodeAsHtml(root: HTMLElement, opts: ExportOptions): Promise<void> {
  const css = await collectCss()

  const clone = root.cloneNode(true) as HTMLElement
  await snapshotCharts(root, clone)
  persistFormState(root, clone)

  const now = new Date().toLocaleString('zh-CN')
  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${opts.title}</title>
<style>${css}</style>
<style>
  html, body { background: #faf8f5; margin: 0; padding: 24px; }
  .__export_meta { font-family: ui-monospace, monospace; font-size: 12px; color: #6b7280; margin-bottom: 16px; }
  * { cursor: default !important; }
  @media print {
    html, body { padding: 0; background: #fff; }
    .__export_meta { display: none; }
  }
</style>
</head>
<body>
<div class="__export_meta">${opts.title} · 导出时间 ${now} · 提示：可在浏览器中按 Ctrl/Cmd+P 另存为 PDF</div>
${clone.outerHTML}
</body>
</html>`

  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = opts.filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}
