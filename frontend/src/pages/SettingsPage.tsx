import { FormEvent, useEffect, useMemo, useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import apiClient from "../api/client";
import PageHeader from "../components/ui/PageHeader";
import Alert from "../components/ui/Alert";
import EmptyState from "../components/ui/EmptyState";
import type { CadesPluginApi, CertificateOption } from "../services/signingService";

const SANDBOX_OMS_CONNECTION = "2363ae64-f3c2-47de-8b46-6ee0c7b82301";

type Device = {
  id: string | number;
  name: string;
  omsId: string;
  connectionId: string;
  inn: string;
};

type DeviceApiShape = {
  id?: string | number;
  _id?: string | number;
  name?: string;
  deviceName?: string;
  omsId?: string;
  oms_id?: string;
  connectionId?: string;
  connection_id?: string;
  inn?: string | null;
};

type DeviceFormDefaults = {
  oms_id?: string | null;
  connection_id?: string | null;
};

const INITIAL_FORM = {
  name: "",
  omsId: "",
  connectionId: "",
  inn: "",
};

type TokenInfo = {
  token: string | null;
  expires_at: string | null;
  expires_in_minutes: number | null;
  is_expired: boolean;
  source: string;
  oms_connection_id: string | null;
  updated_at: string | null;
  true_api_token_configured?: boolean;
  true_api_token_preview?: string | null;
};

function resolveOmsConnection(
  info: TokenInfo | null,
  devices: DeviceApiShape[],
): string {
  const fromInfo = info?.oms_connection_id?.trim();
  if (fromInfo) return fromInfo;

  const fromDevice = devices
    .map((d) => (d.connectionId ?? d.connection_id ?? "").trim())
    .find(Boolean);
  if (fromDevice) return fromDevice;

  return SANDBOX_OMS_CONNECTION;
}

function extractErrorMessage(err: unknown): string {
  if (err && typeof err === "object" && "response" in err) {
    const data = (err as { response?: { data?: { detail?: unknown; error_message?: string } } })
      .response?.data;
    if (typeof data?.error_message === "string") return data.error_message;
    const detail = data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const msg = (detail as { error_message?: string }).error_message;
      if (typeof msg === "string") return msg;
    }
  }
  if (err instanceof Error) return err.message;
  return "Ошибка обновления токена";
}

function TokenStatusWidget() {
  const [info, setInfo] = useState<TokenInfo | null>(null);
  const [devices, setDevices] = useState<DeviceApiShape[]>([]);
  const [certificates, setCertificates] = useState<CertificateOption[]>([]);
  const [selectedCertIndex, setSelectedCertIndex] = useState(1);
  const [refreshing, setRefreshing] = useState(false);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadTokenInfo() {
    const response = await apiClient.get<TokenInfo>("/token/info");
    setInfo(response.data);
  }

  useEffect(() => {
    void (async () => {
      try {
        const [devicesRes] = await Promise.all([
          apiClient.get<DeviceApiShape[]>("/devices").catch(() => ({ data: [] })),
          loadTokenInfo(),
        ]);
        setDevices(Array.isArray(devicesRes.data) ? devicesRes.data : []);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function loadCertificates() {
    try {
      await window.cadesplugin;
      const api = window.cadesplugin as CadesPluginApi;
      const oStore = await api.CreateObjectAsync("CAdESCOM.Store");
      await oStore.Open!(
        api.CADESCOM_CONTAINER_STORE,
        api.CAPICOM_MY_STORE,
        api.CAPICOM_STORE_OPEN_MAXIMUM_ALLOWED,
      );
      const certs = await oStore.Certificates!;
      const count = (await certs.Count) ?? 0;
      const list: CertificateOption[] = [];
      for (let i = 1; i <= count; i++) {
        const cert = await certs.Item!(i);
        const subject = (await cert.SubjectName) ?? `Сертификат ${i}`;
        const cn = subject.match(/CN=([^,]+)/)?.[1] || subject;
        list.push({ index: i, name: cn });
      }
      await oStore.Close?.();
      setCertificates(list);
      if (list.length > 0) setSelectedCertIndex(list[0].index);
    } catch {
      setCertificates([]);
    }
  }

  useEffect(() => {
    void loadCertificates();
  }, []);

  async function handleRefreshToken() {
    setRefreshing(true);
    setTokenError(null);
    setSuccess(null);

    try {
      await window.cadesplugin;
      const api = window.cadesplugin as CadesPluginApi;

      const oStore = await api.CreateObjectAsync("CAdESCOM.Store");
      await oStore.Open!(
        api.CADESCOM_CONTAINER_STORE,
        api.CAPICOM_MY_STORE,
        api.CAPICOM_STORE_OPEN_MAXIMUM_ALLOWED,
      );

      const certs = await oStore.Certificates!;
      const count = (await certs.Count) ?? 0;
      if (count < 1) {
        await oStore.Close?.();
        throw new Error("В хранилище нет сертификатов для подписи.");
      }
      if (selectedCertIndex < 1 || selectedCertIndex > count) {
        await oStore.Close?.();
        throw new Error(`Сертификат с индексом ${selectedCertIndex} не найден (всего ${count}).`);
      }

      const cert = await certs.Item!(selectedCertIndex);
      const omsConnection = resolveOmsConnection(info, devices);

      const key1Res = await apiClient.get<{ uuid: string; data: string }>("/token/auth-key");
      const { uuid: uuid1, data: data1 } = key1Res.data;

      const oSigner1 = await api.CreateObjectAsync("CAdESCOM.CPSigner");
      await oSigner1.propset_Certificate!(cert);
      await oSigner1.propset_CheckCertificate!(true);
      const oSignedData1 = await api.CreateObjectAsync("CAdESCOM.CadesSignedData");
      await oSignedData1.propset_ContentEncoding!(api.CADESCOM_BASE64_TO_BINARY);
      await oSignedData1.propset_Content!(btoa(data1));
      const signature1 = (
        await oSignedData1.SignCades!(oSigner1, api.CADESCOM_CADES_BES, false)
      ).replace(/[\r\n]/g, "");

      const suzRes = await apiClient.post<{ token: string }>(
        `/token/auth-signin/${omsConnection}`,
        { uuid: uuid1, data: signature1 },
      );
      const clientToken = suzRes.data.token;

      const key2Res = await apiClient.get<{ uuid: string; data: string }>("/token/auth-key");
      const { uuid: uuid2, data: data2 } = key2Res.data;

      const oSigner2 = await api.CreateObjectAsync("CAdESCOM.CPSigner");
      await oSigner2.propset_Certificate!(cert);
      await oSigner2.propset_CheckCertificate!(true);
      const oSignedData2 = await api.CreateObjectAsync("CAdESCOM.CadesSignedData");
      await oSignedData2.propset_ContentEncoding!(api.CADESCOM_BASE64_TO_BINARY);
      await oSignedData2.propset_Content!(btoa(data2));
      const signature2 = (
        await oSignedData2.SignCades!(oSigner2, api.CADESCOM_CADES_BES, false)
      ).replace(/[\r\n]/g, "");

      const trueApiRes = await apiClient.post<{ token: string }>(
        "/token/auth-signin-true-api",
        { uuid: uuid2, data: signature2 },
      );
      const trueApiJwt = trueApiRes.data.token;

      await oStore.Close?.();

      await apiClient.post("/token/save", {
        token: clientToken,
        oms_connection_id: omsConnection,
        expires_in_hours: 10,
        true_api_token: trueApiJwt,
        true_api_expires_in_hours: 10,
      });

      await loadTokenInfo();
      setSuccess("Оба токена успешно обновлены!");
    } catch (err) {
      setTokenError(extractErrorMessage(err));
    } finally {
      setRefreshing(false);
    }
  }

  const isExpiring = info?.expires_in_minutes !== null && (info?.expires_in_minutes ?? 0) < 60;
  const isExpired = info?.is_expired ?? false;

  const statusText = loading
    ? "Загрузка статуса..."
    : isExpired
      ? "Токен истёк"
      : isExpiring
        ? `Истекает через ${info?.expires_in_minutes} мин`
        : info?.expires_in_minutes
          ? `Действителен ещё ${info?.expires_in_minutes} мин`
          : "Источник: .env файл";

  return (
    <section id="update-token" className="card mb-8 p-6">
      <h2 className="text-lg font-semibold text-forest-950">Токен СУЗ</h2>
      <div className="mt-4 space-y-3">
        <div
          className={`rounded-lg border p-4 ${
            isExpired
              ? "border-red-200 bg-red-50"
              : isExpiring
                ? "border-amber-200 bg-amber-50"
                : "border-emerald-200 bg-emerald-50"
          }`}
        >
          <h3 className="text-sm font-medium text-forest-950">Статус токена</h3>
          <p className="mt-1 text-xs text-sage-600">{statusText}</p>
          {info?.updated_at ? (
            <p className="text-xs text-sage-400">
              Обновлён: {new Date(info.updated_at).toLocaleString("ru-RU")}
            </p>
          ) : null}
          <p className="mt-1 text-xs text-sage-600">
            True API JWT:{" "}
            {info?.true_api_token_configured
              ? `настроен (${info.true_api_token_preview ?? "…"})`
              : "не настроен — проверка статусов КМ недоступна"}
          </p>
        </div>

        {certificates.length > 0 ? (
          <label className="flex flex-col gap-1.5">
            <span className="label-text">Сертификат для подписи</span>
            <select
              value={selectedCertIndex}
              onChange={(e) => setSelectedCertIndex(Number(e.target.value))}
              className="input-field"
            >
              {certificates.map((c) => (
                <option key={c.index} value={c.index}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p className="text-xs text-sage-500">
            Сертификаты не найдены. Установите КриптоПро ЭЦП Browser plug-in.
          </p>
        )}

        <button
          type="button"
          onClick={() => void handleRefreshToken()}
          disabled={refreshing || certificates.length === 0}
          className="btn-primary w-full"
        >
          {refreshing ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              Обновление токена...
            </>
          ) : (
            "Обновить токен СУЗ"
          )}
        </button>

        {tokenError ? (
          <Alert variant="error" onDismiss={() => setTokenError(null)}>
            {tokenError}
          </Alert>
        ) : null}
        {success ? (
          <Alert variant="success" onDismiss={() => setSuccess(null)}>
            {success}
          </Alert>
        ) : null}
      </div>
    </section>
  );
}

function mapDevice(raw: DeviceApiShape, index: number): Device {
  return {
    id: raw.id ?? raw._id ?? `device-${index}`,
    name: raw.name ?? raw.deviceName ?? "Без имени",
    omsId: raw.omsId ?? raw.oms_id ?? "-",
    connectionId: raw.connectionId ?? raw.connection_id ?? "-",
    inn: raw.inn ?? "",
  };
}

export default function SettingsPage() {
  const [form, setForm] = useState(INITIAL_FORM);
  const [devices, setDevices] = useState<Device[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<string | number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hasDevices = useMemo(() => devices.length > 0, [devices.length]);

  async function loadDevices() {
    setIsLoading(true);
    setError(null);
    try {
      const defaultsPromise = apiClient
        .get<DeviceFormDefaults>("/devices/form-defaults")
        .then((r) => r.data)
        .catch(() => null);

      const response = await apiClient.get<DeviceApiShape[]>("/devices");
      const defaults = await defaultsPromise;

      const nextDevices = Array.isArray(response.data)
        ? response.data.map(mapDevice)
        : [];
      setDevices(nextDevices);

      const o = defaults?.oms_id?.trim();
      const c = defaults?.connection_id?.trim();
      if (o || c) {
        setForm((prev) => ({
          ...prev,
          omsId: prev.omsId || o || "",
          connectionId: prev.connectionId || c || "",
        }));
      }
    } catch (requestError) {
      console.error("Failed to load devices:", requestError);
      setError("Не удалось загрузить список устройств. Повторите попытку.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadDevices();
  }, []);

  async function handleCreateDevice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      await apiClient.post("/devices", {
        name: form.name,
        oms_id: form.omsId,
        connection_id: form.connectionId,
        inn: form.inn.trim() || null,
      });
      setForm(INITIAL_FORM);
      await loadDevices();
    } catch (requestError) {
      console.error("Failed to create device:", requestError);
      setError("Не удалось создать устройство. Проверьте поля формы.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDeleteDevice(id: string | number) {
    setDeletingId(id);
    setError(null);
    try {
      await apiClient.delete(`/devices/${id}`);
      setDevices((prev) => prev.filter((device) => device.id !== id));
    } catch (requestError) {
      console.error("Failed to delete device:", requestError);
      setError("Не удалось удалить устройство.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="page-container">
      <PageHeader
        title="Настройки ЧЗ"
        description="Создание устройств и управление текущими подключениями к системе маркировки."
      />

      {error ? (
        <Alert variant="error" onDismiss={() => setError(null)} className="mb-6">
          {error}
        </Alert>
      ) : null}

      <TokenStatusWidget />

      <section className="card mb-8 p-6">
        <h2 className="text-lg font-semibold text-forest-950">Добавление устройства</h2>
        <form className="mt-5 grid gap-4 md:grid-cols-4" onSubmit={handleCreateDevice}>
          <label className="flex flex-col gap-1.5">
            <span className="label-text">Произвольное имя устройства</span>
            <input
              required
              value={form.name}
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
              className="input-field"
              placeholder="ЗНАК, склад №3"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="label-text">OMS ID</span>
            <input
              required
              value={form.omsId}
              onChange={(event) => setForm((prev) => ({ ...prev, omsId: event.target.value }))}
              className="input-field font-mono text-xs"
              placeholder="abc12def-3456-7890-abcd-ef1234567890"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="label-text">Идентификатор соединения</span>
            <input
              required
              value={form.connectionId}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, connectionId: event.target.value }))
              }
              className="input-field font-mono text-xs"
              placeholder="550e8400-e29b-41d4-a716-446655440000"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="label-text">ИНН</span>
            <input
              value={form.inn}
              onChange={(event) => setForm((prev) => ({ ...prev, inn: event.target.value }))}
              className="input-field font-mono"
              placeholder="7707083893"
              maxLength={12}
            />
          </label>

          <div className="md:col-span-4">
            <button type="submit" disabled={isSubmitting} className="btn-primary">
              {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : null}
              Создать устройство
            </button>
          </div>
        </form>
      </section>

      <section>
        <h2 className="mb-4 text-lg font-semibold text-forest-950">Список устройств</h2>
        <div className="table-container">
          <table className="table-base min-w-full">
            <thead>
              <tr>
                <th>Имя</th>
                <th>ИНН</th>
                <th>OMS ID</th>
                <th>Идентификатор</th>
                <th className="text-right">Действия</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-sage-500">
                    Загрузка устройств...
                  </td>
                </tr>
              ) : null}

              {!isLoading && !hasDevices ? (
                <tr>
                  <td colSpan={5}>
                    <EmptyState
                      title="Устройства не добавлены"
                      description="Создайте первое устройство для подключения к СУЗ."
                    />
                  </td>
                </tr>
              ) : null}

              {!isLoading
                ? devices.map((device) => {
                    const isDeleting = deletingId === device.id;
                    return (
                      <tr key={String(device.id)}>
                        <td>{device.name}</td>
                        <td className="font-mono text-xs">{device.inn || "—"}</td>
                        <td className="font-mono text-xs">{device.omsId}</td>
                        <td className="font-mono text-xs">{device.connectionId}</td>
                        <td className="text-right">
                          <button
                            type="button"
                            onClick={() => void handleDeleteDevice(device.id)}
                            disabled={isDeleting}
                            className="inline-flex rounded-lg p-2.5 text-sage-500 transition hover:bg-red-50 hover:text-red-600 disabled:opacity-70"
                            title="Удалить устройство"
                          >
                            {isDeleting ? (
                              <Loader2 size={16} className="animate-spin" />
                            ) : (
                              <Trash2 size={16} />
                            )}
                          </button>
                        </td>
                      </tr>
                    );
                  })
                : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
