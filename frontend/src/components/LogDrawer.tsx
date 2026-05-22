import { useEffect, useRef } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { ScrapeJob } from "@/lib/api";

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  job: ScrapeJob | null;
};

export function LogDrawer({ open, onOpenChange, job }: Props) {
  const bodyRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [job?.log_total]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-[640px] max-w-full border-l border-slate-800 bg-slate-950 text-slate-200"
      >
        <SheetHeader>
          <SheetTitle className="font-mono text-sm uppercase tracking-widest text-slate-400">
            Scrape Job
            {job && (
              <span className="ml-3 text-slate-500">
                #{job.id} · {job.status}
                {job.rows_inserted ? ` · +${job.rows_inserted} rows` : ""}
              </span>
            )}
          </SheetTitle>
        </SheetHeader>
        <pre
          ref={bodyRef}
          className="mt-4 h-[calc(100vh-120px)] overflow-auto rounded border border-slate-800 bg-black p-3 font-mono text-xs leading-relaxed text-slate-300"
        >
          {job?.log.join("\n") || "等待輸出…"}
        </pre>
      </SheetContent>
    </Sheet>
  );
}
