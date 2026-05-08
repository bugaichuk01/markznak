import { FormEvent, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Loader2, RefreshCw, X } from "lucide-react";
import apiClient from "../api/client";

type EmissionOrderStatus = "created" | "pending" | "available" | "rejected";

type EmissionOrder = {
  id: string;
  product_card_id: string | null;
  gtin: string | null;
  quantity: number;
  status: EmissionOrderStatus;
  suz_order_id: string | null;
};

type ProductCardOption = {
  id: string;
  name: string;
};

type SuzSyncResult = {
  inserted: number;
  updated: number;
  total_remote: number;
};

const statusLabel: Record<EmissionOrderStatus, string> = {
  created: "Создан",
  pending: "В обработке",
  available: "Доступен",
  rejected: "Отклонён",
};

export default function OrdersPage() {
  const [orders, setOrders] = useState<EmissionOrder[]>([]);
  const [cards, setCards] = useState<ProductCardOption[]>([]);
  const [selectedOrderIds, setSelectedOrderIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [syncInfo, setSyncInfo] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isMerging, setIsMerging] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [sendLoadingOrderId, setSendLoadingOrderId] = useState<string | null>(null);
  const [selectedCardId, setSelectedCardId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [orderGtin, setOrderGtin] = useState("");
  const [gtinPatchOrderId, setGtinPatchOrderId] = useState<string | null>(null);
  const [gtinPatchValue, setGtinPatchValue] = useState("");
  const [isPatchingGtin, setIsPatchingGtin] = useState(false);

  const mergeableSelectedIds = useMemo(() => {
    const createdWithCard = new Set(
      orders
        .filter((order) => order.status === "created" && order.product_card_id)
        .map((order) => order.id),
    );
    return selectedOrderIds.filter((id) => createdWithCard.has(id));
  }, [orders, selectedOrderIds]);

  /** Один выбранный черновик с GTIN, готовый к POST в СУЗ (можно отправить и из шапки). */
  const singleSelectedDraftForSuz = useMemo(() => {
    if (selectedOrderIds.length !== 1) {
      return null;
    }
    const order = orders.find((candidate) => candidate.id === selectedOrderIds[0]);
    if (!order) {
      return null;
    }
    const hasGtin = Boolean(order.gtin && order.gtin.trim());
    if (order.status !== "created" || !hasGtin || order.suz_order_id !== null) {
      return null;
    }
    return order;
  }, [orders, selectedOrderIds]);

  async function loadOrders() {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiClient.get<EmissionOrder[]>("/emission-orders/");
      setOrders(Array.isArray(response.data) ? response.data : []);
    } catch (requestError) {
      console.error("Failed to load emission orders:", requestError);
      setError("Не удалось загрузить заказы СУЗ.");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadCards() {
    try {
      const response = await apiClient.get<ProductCardOption[]>("/product-cards/");
      const options = Array.isArray(response.data)
        ? response.data.map((card) => ({ id: card.id, name: card.name }))
        : [];
      setCards(options);
      if (options.length > 0 && !selectedCardId) {
        setSelectedCardId(options[0].id);
      }
    } catch (requestError) {
      console.error("Failed to load product cards for order form:", requestError);
      setError("Не удалось загрузить список карточек товаров.");
    }
  }

  useEffect(() => {
    void Promise.all([loadOrders(), loadCards()]);
  }, []);

  useEffect(() => {
    setSelectedOrderIds((previous) => previous.filter((id) => orders.some((order) => order.id === id)));
  }, [orders]);

  async function handleSyncFromSuz() {
    setIsSyncing(true);
    setError(null);
    setSyncInfo(null);
    try {
      const response = await apiClient.post<SuzSyncResult>("/emission-orders/sync-from-suz");
      const { inserted, updated, total_remote } = response.data;
      setSyncInfo(
        `Синхронизация: получено из СУЗ ${total_remote}, новых ${inserted}, обновлено ${updated}.`,
      );
      await loadOrders();
    } catch (requestError) {
      console.error("Failed to sync SUZ orders:", requestError);
      if (axios.isAxiosError(requestError)) {
        const detail = requestError.response?.data?.detail;
        if (typeof detail === "string" && detail.trim()) {
          setError(detail);
          return;
        }
      }
      setError("Не удалось подтянуть заказы из СУЗ. Проверьте SUZ_* в .env бэкенда.");
    } finally {
      setIsSyncing(false);
    }
  }

  async function handleSendOrderToSuz(orderId: string) {
    setSendLoadingOrderId(orderId);
    setSyncInfo(null);
    setError(null);
    try {
      await apiClient.post(`/emission-orders/${orderId}/send`);
      setSyncInfo("Заказ отправлен в СУЗ.");
      await loadOrders();
    } catch (requestError) {
      console.error("Failed to send order to SUZ:", requestError);
      if (axios.isAxiosError(requestError)) {
        const detail = requestError.response?.data?.detail;
        if (typeof detail === "string" && detail.trim()) {
          setError(detail);
          return;
        }
      }
      setError("Не удалось отправить заказ в СУЗ.");
    } finally {
      setSendLoadingOrderId(null);
    }
  }

  async function handlePatchOrderGtin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = gtinPatchOrderId;
    if (!id) return;
    const trimmed = gtinPatchValue.trim();
    if (trimmed.length < 8) {
      setError("GTIN должен быть не короче 8 цифр.");
      return;
    }

    setIsPatchingGtin(true);
    setError(null);
    try {
      await apiClient.patch(`/emission-orders/${id}/gtin`, { gtin: trimmed });
      setGtinPatchOrderId(null);
      setGtinPatchValue("");
      setSyncInfo("GTIN сохранён в заказе. Можно отправлять в СУЗ.");
      await loadOrders();
    } catch (requestError) {
      console.error("Failed to patch order GTIN:", requestError);
      if (axios.isAxiosError(requestError)) {
        const detail = requestError.response?.data?.detail;
        if (typeof detail === "string" && detail.trim()) {
          setError(detail);
          return;
        }
      }
      setError("Не удалось сохранить GTIN.");
    } finally {
      setIsPatchingGtin(false);
    }
  }

  async function handleCreateOrder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedQuantity = Number(quantity);
    if (!selectedCardId || Number.isNaN(parsedQuantity) || parsedQuantity <= 0) {
      setError("Выберите карточку и укажите количество больше 0.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        product_card_id: selectedCardId,
        quantity: parsedQuantity,
      };
      const g = orderGtin.trim();
      if (g.length >= 8) payload.gtin = g;

      await apiClient.post("/emission-orders/", payload);
      setIsModalOpen(false);
      setQuantity("1");
      setOrderGtin("");
      await loadOrders();
    } catch (requestError) {
      console.error("Failed to create emission order:", requestError);
      if (axios.isAxiosError(requestError) && requestError.response?.status === 422) {
        setError("Не удалось создать заказ: проверьте карточку товара и количество.");
        return;
      }
      setError("Не удалось создать заказ на эмиссию.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleMergeOrders() {
    if (mergeableSelectedIds.length < 2) {
      return;
    }
    setIsMerging(true);
    setError(null);
    try {
      await apiClient.post("/emission-orders/merge", {
        order_ids: mergeableSelectedIds,
      });
      setSelectedOrderIds([]);
      await loadOrders();
    } catch (requestError) {
      console.error("Failed to merge emission orders:", requestError);
      setError("Не удалось объединить выбранные заказы.");
    } finally {
      setIsMerging(false);
    }
  }

  function toggleOrder(orderId: string, checked: boolean) {
    setSelectedOrderIds((previous) => {
      if (checked) {
        return [...previous, orderId];
      }
      return previous.filter((id) => id !== orderId);
    });
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Заказы СУЗ</h1>
          <p className="mt-1 text-sm text-slate-500">
            Черновик создаётся локально («Заказать коды»); в СУЗ — кнопка в строке таблицы или «Отправить в СУЗ (выбранный)»
            после отметки одного черновика с GTIN. Список с сервера — «Подтянуть из СУЗ». Объединять можно только созданные заказы с
            карточкой.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void handleSyncFromSuz()}
            disabled={isSyncing}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isSyncing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            Подтянуть из СУЗ
          </button>
          {singleSelectedDraftForSuz ? (
            <button
              type="button"
              onClick={() => void handleSendOrderToSuz(singleSelectedDraftForSuz.id)}
              disabled={sendLoadingOrderId === singleSelectedDraftForSuz.id}
              className="inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-950 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {sendLoadingOrderId === singleSelectedDraftForSuz.id ? (
                <Loader2 size={16} className="animate-spin" />
              ) : null}
              Отправить в СУЗ (выбранный)
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => setIsModalOpen(true)}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
          >
            Заказать коды
          </button>
        </div>
      </section>

      {mergeableSelectedIds.length >= 2 ? (
        <div className="flex justify-start">
          <button
            type="button"
            onClick={() => void handleMergeOrders()}
            disabled={isMerging}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isMerging ? <Loader2 size={16} className="animate-spin" /> : null}
            Объединить заказы
          </button>
        </div>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      ) : null}

      {syncInfo ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {syncInfo}
        </div>
      ) : null}

      <div className="overflow-hidden rounded-xl border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 bg-white text-sm">
          <thead className="bg-slate-50 text-left text-slate-600">
            <tr>
              <th className="px-4 py-3 font-medium" />
              <th className="px-4 py-3 font-medium">Заказ СУЗ</th>
              <th className="px-4 py-3 font-medium">GTIN</th>
              <th className="px-4 py-3 font-medium">ID карточки</th>
              <th className="px-4 py-3 font-medium">Количество</th>
              <th className="px-4 py-3 font-medium">Статус</th>
              <th className="min-w-[150px] px-4 py-3 font-medium">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {isLoading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                  Загрузка заказов...
                </td>
              </tr>
            ) : null}

            {!isLoading && orders.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                  Заказов пока нет. Нажмите «Подтянуть из СУЗ» или создайте заказ вручную.
                </td>
              </tr>
            ) : null}

            {orders.map((order) => {
              const isCreated = order.status === "created";
              const canSelect = isCreated && Boolean(order.product_card_id);
              const hasGtin = Boolean(order.gtin && order.gtin.trim());
              const canSpecifyGtin =
                order.status === "created" &&
                Boolean(order.product_card_id) &&
                order.suz_order_id == null &&
                !hasGtin;
              const canSendToSuz =
                order.status === "created" &&
                hasGtin &&
                order.suz_order_id == null;
              const isChecked = selectedOrderIds.includes(order.id);
              const isSendingRow = sendLoadingOrderId === order.id;
              const showPlaceholder = !canSpecifyGtin && !canSendToSuz;
              return (
                <tr key={order.id}>
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      disabled={!canSelect}
                      onChange={(event) => toggleOrder(order.id, event.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                    />
                  </td>
                  <td className="max-w-[140px] truncate px-4 py-3 font-mono text-xs" title={order.suz_order_id ?? ""}>
                    {order.suz_order_id ?? "—"}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{order.gtin ?? "—"}</td>
                  <td className="px-4 py-3 font-mono text-xs sm:text-sm">
                    {order.product_card_id ?? "—"}
                  </td>
                  <td className="px-4 py-3">{order.quantity}</td>
                  <td className="px-4 py-3">{statusLabel[order.status] ?? order.status}</td>
                  <td className="max-w-[200px] px-4 py-3">
                    <div className="flex flex-col items-start gap-1.5">
                      {canSpecifyGtin ? (
                        <button
                          type="button"
                          onClick={() => {
                            setGtinPatchOrderId(order.id);
                            setGtinPatchValue("");
                            setError(null);
                          }}
                          className="rounded-md border border-blue-200 bg-blue-50 px-2 py-1 text-xs font-medium text-blue-900 transition hover:bg-blue-100"
                        >
                          Указать GTIN
                        </button>
                      ) : null}
                      {canSendToSuz ? (
                        <button
                          type="button"
                          onClick={() => void handleSendOrderToSuz(order.id)}
                          disabled={isSendingRow}
                          className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-900 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {isSendingRow ? <Loader2 size={14} className="animate-spin" /> : null}
                          Отправить в СУЗ
                        </button>
                      ) : null}
                      {showPlaceholder ? <span className="text-xs text-slate-400">—</span> : null}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {isModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-5 shadow-xl">
            <div className="mb-4 flex items-start justify-between">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Заказать коды</h2>
                <p className="text-sm text-slate-500">Локальный черновик заказа; затем отправьте его кнопкой «Отправить в СУЗ».</p>
              </div>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="rounded-md p-1 text-slate-500 transition hover:bg-slate-100"
              >
                <X size={18} />
              </button>
            </div>

            <form className="space-y-3" onSubmit={handleCreateOrder}>
              <label className="flex flex-col gap-1 text-sm text-slate-700">
                Карточка товара
                <select
                  value={selectedCardId}
                  onChange={(event) => setSelectedCardId(event.target.value)}
                  required
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 outline-none ring-blue-500 transition focus:ring-2"
                >
                  {cards.length === 0 ? <option value="">Нет доступных карточек</option> : null}
                  {cards.map((card) => (
                    <option key={card.id} value={card.id}>
                      {card.name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1 text-sm text-slate-700">
                Количество
                <input
                  type="number"
                  min={1}
                  required
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 outline-none ring-blue-500 transition focus:ring-2"
                />
              </label>

              <label className="flex flex-col gap-1 text-sm text-slate-700">
                GTIN для СУЗ (если карточка без GTIN)
                <input
                  type="text"
                  inputMode="numeric"
                  placeholder="Необязательно: 8–14 цифр"
                  value={orderGtin}
                  onChange={(event) => setOrderGtin(event.target.value.replace(/\D/g, ""))}
                  className="rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm outline-none ring-blue-500 transition focus:ring-2"
                />
                <span className="text-xs text-slate-500">
                  API СУЗ требует GTIN в теле заказа. У техкарточки в НК код может быть пустым — укажите его здесь.
                </span>
              </label>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || cards.length === 0}
                  className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : null}
                  Создать заказ
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {gtinPatchOrderId !== null ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-xl">
            <div className="mb-4 flex items-start justify-between">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">GTIN для отправки в СУЗ</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Сохраняется только в этом заказе; карточку в Нацкаталоге можно не менять.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setGtinPatchOrderId(null);
                  setGtinPatchValue("");
                }}
                className="rounded-md p-1 text-slate-500 transition hover:bg-slate-100"
              >
                <X size={18} />
              </button>
            </div>
            <form className="space-y-3" onSubmit={handlePatchOrderGtin}>
              <label className="flex flex-col gap-1 text-sm text-slate-700">
                GTIN (8–14 цифр)
                <input
                  type="text"
                  inputMode="numeric"
                  required
                  minLength={8}
                  maxLength={14}
                  value={gtinPatchValue}
                  onChange={(event) => setGtinPatchValue(event.target.value.replace(/\D/g, ""))}
                  className="rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm outline-none ring-blue-500 transition focus:ring-2"
                />
              </label>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setGtinPatchOrderId(null);
                    setGtinPatchValue("");
                  }}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  disabled={isPatchingGtin}
                  className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-70"
                >
                  {isPatchingGtin ? <Loader2 size={16} className="animate-spin" /> : null}
                  Сохранить
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}
