import { FormEvent, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { CopyPlus, Loader2, Trash2, X } from "lucide-react";
import apiClient from "../api/client";

type ProductCardType = "unit" | "set" | "tech_card" | "bundle";
type ProductCardStatus = "draft" | "sent" | "published";

type ProductCard = {
  id: string;
  type: ProductCardType;
  tn_ved: string;
  gtin: string | null;
  name: string;
  status: ProductCardStatus;
  national_catalog_feed_id: string | null;
  national_catalog_feed_status: string | null;
  national_catalog_feed_payload: Record<string, unknown> | null;
};

type CreateCardPayload = {
  name: string;
  type: ProductCardType;
  tn_ved: string;
  gtin?: string;
  cat_id?: number;
};

const typeLabel: Record<ProductCardType, string> = {
  unit: "Единица",
  set: "Комплект",
  tech_card: "Техкарта",
  bundle: "Набор",
};

const statusLabel: Record<ProductCardStatus, string> = {
  draft: "Черновик",
  sent: "Отправлена",
  published: "Опубликована",
};

function extractRejectedReason(payload: Record<string, unknown> | null): string | null {
  if (!payload) return null;
  const result = payload.result as Record<string, unknown> | undefined;
  if (!result) return null;

  const details = result.error_details as Record<string, unknown> | undefined;
  const detailItems = details?.items as Array<Record<string, unknown>> | undefined;
  if (Array.isArray(detailItems) && detailItems.length > 0) {
    const firstMessage = detailItems[0]?.message;
    if (typeof firstMessage === "string" && firstMessage.trim()) return firstMessage.trim();
    const firstErrors = detailItems[0]?.errors as Array<Record<string, unknown>> | undefined;
    if (Array.isArray(firstErrors) && firstErrors.length > 0) {
      const firstErrorText = firstErrors[0]?.text;
      if (typeof firstErrorText === "string" && firstErrorText.trim()) return firstErrorText.trim();
    }
  }

  const rejectedResult = result.result as Record<string, unknown> | undefined;
  if (rejectedResult) {
    for (const value of Object.values(rejectedResult)) {
      if (Array.isArray(value) && value.length > 0 && typeof value[0] === "string") {
        return value[0];
      }
    }
  }

  return null;
}

export default function CardsPage() {
  const [cards, setCards] = useState<ProductCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loadingActionId, setLoadingActionId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [type, setType] = useState<ProductCardType>("tech_card");
  const [tnVed, setTnVed] = useState("");
  const [gtin, setGtin] = useState("");
  const [catId, setCatId] = useState("");

  const isBundleSelected = type === "bundle";
  const isGtinRequired = type === "unit" || type === "set";
  const isCreateDisabled = useMemo(() => {
    if (isBundleSelected) {
      return true;
    }
    if (isGtinRequired && gtin.trim().length === 0) {
      return true;
    }
    return isSubmitting;
  }, [gtin, isBundleSelected, isGtinRequired, isSubmitting]);

  async function loadCards() {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiClient.get<ProductCard[]>("/product-cards/");
      setCards(Array.isArray(response.data) ? response.data : []);
    } catch (requestError) {
      console.error("Failed to load product cards:", requestError);
      setError("Не удалось загрузить карточки Национального каталога.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadCards();
  }, []);

  function resetForm() {
    setName("");
    setType("tech_card");
    setTnVed("");
    setGtin("");
    setCatId("");
  }

  async function handleCreateCard(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isBundleSelected) {
      return;
    }
    if (isGtinRequired && gtin.trim().length === 0) {
      setError("Для типов Единица и Комплект требуется GTIN.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const payload: CreateCardPayload = {
        name: name.trim(),
        type,
        tn_ved: tnVed.trim(),
      };
      if (gtin.trim()) {
        payload.gtin = gtin.trim();
      }
      if (catId.trim()) {
        const parsedCatId = Number(catId.trim());
        if (!Number.isInteger(parsedCatId) || parsedCatId <= 0) {
          setError("cat_id должен быть положительным целым числом.");
          return;
        }
        payload.cat_id = parsedCatId;
      }

      await apiClient.post("/product-cards/", payload);
      setIsModalOpen(false);
      resetForm();
      await loadCards();
    } catch (requestError) {
      console.error("Failed to create product card:", requestError);
      if (axios.isAxiosError(requestError)) {
        if (requestError.response?.status === 422) {
          setError("Не удалось создать карточку: проверьте обязательные поля и формат ТН ВЭД/GTIN.");
          return;
        }
        const backendDetail = requestError.response?.data?.detail;
        if (typeof backendDetail === "string" && backendDetail.trim().length > 0) {
          setError(backendDetail);
          return;
        }
      }
      setError("Не удалось создать карточку товара.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDeleteCard(cardId: string) {
    setLoadingActionId(cardId);
    setError(null);
    try {
      await apiClient.delete(`/product-cards/${cardId}`);
      await loadCards();
    } catch (requestError) {
      console.error("Failed to delete product card:", requestError);
      setError("Не удалось удалить карточку товара.");
    } finally {
      setLoadingActionId(null);
    }
  }

  async function handleCopyCard(cardId: string) {
    setLoadingActionId(cardId);
    setError(null);
    try {
      await apiClient.post(`/product-cards/${cardId}/copy`);
      await loadCards();
    } catch (requestError) {
      console.error("Failed to copy product card:", requestError);
      setError("Не удалось создать подобную карточку.");
    } finally {
      setLoadingActionId(null);
    }
  }

  async function handleSyncFeedStatus(cardId: string) {
    setLoadingActionId(cardId);
    setError(null);
    try {
      await apiClient.post(`/product-cards/${cardId}/sync-feed-status`);
      await loadCards();
    } catch (requestError) {
      console.error("Failed to sync feed status:", requestError);
      if (axios.isAxiosError(requestError) && typeof requestError.response?.data?.detail === "string") {
        setError(requestError.response.data.detail);
        return;
      }
      setError("Не удалось обновить статус фида НК.");
    } finally {
      setLoadingActionId(null);
    }
  }

  return (
    <div className="space-y-6">
      <section className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Национальный каталог</h1>
          <p className="mt-1 text-sm text-slate-500">Управление карточками товаров Честного Знака.</p>
        </div>
        <button
          type="button"
          onClick={() => setIsModalOpen(true)}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
        >
          Создать карточку
        </button>
      </section>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <div className="overflow-hidden rounded-xl border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 bg-white text-sm">
          <thead className="bg-slate-50 text-left text-slate-600">
            <tr>
              <th className="px-4 py-3 font-medium">Тип</th>
              <th className="px-4 py-3 font-medium">ТН ВЭД</th>
              <th className="px-4 py-3 font-medium">Название</th>
              <th className="px-4 py-3 font-medium">Статус</th>
              <th className="px-4 py-3 font-medium">Статус НК</th>
              <th className="px-4 py-3 font-medium">Причина НК</th>
              <th className="px-4 py-3 font-medium">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {isLoading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                  Загрузка карточек...
                </td>
              </tr>
            ) : null}

            {!isLoading && cards.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                  Карточек пока нет.
                </td>
              </tr>
            ) : null}

            {cards.map((card) => (
              <tr key={card.id}>
                <td className="px-4 py-3">{typeLabel[card.type] ?? card.type}</td>
                <td className="px-4 py-3">{card.tn_ved}</td>
                <td className="px-4 py-3">{card.name}</td>
                <td className="px-4 py-3">{statusLabel[card.status] ?? card.status}</td>
                <td className="px-4 py-3">{card.national_catalog_feed_status ?? "—"}</td>
                <td className="max-w-xs truncate px-4 py-3" title={extractRejectedReason(card.national_catalog_feed_payload) ?? ""}>
                  {extractRejectedReason(card.national_catalog_feed_payload) ?? "—"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void handleSyncFeedStatus(card.id)}
                      disabled={loadingActionId === card.id || !card.national_catalog_feed_id}
                      title="Обновить статус НК"
                      className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      Sync
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleCopyCard(card.id)}
                      disabled={loadingActionId === card.id}
                      title="Создать подобный"
                      className="rounded-md border border-slate-200 p-2 text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {loadingActionId === card.id ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <CopyPlus size={16} />
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDeleteCard(card.id)}
                      disabled={loadingActionId === card.id}
                      title="Удалить"
                      className="rounded-md border border-slate-200 p-2 text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {loadingActionId === card.id ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Trash2 size={16} />
                      )}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {isModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-5 shadow-xl">
            <div className="mb-4 flex items-start justify-between">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Создать карточку</h2>
                <p className="text-sm text-slate-500">Заполните поля новой карточки товара.</p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsModalOpen(false);
                  resetForm();
                }}
                className="rounded-md p-1 text-slate-500 transition hover:bg-slate-100"
              >
                <X size={18} />
              </button>
            </div>

            <form className="space-y-3" onSubmit={handleCreateCard}>
              <label className="flex flex-col gap-1 text-sm text-slate-700">
                Название
                <input
                  required
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 outline-none ring-blue-500 transition focus:ring-2"
                />
              </label>

              <label className="flex flex-col gap-1 text-sm text-slate-700">
                Тип
                <select
                  value={type}
                  onChange={(event) => setType(event.target.value as ProductCardType)}
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 outline-none ring-blue-500 transition focus:ring-2"
                >
                  <option value="unit">Единица</option>
                  <option value="set">Комплект</option>
                  <option value="tech_card">Техкарта</option>
                  <option value="bundle">Набор</option>
                </select>
              </label>

              <label className="flex flex-col gap-1 text-sm text-slate-700">
                ТН ВЭД
                <input
                  required
                  value={tnVed}
                  onChange={(event) => setTnVed(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 outline-none ring-blue-500 transition focus:ring-2"
                />
              </label>

              <label className="flex flex-col gap-1 text-sm text-slate-700">
                GTIN {isGtinRequired ? "(обязательно для типа Единица/Комплект)" : "(опционально)"}
                <input
                  value={gtin}
                  onChange={(event) => setGtin(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 outline-none ring-blue-500 transition focus:ring-2"
                />
              </label>

              <label className="flex flex-col gap-1 text-sm text-slate-700">
                Категория НК (cat_id, рекомендуется для отправки)
                <input
                  value={catId}
                  onChange={(event) => setCatId(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 outline-none ring-blue-500 transition focus:ring-2"
                />
              </label>

              {isBundleSelected ? (
                <p className="text-sm text-red-600">
                  Карточки с типом Набор создаются и редактируются только через сайт Честного Знака.
                </p>
              ) : null}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setIsModalOpen(false);
                    resetForm();
                  }}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  disabled={isCreateDisabled}
                  className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : null}
                  Создать карточку
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}
