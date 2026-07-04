/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SIDECAR_PORT?: string
  readonly VITE_SIDECAR_HOST?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
