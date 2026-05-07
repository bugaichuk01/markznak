import { FormEvent, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Loader2, X } from "lucide-react";
import apiClient from "../api/client";

type EmissionOrderStatus = "created" | "pending" | "available" | "rejected";

type EmissionOrder = {
  id: string;
  product_card_id: string;
  quantity: number;
  status: EmissionOrderStatus;
};

type ProductCardOption = {
  id: string;
  name: string;
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
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isMerging, setIsMerging] = useState(false);
  const [selectedCardId, setSelectedCardId] = useState("");
  const [quantity, setQuantity] = useState("1");

  const mergeableSelectedIds = useMemo(() => {
    const createdIds = new Set(
      orders.filter((order) => order.status === "created").map((order) => order.id),
    );
    return selectedOrderIds.filter((id) => createdIds.has(id));
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
      await apiClient.post("/emission-orders/", {
        product_card_id: selectedCardId,
        quantity: parsedQuantity,
      });
      setIsModalOpen(false);
      setQuantity("1");
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
      <section className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Заказы СУЗ</h1>
          <p className="mt-1 text-sm text-slate-500">Создание и объединение заказов на эмиссию кодов.</p>
        </div>
        <button
          type="button"
          onClick={() => setIsModalOpen(true)}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
        >
          Заказать коды
        </button>
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
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <div className="overflow-hidden rounded-xl border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 bg-white text-sm">
          <thead className="bg-slate-50 text-left text-slate-600">
            <tr>
              <th className="px-4 py-3 font-medium" />
              <th className="px-4 py-3 font-medium">ID карточки</th>
              <th className="px-4 py-3 font-medium">Количество</th>
              <th className="px-4 py-3 font-medium">Статус</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {isLoading ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                  Загрузка заказов...
                </td>
              </tr>
            ) : null}

            {!isLoading && orders.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                  Заказов пока нет.
                </td>
              </tr>
            ) : null}

            {orders.map((order) => {
              const isCreated = order.status === "created";
              const isChecked = selectedOrderIds.includes(order.id);
              return (
                <tr key={order.id}>
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      disabled={!isCreated}
                      onChange={(event) => toggleOrder(order.id, event.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                    />
                  </td>
                  <td className="px-4 py-3 font-mono text-xs sm:text-sm">{order.product_card_id}</td>
                  <td className="px-4 py-3">{order.quantity}</td>
                  <td className="px-4 py-3">{statusLabel[order.status] ?? order.status}</td>
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
                <p className="text-sm text-slate-500">Создание нового заказа на эмиссию в СУЗ.</p>
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
    </div>
  );
}
