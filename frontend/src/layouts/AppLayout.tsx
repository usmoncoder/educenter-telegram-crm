import { useMutation, useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  CalendarClock,
  History,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageCircleReply,
  MessagesSquare,
  PlugZap,
  ScrollText,
  Settings,
  ShieldCheck,
  TimerReset,
  Users,
  UsersRound,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router";

import { api } from "../api/client";
import { ConnectionPill } from "../components/ConnectionPill";
import { useAuth } from "../hooks/auth";
import { ROLE_LABEL } from "../lib/format";
import { LANGS, useLang, useT } from "../lib/i18n";
import type { Page, Incident } from "../types/api";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  perm: string;
  badge?: "overdue";
}

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Murojaatlar",
    items: [
      { to: "/", label: "Dashboard", icon: <LayoutDashboard />, perm: "dashboard.view" },
      { to: "/incidents", label: "Javobsiz murojaatlar", icon: <TimerReset />, perm: "conversations.view", badge: "overdue" },
      { to: "/conversations", label: "Suhbatlar", icon: <MessagesSquare />, perm: "conversations.view" },
      { to: "/customers", label: "Mijozlar", icon: <Users />, perm: "customers.view" },
      { to: "/autoreply", label: "Avtomatik javoblar", icon: <MessageCircleReply />, perm: "autoreply.manage" },
    ],
  },
  {
    group: "E'lonlar",
    items: [
      { to: "/groups", label: "Telegram guruhlari", icon: <UsersRound />, perm: "groups.view" },
      { to: "/campaigns", label: "Rejalashtirilgan xabarlar", icon: <CalendarClock />, perm: "campaigns.view" },
      { to: "/history", label: "Xabarlar tarixi", icon: <History />, perm: "history.view" },
      { to: "/reports", label: "Hisobotlar", icon: <BarChart3 />, perm: "reports.view" },
    ],
  },
  {
    group: "Tizim",
    items: [
      { to: "/telegram", label: "Telegram ulanishi", icon: <PlugZap />, perm: "telegram.view" },
      { to: "/admins", label: "Administratorlar", icon: <ShieldCheck />, perm: "admins.manage" },
      { to: "/settings", label: "Sozlamalar", icon: <Settings />, perm: "settings.manage" },
      { to: "/audit", label: "Audit jurnali", icon: <ScrollText />, perm: "audit.view" },
    ],
  },
];

function OverdueCount() {
  const { data } = useQuery({
    queryKey: ["incidents", "overdue-count"],
    queryFn: () => api.get<Page<Incident>>("/incidents", { status: "overdue", page_size: 1 }),
    refetchInterval: 20_000,
  });
  if (!data?.total) return null;
  return (
    <span className="tabular ml-auto rounded-full bg-margin px-1.5 py-px text-[11.5px] font-semibold text-white">
      {data.total}
    </span>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { can } = useAuth();
  const t = useT();
  return (
    <nav aria-label={t("Asosiy menyu")} className="flex flex-col gap-5 px-3 pb-6">
      {NAV.map((section) => {
        const items = section.items.filter((i) => can(i.perm));
        if (!items.length) return null;
        return (
          <div key={section.group}>
            <p className="px-3 pb-1.5 text-[12px] font-medium text-board-300/80">{t(section.group)}</p>
            <ul className="flex flex-col gap-0.5">
              {items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === "/"}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 rounded-[7px] px-3 py-2 text-[14px] transition-colors [&>svg]:size-[17px] [&>svg]:shrink-0 ${
                        isActive ? "bg-board-600 font-medium text-white" : "text-white/75 hover:bg-board-700 hover:text-white"
                      }`
                    }
                  >
                    {item.icon}
                    <span className="truncate">{t(item.label)}</span>
                    {item.badge === "overdue" && <OverdueCount />}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

function LangSwitch() {
  const { lang, setLang } = useLang();
  return (
    <div className="flex items-center rounded-md border border-line p-0.5" role="group" aria-label="Til / Язык">
      {LANGS.map((l) => (
        <button
          key={l.code}
          onClick={() => setLang(l.code)}
          className={`rounded px-2 py-1 text-[12.5px] font-medium transition-colors ${
            lang === l.code ? "bg-ink/10 text-ink" : "text-ink-3 hover:text-ink"
          }`}
          aria-pressed={lang === l.code}
        >
          {l.code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

function Brand() {
  const t = useT();
  return (
    <div className="flex items-center gap-2.5 px-6 py-5">
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
        <rect width="32" height="32" rx="7" fill="#F6F8F7" />
        <path d="M10 11h13M10 16h13M10 21h8" stroke="#1E3A33" strokeWidth="2.4" strokeLinecap="round" />
        <path d="M6.5 5v22" stroke="#C33A2C" strokeWidth="1.8" />
      </svg>
      <div className="leading-tight">
        <p className="text-[15px] font-semibold text-white">EduCenter CRM</p>
        <p className="text-[12px] text-board-300">{t("Murojaatlar nazorati")}</p>
      </div>
    </div>
  );
}

function loadCollapsed(): boolean {
  try {
    return localStorage.getItem("sidebar_collapsed") === "1";
  } catch {
    return false;
  }
}

export function AppLayout() {
  const { me, setMe } = useAuth();
  const t = useT();
  const [drawer, setDrawer] = useState(false);
  const [collapsed, setCollapsed] = useState(loadCollapsed);
  const location = useLocation();
  useEffect(() => setDrawer(false), [location.pathname]);

  // The hamburger toggles the persistent sidebar on desktop and the overlay drawer on mobile.
  const toggleMenu = () => {
    if (typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches) {
      setCollapsed((c) => {
        const next = !c;
        try {
          localStorage.setItem("sidebar_collapsed", next ? "1" : "0");
        } catch {
          /* ignore storage errors */
        }
        return next;
      });
    } else {
      setDrawer(true);
    }
  };

  const logout = useMutation({
    mutationFn: () => api.post("/auth/logout"),
    onSettled: () => setMe(null),
  });

  return (
    <div className={`min-h-dvh ${collapsed ? "" : "lg:pl-[264px]"}`}>
      <aside
        className={`fixed inset-y-0 left-0 z-30 hidden w-[264px] flex-col overflow-y-auto bg-board ${
          collapsed ? "" : "lg:flex"
        }`}
      >
        <Brand />
        <Sidebar />
      </aside>

      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label={t("Menyu")}>
          <button className="absolute inset-0 bg-board/50" aria-label={t("Menyuni yopish")} onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-[280px] max-w-[85vw] flex-col overflow-y-auto bg-board">
            <div className="flex items-center justify-between pr-3">
              <Brand />
              <button onClick={() => setDrawer(false)} className="rounded-md p-2 text-white/80 hover:bg-board-700" aria-label={t("Yopish")}>
                <X className="size-5" />
              </button>
            </div>
            <Sidebar onNavigate={() => setDrawer(false)} />
          </aside>
        </div>
      )}

      <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-line bg-paper/90 px-4 backdrop-blur sm:px-6">
        <button
          className="rounded-md p-2 text-ink-2 hover:bg-ink/5"
          onClick={toggleMenu}
          aria-label={t("Menyuni ochish/yopish")}
        >
          <Menu className="size-5" />
        </button>
        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          <LangSwitch />
          <ConnectionPill />
          <div className="hidden text-right leading-tight sm:block">
            <p className="text-[13.5px] font-medium text-ink">{me?.admin.full_name || me?.admin.username}</p>
            <p className="text-[12px] text-ink-3">{me ? t(ROLE_LABEL[me.admin.role]) : ""}</p>
          </div>
          <NavLink to="/account" className="rounded-md p-2 text-ink-2 hover:bg-ink/5" title={t("Parolni o'zgartirish")} aria-label={t("Parolni o'zgartirish")}>
            <KeyRound className="size-[18px]" />
          </NavLink>
          <button
            onClick={() => logout.mutate()}
            className="rounded-md p-2 text-ink-2 hover:bg-ink/5"
            title={t("Chiqish")}
            aria-label={t("Tizimdan chiqish")}
          >
            <LogOut className="size-[18px]" />
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1320px] px-4 py-6 sm:px-6 lg:py-8">
        <Outlet />
      </main>
    </div>
  );
}
