import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { api, errorMessage } from "../api/client";
import { SlaTimer } from "../components/SlaTimer";
import { StatusBadge } from "../components/StatusBadge";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, FilterTabs, Loading, PageHeader, Pagination, Panel, Table, Td, Th } from "../components/ui/Layout";
import { ConfirmDialog } from "../components/ui/Modal";
import { useToast } from "../components/ui/Toast";
import { useAuth } from "../hooks/auth";
import { customerHandle, fmtDuration, fmtRelativeDay } from "../lib/format";
import { useT } from "../lib/i18n";
import type { Incident, Page } from "../types/api";

type Filter = "open" | "overdue" | "breached" | "resolved" | "dismissed";

const RESOLUTION: Record<string, string> = {
  human_reply: "Telegramda javob",
  panel_reply: "Panel orqali javob",
  dismissed: "Qo'lda yopilgan",
};

export function IncidentsPage() {
  const [filter, setFilter] = useState<Filter>("open");
  const [page, setPage] = useState(1);
  const [dismiss, setDismiss] = useState<Incident | null>(null);
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const t = useT();

  const q = useQuery({
    queryKey: ["incidents", filter, page],
    queryFn: () => api.get<Page<Incident>>("/incidents", { status: filter, page, page_size: 25 }),
    refetchInterval: filter === "open" || filter === "overdue" ? 15_000 : false,
  });
  const dismissM = useMutation({
    mutationFn: (id: number) => api.post(`/incidents/${id}/dismiss`),
    onSuccess: () => {
      toast.ok(t("Murojaat yopildi"));
      setDismiss(null);
      qc.invalidateQueries({ queryKey: ["incidents"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const active = filter === "open" || filter === "overdue";

  return (
    <>
      <PageHeader
        title={t("Javobsiz murojaatlar")}
        description={t("Mijoz yozgan, lekin operator hali javob bermagan suhbatlar. Avtomatik javob hisobga olinmaydi.")}
      />
      <div className="mb-4">
        <FilterTabs<Filter>
          label={t("Holat bo'yicha filtr")}
          value={filter}
          onChange={(v) => {
            setFilter(v);
            setPage(1);
          }}
          options={[
            { value: "open", label: t("Kutmoqda") },
            { value: "overdue", label: t("Muddati o'tgan") },
            { value: "breached", label: t("Muddat buzilgan (barchasi)") },
            { value: "resolved", label: t("Javob berilgan") },
            { value: "dismissed", label: t("Yopilgan") },
          ]}
        />
      </div>
      <Panel padded={false}>
        {q.isLoading ? (
          <Loading />
        ) : q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !q.data?.items.length ? (
          <EmptyState
            title={active ? t("Javob kutayotgan mijoz yo'q") : t("Bu bo'limda yozuv yo'q")}
            description={active ? t("Yangi murojaat kelganda shu yerda paydo bo'ladi.") : undefined}
          />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>{t("Mijoz")}</Th>
                  <Th>{t("Birinchi xabar")}</Th>
                  <Th>{t("Murojaat vaqti")}</Th>
                  <Th>{active ? t("Kutish") : t("Javob vaqti")}</Th>
                  <Th>{t("Ogohlantirish")}</Th>
                  <Th className="text-right">{t("Amallar")}</Th>
                </tr>
              </thead>
              <tbody>
                {q.data.items.map((i) => (
                  <tr key={i.id}>
                    <Td>
                      <Link to={`/conversations/${i.conversation_id}`} className="font-medium hover:text-action">
                        {i.customer.display_name}
                      </Link>
                      <p className="text-[12.5px] text-ink-3">{customerHandle(i.customer)}</p>
                    </Td>
                    <Td className="max-w-[280px]">
                      <p className="line-clamp-2 text-ink-2">{i.first_message_preview ?? <span className="text-ink-3">—</span>}</p>
                      {i.customer_message_count > 1 && <p className="text-[12px] text-ink-3">{t("{n} ta xabar", { n: i.customer_message_count })}</p>}
                    </Td>
                    <Td className="whitespace-nowrap text-ink-2">{fmtRelativeDay(i.started_at)}</Td>
                    <Td>
                      {i.status === "open" ? (
                        <SlaTimer since={i.started_at} deadline={i.deadline_at} />
                      ) : (
                        <div>
                          <span className={`tabular font-medium ${i.breached_at ? "text-margin" : "text-calm"}`}>
                            {fmtDuration(i.response_seconds)}
                          </span>
                          <p className="text-[12px] text-ink-3">{i.resolution ? t(RESOLUTION[i.resolution]) : ""}</p>
                        </div>
                      )}
                    </Td>
                    <Td>
                      <StatusBadge kind="alert" value={i.alert_status} />
                      {i.alert_error && <p className="mt-1 max-w-[200px] text-[12px] text-margin">{i.alert_error}</p>}
                    </Td>
                    <Td className="text-right">
                      <div className="flex justify-end gap-2">
                        <Link
                          to={`/conversations/${i.conversation_id}`}
                          className="inline-flex h-8 items-center rounded-[var(--radius-control)] border border-line-strong px-3 text-[13px] font-medium hover:bg-paper"
                        >
                          {t("Ochish")}
                        </Link>
                        {i.status === "open" && can("incidents.dismiss") && (
                          <Button size="sm" variant="ghost" onClick={() => setDismiss(i)}>
                            {t("Yopish")}
                          </Button>
                        )}
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} pageSize={25} total={q.data.total} onChange={setPage} />
          </>
        )}
      </Panel>
      <ConfirmDialog
        open={!!dismiss}
        title={t("Murojaatni javobsiz yopish")}
        message={
          <>
            <b>{dismiss?.customer.display_name}</b>{" "}
            {t("murojaati javob talab qilmaydi deb belgilanadi (masalan, mijoz faqat «rahmat» yozgan). Ogohlantirish yuborilmaydi. Bu amal audit jurnaliga yoziladi.")}
          </>
        }
        confirmLabel={t("Yopish")}
        loading={dismissM.isPending}
        onConfirm={() => dismiss && dismissM.mutate(dismiss.id)}
        onCancel={() => setDismiss(null)}
      />
    </>
  );
}
