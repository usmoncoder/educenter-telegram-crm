import { CheckCircle2, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

interface ToastItem {
  id: number;
  tone: "ok" | "error";
  message: string;
}

const ToastContext = createContext<(tone: ToastItem["tone"], message: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((tone: ToastItem["tone"], message: string) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs.slice(-3), { id, tone, message }]);
    window.setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), tone === "error" ? 7000 : 4000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col items-end gap-2 sm:left-auto">
        {items.map((t) => (
          <div
            key={t.id}
            role={t.tone === "error" ? "alert" : "status"}
            className="pointer-events-auto flex max-w-sm items-start gap-2.5 rounded-[var(--radius-panel)] bg-board px-4 py-3 text-sm text-white shadow-[0_12px_30px_-12px_rgba(24,33,30,0.5)]"
          >
            {t.tone === "ok" ? (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-board-300" aria-hidden />
            ) : (
              <XCircle className="mt-0.5 size-4 shrink-0 text-[#f19a8f]" aria-hidden />
            )}
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const push = useContext(ToastContext);
  return {
    ok: (message: string) => push("ok", message),
    error: (message: string) => push("error", message),
  };
}
