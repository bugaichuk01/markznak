import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import bwipjs from "bwip-js";
import { Printer } from "lucide-react";

type LabelSizeKey = "58x40" | "43x25";

type LabelSize = {
  key: LabelSizeKey;
  title: string;
  widthMm: number;
  heightMm: number;
};

const LABEL_SIZES: LabelSize[] = [
  { key: "58x40", title: "Стандарт 58х40", widthMm: 58, heightMm: 40 },
  { key: "43x25", title: "Малая 43х25", widthMm: 43, heightMm: 25 },
];

export default function LabelsPage() {
  const [sizeKey, setSizeKey] = useState<LabelSizeKey>("58x40");
  const [name, setName] = useState("Футболка базовая");
  const [article, setArticle] = useState("ART-1001");
  const [gtin, setGtin] = useState("04607123456789");
  const [productSize, setProductSize] = useState("L");
  const [markingCode, setMarkingCode] = useState("010460712345678921abcDEF1234567890");
  const [barcodeError, setBarcodeError] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const selectedSize = useMemo(
    () => LABEL_SIZES.find((item) => item.key === sizeKey) ?? LABEL_SIZES[0],
    [sizeKey],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !markingCode.trim()) {
      setBarcodeError(markingCode.trim() ? null : "Введите код маркировки для генерации DataMatrix.");
      return;
    }

    try {
      bwipjs.toCanvas(canvas, {
        bcid: "datamatrix",
        text: markingCode.trim(),
        scale: 4,
        paddingwidth: 0,
        paddingheight: 0,
      });
      setBarcodeError(null);
    } catch (error) {
      console.error("Failed to render DataMatrix:", error);
      setBarcodeError("Не удалось сгенерировать DataMatrix. Проверьте корректность кода.");
    }
  }, [markingCode]);

  function handlePrint(event: FormEvent) {
    event.preventDefault();
    window.print();
  }

  const previewScale = 6;
  const previewWidth = selectedSize.widthMm * previewScale;
  const previewHeight = selectedSize.heightMm * previewScale;

  return (
    <div className="space-y-6 print:space-y-0">
      <header className="print:hidden">
        <h1 className="text-2xl font-semibold text-slate-900">Печать этикеток</h1>
        <p className="mt-1 text-sm text-slate-500">
          Настройте шаблон, проверьте предпросмотр и отправьте этикетку в печать.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[340px,1fr]">
        <form
          className="space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-4 print:hidden"
          onSubmit={handlePrint}
        >
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="label-size">
              Размер этикетки
            </label>
            <select
              id="label-size"
              value={sizeKey}
              onChange={(event) => setSizeKey(event.target.value as LabelSizeKey)}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-blue-500"
            >
              {LABEL_SIZES.map((size) => (
                <option key={size.key} value={size.key}>
                  {size.title}
                </option>
              ))}
            </select>
          </div>

          <InputField id="label-name" label="Наименование товара" value={name} onChange={setName} />
          <InputField id="label-article" label="Артикул" value={article} onChange={setArticle} />
          <InputField id="label-gtin" label="GTIN" value={gtin} onChange={setGtin} />
          <InputField id="label-product-size" label="Размер" value={productSize} onChange={setProductSize} />
          <InputField
            id="label-marking-code"
            label="Произвольный код маркировки"
            value={markingCode}
            onChange={setMarkingCode}
          />

          <button
            type="submit"
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
          >
            <Printer size={16} />
            Печать на принтере
          </button>
        </form>

        <section className="flex min-h-[360px] items-center justify-center rounded-xl border border-slate-200 bg-slate-50 p-6 print:min-h-0 print:border-0 print:bg-white print:p-0">
          <div
            className="overflow-hidden rounded bg-white text-slate-900 shadow-sm ring-1 ring-slate-200 print:rounded-none print:shadow-none print:ring-0"
            style={{
              width: `${previewWidth}px`,
              height: `${previewHeight}px`,
            }}
          >
            <div className="flex h-full min-h-0 flex-row gap-1 px-2 py-2">
              <div className="flex min-h-0 min-w-0 basis-[46%] flex-col justify-between text-[10px] leading-tight">
                <div>
                  <p className="line-clamp-3 font-semibold">{name || "Наименование товара"}</p>
                  <p className="mt-1">Арт: {article || "-"}</p>
                </div>
                <div className="mt-1 space-y-0.5">
                  <p className="break-all">GTIN: {gtin || "-"}</p>
                  <p className="break-words">Размер: {productSize || "-"}</p>
                </div>
              </div>
              <div className="flex min-h-0 min-w-0 flex-1 items-center justify-center">
                {barcodeError ? (
                  <p className="text-center text-[9px] leading-snug text-red-600">{barcodeError}</p>
                ) : (
                  <canvas
                    ref={canvasRef}
                    className="h-full max-h-full w-full object-contain"
                    aria-label="DataMatrix preview"
                  />
                )}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

type InputFieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (nextValue: string) => void;
};

function InputField({ id, label, value, onChange }: InputFieldProps) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-blue-500"
      />
    </div>
  );
}
