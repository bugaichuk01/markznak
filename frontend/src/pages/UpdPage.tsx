import { FormEvent, useState } from "react";
import { Loader2 } from "lucide-react";
import axios from "axios";
import apiClient from "../api/client";
import {
  checkPluginStatus,
  getUserCertificates,
  signData,
  type UserCertificate,
} from "../services/cryptoPro";

/** Значения как в backend/schemas.py: EdoType */
type EdoTypeApi = "edo_lite" | "commercial_edo";

type CreateUpdResponse = {
  id?: string | number;
  message?: string;
  edo_type?: EdoTypeApi;
};

type SendUpdRequest = {
  signature: {
    format: "detached_cms_base64";
    value: string;
    thumbprint: string;
    signed_at: string;
    metadata: Record<string, string>;
  };
};

const CRYPTO_PLUGIN_ERROR =
  "Проверьте, подключен ли у вас плагин в браузере (КриптоПро ЭЦП Browser plug-in). Для корректной работы рекомендуем использовать Яндекс Браузер или Chromium GOST.";

export default function UpdPage() {
  const [documentNumber, setDocumentNumber] = useState("");
  const [markingCodesText, setMarkingCodesText] = useState("");
  const [disableOwnerControl, setDisableOwnerControl] = useState(false);
  const [edoType, setEdoType] = useState<EdoTypeApi>("edo_lite");
  const [isCreating, setIsCreating] = useState(false);
  const [isPluginChecking, setIsPluginChecking] = useState(false);
  const [isCertificatesLoading, setIsCertificatesLoading] = useState(false);
  const [isSigning, setIsSigning] = useState(false);
  const [certificates, setCertificates] = useState<UserCertificate[]>([]);
  const [selectedThumbprint, setSelectedThumbprint] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [draftId, setDraftId] = useState<string | number | null>(null);

  function getMarkingCodes(): string[] {
    return markingCodesText
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
  }

  async function handleCreateUpd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsCreating(true);
    setError(null);
    setSuccess(null);

    try {
      const payload = {
        document_number: documentNumber.trim(),
        marking_codes: getMarkingCodes(),
        disable_owner_control: disableOwnerControl,
        edo_type: edoType,
      };
      const response = await apiClient.post<CreateUpdResponse>("/upd/create", payload);
      const createdId = response.data?.id ?? null;
      setDraftId(createdId);
      setCertificates([]);
      setSelectedThumbprint("");
      setSuccess(
        createdId
          ? `Черновик УПД создан (ID: ${String(createdId)}).`
          : "Черновик УПД успешно создан.",
      );
    } catch (requestError) {
      console.error("Failed to create UPD:", requestError);
      setError("Не удалось создать УПД. Проверьте данные формы.");
    } finally {
      setIsCreating(false);
    }
  }

  async function handleSignAndSend() {
    if (!draftId) {
      setError("Сначала создайте УПД, чтобы подписать и отправить документ.");
      return;
    }

    setIsPluginChecking(true);
    setIsCertificatesLoading(true);
    setError(null);
    setSuccess(null);
    setCertificates([]);
    setSelectedThumbprint("");

    const pluginStatus = await checkPluginStatus();
    if (!pluginStatus.installed) {
      setError(pluginStatus.hint ?? CRYPTO_PLUGIN_ERROR);
      setIsPluginChecking(false);
      setIsCertificatesLoading(false);
      return;
    }

    try {
      const availableCertificates = await getUserCertificates();
      if (availableCertificates.length === 0) {
        setError("Доступные сертификаты не найдены. Вставьте токен и повторите попытку.");
        return;
      }

      setCertificates(availableCertificates);
      setSelectedThumbprint(availableCertificates[0].thumbprint);
      setSuccess("Плагин найден. Выберите сертификат для подписи.");
    } catch (pluginError) {
      setError(pluginError instanceof Error ? pluginError.message : CRYPTO_PLUGIN_ERROR);
    } finally {
      setIsPluginChecking(false);
      setIsCertificatesLoading(false);
    }
  }

  async function handleConfirmSigning() {
    if (!draftId) {
      setError("Сначала создайте УПД, чтобы подписать документ.");
      return;
    }

    if (!selectedThumbprint) {
      setError("Выберите сертификат для подписи.");
      return;
    }

    setIsSigning(true);
    setError(null);
    setSuccess(null);

    try {
      const xmlResponse = await apiClient.get<Blob>(`/upd/${String(draftId)}/download-xml`, {
        responseType: "blob",
      });
      const xmlString = await xmlResponse.data.text();
      const signature = await signData(selectedThumbprint, xmlString);
      const sendPayload: SendUpdRequest = { signature };
      await apiClient.post(`/upd/${String(draftId)}/send`, sendPayload);
      setSuccess(
        edoType === "edo_lite"
          ? "Документ подписан и успешно отправлен в ЭДО Лайт."
          : "Документ подписан и передан в обработчик коммерческого ЭДО.",
      );
    } catch (signError) {
      if (axios.isAxiosError(signError) && signError.response?.status === 404) {
        setError("Черновик УПД не найден.");
        return;
      }

      if (axios.isAxiosError(signError) && signError.response?.status === 502) {
        setError("Не удалось отправить документ в ЭДО. Попробуйте позже.");
        return;
      }

      if (axios.isAxiosError(signError) && signError.response?.status === 422) {
        setError(
          typeof signError.response?.data?.detail === "string"
            ? signError.response.data.detail
            : "Некорректный payload подписи. Проверьте сертификат и повторите попытку.",
        );
        return;
      }

      setError(
        signError instanceof Error
          ? signError.message
          : "Не удалось подписать документ. Проверьте сертификат и токен.",
      );
    } finally {
      setIsSigning(false);
    }
  }

  async function handleSaveDraftXml() {
    if (!draftId) {
      setError("Сначала создайте УПД, чтобы скачать XML-черновик.");
      return;
    }

    setError(null);
    setSuccess(null);

    try {
      const response = await apiClient.get<Blob>(`/upd/${String(draftId)}/download-xml`, {
        responseType: "blob",
      });

      const blob = new Blob([response.data], { type: "application/xml" });
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = "upd_draft.xml";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);

      setSuccess("XML-черновик успешно скачан.");
    } catch (requestError) {
      console.error("Failed to download XML draft:", requestError);
      if (axios.isAxiosError(requestError) && requestError.response?.status === 404) {
        setError("Черновик УПД не найден.");
        return;
      }
      setError("Не удалось скачать XML-черновик.");
    }
  }

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold text-slate-900">Документы УПД</h1>
        <p className="mt-1 text-sm text-slate-500">
          Формирование УПД, выбор типа ЭДО и дальнейшие действия с черновиком.
        </p>
      </section>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      {success ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {success}
        </div>
      ) : null}

      <section className="rounded-xl border border-slate-200 bg-slate-50 p-5">
        <h2 className="text-lg font-medium text-slate-900">Создание УПД на отгрузку</h2>
        <form className="mt-4 space-y-4" onSubmit={handleCreateUpd}>
          <label className="flex flex-col gap-1 text-sm text-slate-700">
            Номер документа
            <input
              required
              value={documentNumber}
              onChange={(event) => setDocumentNumber(event.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 outline-none ring-blue-500 transition focus:ring-2"
              placeholder="УПД-0047 от 19.04.2026"
            />
          </label>

          <label className="flex flex-col gap-1 text-sm text-slate-700">
            Коды маркировки (каждый код с новой строки)
            <textarea
              required
              value={markingCodesText}
              onChange={(event) => setMarkingCodesText(event.target.value)}
              rows={8}
              className="resize-y rounded-lg border border-slate-300 px-3 py-2 outline-none ring-blue-500 transition focus:ring-2"
              placeholder={
                "0104601234567890215ABC123DEF4567821\n0104601234567890215XYZ98765432109812"
              }
            />
          </label>

          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={disableOwnerControl}
              onChange={(event) => setDisableOwnerControl(event.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            Отключить контроль владельца
          </label>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-slate-700">Тип ЭДО</legend>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="radio"
                name="edoType"
                value="edo_lite"
                checked={edoType === "edo_lite"}
                onChange={() => setEdoType("edo_lite")}
                className="h-4 w-4 border-slate-300 text-blue-600 focus:ring-blue-500"
              />
              ЭДО Лайт
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="radio"
                name="edoType"
                value="commercial_edo"
                checked={edoType === "commercial_edo"}
                onChange={() => setEdoType("commercial_edo")}
                className="h-4 w-4 border-slate-300 text-blue-600 focus:ring-blue-500"
              />
              Коммерческое ЭДО
            </label>
          </fieldset>

          <button
            type="submit"
            disabled={isCreating}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isCreating ? <Loader2 size={16} className="animate-spin" /> : null}
            Создать УПД на отгрузку
          </button>
        </form>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-medium text-slate-900">Дальнейшие действия</h2>
        {draftId ? (
          <p className="mt-1 text-sm text-slate-500">Активный черновик: {String(draftId)}</p>
        ) : (
          <p className="mt-1 text-sm text-slate-500">
            После создания УПД выберите дальнейшее действие.
          </p>
        )}

        <div className="mt-4">
          {edoType === "edo_lite" ? (
            <button
              type="button"
              onClick={() => void handleSignAndSend()}
              disabled={isPluginChecking || isCertificatesLoading || isSigning}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {isPluginChecking || isCertificatesLoading ? (
                <Loader2 size={16} className="animate-spin" />
              ) : null}
              Подписать и отправить
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void handleSaveDraftXml()}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
            >
              Сохранить черновик в XML
            </button>
          )}
        </div>

        {edoType === "edo_lite" && certificates.length > 0 ? (
          <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm font-medium text-slate-800">Выберите сертификат для подписи</p>
            <select
              value={selectedThumbprint}
              onChange={(event) => setSelectedThumbprint(event.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none ring-blue-500 transition focus:ring-2"
            >
              {certificates.map((certificate) => (
                <option key={certificate.thumbprint} value={certificate.thumbprint}>
                  {certificate.ownerName} (до {new Date(certificate.validTo).toLocaleDateString("ru-RU")})
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-slate-500">
              Отпечаток:{" "}
              {certificates.find((certificate) => certificate.thumbprint === selectedThumbprint)
                ?.thumbprint ?? "не выбран"}
            </p>
            <button
              type="button"
              onClick={() => void handleConfirmSigning()}
              disabled={isSigning || !selectedThumbprint}
              className="mt-3 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {isSigning ? <Loader2 size={16} className="animate-spin" /> : null}
              Подтвердить подписание
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
