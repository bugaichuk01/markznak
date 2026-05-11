/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Полный базовый URL API, например https://api.example.com/api/v1. Пусто = /api/v1 (локальный прокси Vite). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
