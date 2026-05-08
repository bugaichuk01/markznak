import { FormEvent, useEffect, useMemo, useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import apiClient from "../api/client";

type Device = {
  id: string | number;
  name: string;
  omsId: string;
  connectionId: string;
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
};

type DeviceFormDefaults = {
  oms_id?: string | null;
  connection_id?: string | null;
};

const INITIAL_FORM = {
  name: "",
  omsId: "",
  connectionId: "",
};

function mapDevice(raw: DeviceApiShape, index: number): Device {
  return {
    id: raw.id ?? raw._id ?? `device-${index}`,
    name: raw.name ?? raw.deviceName ?? "Без имени",
    omsId: raw.omsId ?? raw.oms_id ?? "-",
    connectionId: raw.connectionId ?? raw.connection_id ?? "-",
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
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold text-slate-900">Настройки ЧЗ</h1>
        <p className="mt-1 text-sm text-slate-500">
          Создание устройств и управление текущими подключениями.
        </p>
      </section>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <section className="rounded-xl border border-slate-200 bg-slate-50 p-5">
        <h2 className="text-lg font-medium text-slate-900">Добавление устройства</h2>
        <form className="mt-4 grid gap-4 md:grid-cols-3" onSubmit={handleCreateDevice}>
          <label className="flex flex-col gap-1 text-sm text-slate-700">
            Произвольное имя устройства
            <input
              required
              value={form.name}
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
              className="rounded-lg border border-slate-300 px-3 py-2 outline-none ring-blue-500 transition focus:ring-2"
              placeholder="ЗНАК, склад №3"
            />
          </label>

          <label className="flex flex-col gap-1 text-sm text-slate-700">
            OMS ID
            <input
              required
              value={form.omsId}
              onChange={(event) => setForm((prev) => ({ ...prev, omsId: event.target.value }))}
              className="rounded-lg border border-slate-300 px-3 py-2 outline-none ring-blue-500 transition focus:ring-2"
              placeholder="напр. abc12def-3456-7890-abcd-ef1234567890"
            />
          </label>

          <label className="flex flex-col gap-1 text-sm text-slate-700">
            Идентификатор соединения
            <input
              required
              value={form.connectionId}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, connectionId: event.target.value }))
              }
              className="rounded-lg border border-slate-300 px-3 py-2 outline-none ring-blue-500 transition focus:ring-2"
              placeholder="напр. 550e8400-e29b-41d4-a716-446655440000"
            />
          </label>

          <div className="md:col-span-3">
            <button
              type="submit"
              disabled={isSubmitting}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : null}
              Создать устройство
            </button>
          </div>
        </form>
      </section>

      <section>
        <h2 className="text-lg font-medium text-slate-900">Список устройств</h2>
        <div className="mt-3 overflow-hidden rounded-xl border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 bg-white text-sm">
            <thead className="bg-slate-50 text-left text-slate-600">
              <tr>
                <th className="px-4 py-3 font-medium">Имя</th>
                <th className="px-4 py-3 font-medium">OMS ID</th>
                <th className="px-4 py-3 font-medium">Идентификатор</th>
                <th className="px-4 py-3 text-right font-medium">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {isLoading ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                    Загрузка устройств...
                  </td>
                </tr>
              ) : null}

              {!isLoading && !hasDevices ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                    Устройства пока не добавлены.
                  </td>
                </tr>
              ) : null}

              {!isLoading
                ? devices.map((device) => {
                    const isDeleting = deletingId === device.id;
                    return (
                      <tr key={String(device.id)}>
                        <td className="px-4 py-3">{device.name}</td>
                        <td className="px-4 py-3">{device.omsId}</td>
                        <td className="px-4 py-3">{device.connectionId}</td>
                        <td className="px-4 py-3 text-right">
                          <button
                            type="button"
                            onClick={() => void handleDeleteDevice(device.id)}
                            disabled={isDeleting}
                            className="inline-flex items-center rounded-md p-2 text-slate-500 transition hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-70"
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
