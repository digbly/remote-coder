import { loader } from '@monaco-editor/react'

let monacoPromise: Promise<void> | null = null

async function setupMonaco(): Promise<void> {
  // monaco-editor 0.57 maps `./*` to `./esm/vs/*.js` in its package exports, so
  // worker subpaths must omit the `esm/vs` prefix to resolve.
  const [monaco, editorWorker, cssWorker, htmlWorker, jsonWorker, tsWorker] = await Promise.all([
    import('monaco-editor'),
    import('monaco-editor/editor/editor.worker?worker'),
    import('monaco-editor/language/css/css.worker?worker'),
    import('monaco-editor/language/html/html.worker?worker'),
    import('monaco-editor/language/json/json.worker?worker'),
    import('monaco-editor/language/typescript/ts.worker?worker'),
  ])

  self.MonacoEnvironment = {
    getWorker(_workerId, label) {
      switch (label) {
        case 'json':
          return new jsonWorker.default()
        case 'css':
        case 'scss':
        case 'less':
          return new cssWorker.default()
        case 'html':
        case 'handlebars':
        case 'razor':
          return new htmlWorker.default()
        case 'typescript':
        case 'javascript':
          return new tsWorker.default()
        default:
          return new editorWorker.default()
      }
    },
  }

  loader.config({ monaco })
}

export function ensureMonaco(): Promise<void> {
  monacoPromise ??= setupMonaco().catch((error: unknown) => {
    // Do not cache a failed load: a transient chunk error would otherwise block
    // every editor until a full page reload.
    monacoPromise = null
    throw error
  })
  return monacoPromise
}
