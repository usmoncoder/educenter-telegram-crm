import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { api } from "../api/client";
import { SlaTimer } from "../components/SlaTimer";
import { StatusBadge } from "../components/StatusBadge";
import { Input } from "../components/ui/Field";
import { EmptyState, ErrorState, FilterTabs, Loading, PageHeader, Pagination, Panel, Table, Td, Th } from "../components/ui/Layout";
import { useAuth } from "../hooks/auth";
import { customerHandle, fmtRelativeDay } from "../lib/format";
import { useT } from "../lib/i18n";
import type { Conversation, Page } from "../types/api";

type Filter = "all" | "unresolved" | "overdue" | "resolved";

export function ConversationsPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [mine, setMine] = useState(false);
  const [page, setPage] = useState(1);
  const { can } = useAuth();
  const t = useT();
  const q = useQuery({
    queryKey: ["conversations", filter, search, mine, page],
    queryFn: () =>
      api.get<Page<Conversation>>("/conversations", {
        status: filter,
        search: search.trim() || undefined,
        assigned: mine ? "me" : undefined,
        page,
        page_size: 25,
      }),
    refetchInterval: 20_000,
    placeholderData: (prev) => prev,
  });

  return (
    <>
      <PageHeader
        title={t("Suhbatlar")}
        description={
          can("conversations.view_all")
            ? t("Mijozlar bilan barcha shaxsiy suhbatlar.")
            : t("Sizga biriktirilgan va hali hech kimga biriktirilmagan suhbatlar.")
        }
      />
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <FilterTabs<Filter>
          label={t("Holat")}
          value={filter}
          onChange={(v) => {
            setFilter(v);
            setPage(1);
          }}
          options={[
            { value: "all", label: t("Barchasi") },
            { value: "unresolved", label: t("Javob kutmoqda") },
            { value: "overdue", label: t("Muddati o'tgan") },
            { value: "resolved", label: t("Javob berilgan") },
          ]}
        />
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-[13px] text-ink-2">
            <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} className="size-4 accent-action" />
            {t("Faqat menga biriktirilgan")}
          </label>
          <div className="relative w-full lg:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
            <Input
              aria-label={t("Qidirish")}
              placeholder={t("Ism, @username yoki ID")}
              className="pl-9"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>
      </div>
      <Panel padded={false}>
        {q.isLoading ? (
          <Loading />
        ) : q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !q.data?.items.length ? (
          <EmptyState
            title={search ? t("Hech narsa topilmadi") : t("Suhbatlar yo'q")}
            description={search ? t("Boshqa ism yoki ID bilan qidirib ko'ring.") : t("Mijoz yozganda suhbat shu yerda paydo bo'ladi.")}
          />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>{t("Mijoz")}</Th>
                  <Th>{t("Mijozning oxirgi xabari")}</Th>
                  <Th>{t("Oxirgi kiruvchi")}</Th>
                  <Th>{t("Oxirgi javob")}</Th>
                  <Th>{t("Holat")}</Th>
                  <Th>{t("Mas'ul")}</Th>
                </tr>
              </thead>
              <tbody>
                {q.data.items.map((c) => (
                  <tr key={c.id} className="hover:bg-paper/60">
                    <Td>
                      <Link to={`/conversations/${c.id}`} className="font-medium hover:text-action">
                        {c.customer.display_name}
                      </Link>
                      <p className="text-[12.5px] text-ink-3">{customerHandle(c.customer)}</p>
                    </Td>
                    <Td className="max-w-[260px]">
                      <p className="truncate text-ink-2">{c.last_message_preview ?? <span className="text-ink-3">—</span>}</p>
                    </Td>
                    <Td className="whitespace-nowrap text-ink-2">{fmtRelativeDay(c.last_incoming_at)}</Td>
                    <Td className="whitespace-nowrap text-ink-2">{fmtRelativeDay(c.last_human_reply_at)}</Td>
                    <Td>
                      {c.waiting_since && c.deadline_at ? (
                        <SlaTimer since={c.waiting_since} deadline={c.deadline_at} compact />
                      ) : (
                        <StatusBadge kind="sla" value={c.sla_state} />
                      )}
                    </Td>
                    <Td className="whitespace-nowrap text-ink-2">{c.assigned_admin_name ?? <span className="text-ink-3">—</span>}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} pageSize={25} total={q.data.total} onChange={setPage} />
          </>
        )}
      </Panel>
    </>
  );
}
