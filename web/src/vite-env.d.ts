/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_STATIC?: string; // "1" in the live build: data comes from /data/*.json
}
