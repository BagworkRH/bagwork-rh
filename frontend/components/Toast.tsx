"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

import { AlertIcon, CheckIcon, CloseIcon, InfoIcon } from "@/components/icons";

type ToastKind = "success" | "error" | "info";

type ToastItem = {
  id: number;
  kind: ToastKind;
  title: string;
  body?: string;
};

type ToastApi = {
  notify: (toast: { kind?: ToastKind; title: string; body?: string }) => void;
  success: (title: string, body?: string) => void;
  error: (title: string, body?: string) => void;
};

const ToastContext = createContext<ToastApi | null>(null);

/**
 * App-wide toasts.
 *
 * A component may call `useToast()` outside the provider (a page rendered in
 * isolation, a test) without crashing — it simply gets a no-op, because a
 * missing notification is a far smaller failure than a thrown one.
 */
export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  return (
    ctx ?? {
      notify: () => {},
      success: () => {},
      error: () => {},
    }
  );
}

const ICONS = {
  success: CheckIcon,
  error: AlertIcon,
  info: InfoIcon,
} as const;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const remove = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const notify = useCallback(
    ({ kind = "info", title, body }: { kind?: ToastKind; title: string; body?: string }) => {
      const id = nextId.current++;
      setItems((current) => [...current, { id, kind, title, body }]);
      // Errors linger a little longer: they usually carry something to read.
      window.setTimeout(() => remove(id), kind === "error" ? 6500 : 4200);
    },
    [remove]
  );

  const api = useMemo<ToastApi>(
    () => ({
      notify,
      success: (title, body) => notify({ kind: "success", title, body }),
      error: (title, body) => notify({ kind: "error", title, body }),
    }),
    [notify]
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {items.map((item) => {
          const Icon = ICONS[item.kind];
          return (
            <div key={item.id} className={`toast toast-${item.kind}`}>
              <Icon size={18} />
              <div>
                <div className="toast-title">{item.title}</div>
                {item.body ? <p className="toast-body">{item.body}</p> : null}
              </div>
              <button className="toast-close" onClick={() => remove(item.id)} aria-label="Dismiss">
                <CloseIcon size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
