/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Полный базовый URL API, например https://api.example.com/api/v1. Пусто = /api/v1 (локальный прокси Vite). */
  readonly VITE_API_BASE_URL?: string;
  /** Номер сертификата в хранилище cadesplugin (1-based), если не выбран отпечаток в UI. */
  readonly VITE_CERT_INDEX?: string;
}


interface ImportMeta {
  readonly env: ImportMetaEnv;
}
