import { ChangeEvent, useRef, useState } from "react";
import { Download, Loader2, Upload } from "lucide-react";
import apiClient from "../api/client";

type Product = {
  article: string;
  name: string;
  gtin: string;
  ozonId?: string | null;
};

type ProductApiShape = {
  article?: string;
  sku?: string;
  name?: string;
  title?: string;
  gtin?: string;
  ozonId?: string | null;
  ozon_id?: string | null;
};

type OzonParseXmlResponse = {
  products: ProductApiShape[];
};

type ExcelImportResult = {
  created: number;
  updated: number;
  skipped: number;
};

function mapProduct(raw: ProductApiShape): Product {
  return {
    article: raw.article ?? raw.sku ?? "-",
    name: raw.name ?? raw.title ?? "Без названия",
    gtin: raw.gtin ?? "-",
    ozonId: raw.ozonId ?? raw.ozon_id ?? null,
  };
}

function downloadBlob(blob: Blob, fallbackName: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isUploadingXml, setIsUploadingXml] = useState(false);
  const [isDownloadingExcel, setIsDownloadingExcel] = useState(false);
  const [isImportingExcel, setIsImportingExcel] = useState(false);
  const [isTableVisible, setIsTableVisible] = useState(false);
  const [importInfo, setImportInfo] = useState<string | null>(null);
  const excelInputRef = useRef<HTMLInputElement | null>(null);
  const xmlInputRef = useRef<HTMLInputElement | null>(null);

  async function handleXmlUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    setIsUploadingXml(true);
    setError(null);
    setImportInfo(null);
    try {
      const response = await apiClient.post<OzonParseXmlResponse>("/ozon/parse-xml", formData);
      const list = response.data?.products;
      const mapped = Array.isArray(list) ? list.map(mapProduct) : [];
      setProducts(mapped);
      setIsTableVisible(true);
    } catch (requestError) {
      console.error("Failed to parse XML:", requestError);
      setError("Не удалось обработать XML файл от Ozon.");
    } finally {
      setIsUploadingXml(false);
      event.target.value = "";
    }
  }

  async function handleDownloadTemplate() {
    if (products.length === 0) {
      setError("Сначала загрузите XML и получите список товаров.");
      return;
    }

    setIsDownloadingExcel(true);
    setError(null);
    try {
      const items = products.map((p) => ({
        article: p.article,
        name: p.name,
        gtin: p.gtin,
        ozon_id: p.ozonId ?? null,
      }));
      const response = await apiClient.post("/excel/generate-template", { items }, {
        responseType: "blob",
      });
      downloadBlob(response.data as Blob, "ozon_mapping_template.xlsx");
    } catch (requestError) {
      console.error("Failed to generate template:", requestError);
      setError("Не удалось скачать шаблон Excel.");
    } finally {
      setIsDownloadingExcel(false);
    }
  }

  async function handleImportExcel(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    setIsImportingExcel(true);
    setError(null);
    setImportInfo(null);
    try {
      const response = await apiClient.post<ExcelImportResult>("/excel/import-ozon-id", formData);
      const { created, updated, skipped } = response.data;
      setImportInfo(
        `Импорт завершён: создано ${created}, обновлено ${updated}, пропущено ${skipped}. Чтобы подтянуть новые Ozon ID в таблицу, снова загрузите XML.`,
      );
    } catch (requestError) {
      console.error("Failed to import Excel:", requestError);
      setError("Не удалось импортировать файл Excel.");
    } finally {
      setIsImportingExcel(false);
      event.target.value = "";
    }
  }

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold text-slate-900">Товары и Ozon</h1>
        <p className="mt-1 text-sm text-slate-500">
          Загрузка XML, сверка данных и массовое обновление Ozon ID.
        </p>
      </section>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      {importInfo ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {importInfo}
        </div>
      ) : null}

      <section className="space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-5">
        <h2 className="text-lg font-medium text-slate-900">Загрузка XML от Ozon</h2>
        <p className="text-sm text-slate-600">
          Пример имени файла из личного кабинета:{" "}
          <span className="font-mono text-slate-800">offers_12345678.xml</span>
        </p>

        <button
          type="button"
          onClick={() => xmlInputRef.current?.click()}
          disabled={isUploadingXml}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-70"
        >
          {isUploadingXml ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
          Загрузить XML от Ozon
        </button>

        <input
          ref={xmlInputRef}
          type="file"
          accept=".xml"
          className="hidden"
          onChange={(event) => void handleXmlUpload(event)}
        />
      </section>

      <section>
        <div className="mb-3 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void handleDownloadTemplate()}
            disabled={isDownloadingExcel}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isDownloadingExcel ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Download size={16} />
            )}
            Скачать шаблон Excel
          </button>

          <button
            type="button"
            onClick={() => excelInputRef.current?.click()}
            disabled={isImportingExcel}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isImportingExcel ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
            Импорт Excel (csv, xlsx)
          </button>

          <input
            ref={excelInputRef}
            type="file"
            accept=".csv,.xlsx"
            className="hidden"
            onChange={(event) => void handleImportExcel(event)}
          />
        </div>

        <div className="overflow-hidden rounded-xl border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 bg-white text-sm">
            <thead className="bg-slate-50 text-left text-slate-600">
              <tr>
                <th className="px-4 py-3 font-medium">Артикул</th>
                <th className="px-4 py-3 font-medium">Наименование</th>
                <th className="px-4 py-3 font-medium">GTIN</th>
                <th className="px-4 py-3 font-medium">Ozon ID</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {!isTableVisible ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                    Загрузите XML файл, чтобы увидеть товары.
                  </td>
                </tr>
              ) : null}

              {isTableVisible && products.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                    В ответе нет данных по товарам.
                  </td>
                </tr>
              ) : null}

              {products.map((product) => (
                <tr key={`${product.article}-${product.gtin}`}>
                  <td className="px-4 py-3">{product.article}</td>
                  <td className="px-4 py-3">{product.name}</td>
                  <td className="px-4 py-3">{product.gtin}</td>
                  <td className="px-4 py-3">{product.ozonId || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
