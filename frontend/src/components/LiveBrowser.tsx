import { AnimatePresence, motion } from "framer-motion";
import clsx from "clsx";
import { Lock, MonitorPlay, ShieldCheck } from "lucide-react";
import type { Shot } from "../lib/useRunStream";

const TAG_LABEL: Record<string, string> = {
  target: "about to act on",
  approval: "awaiting approval",
  click: "after click",
  goto: "page loaded",
  submit: "submitted",
  type: "typed",
  select: "selected",
  observe: "observed",
  back: "went back",
  scroll: "scrolled",
};

export default function LiveBrowser({ shot, shots, onPick, live }: {
  shot: Shot | null; shots: Shot[]; onPick: (s: Shot) => void; live: boolean;
}) {
  const url = shot?.page_url ?? "about:blank";
  const secure = url.startsWith("https");
  return (
    <div className="panel flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex items-center gap-3 border-b border-white/[0.05] px-3 py-2">
        <div className="flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]/70" />
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg bg-ink-950/70 px-3 py-1 font-mono text-[11.5px] text-ink-300">
          {secure && <Lock size={11} className="text-verified" />}
          <span className="truncate">{url}</span>
        </div>
        {shot?.actor === "verifier" && (
          <span className="chip border-verified/40 bg-verified/10 text-verified"><ShieldCheck size={11} /> verifier tab</span>
        )}
        {shot && (
          <span className={clsx("chip", shot.tag === "target" || shot.tag === "approval"
            ? "border-risk/40 bg-risk/10 text-risk" : "border-white/10 text-ink-300")}>
            {TAG_LABEL[shot.tag] ?? shot.tag}{shot.target ? `: ${shot.target}` : ""}
          </span>
        )}
        {live && <span className="chip border-signal/30 text-signal"><span className="h-1.5 w-1.5 rounded-full bg-signal pulse-dot" /> LIVE</span>}
      </div>
      <div className={clsx("relative min-h-0 flex-1 bg-ink-950", live && !shot && "scanline")}>
        <AnimatePresence mode="popLayout">
          {shot ? (
            <motion.img key={shot.url} src={shot.url} alt={url}
                        initial={{ opacity: 0.4 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}
                        className="absolute inset-0 h-full w-full object-contain object-top" />
          ) : (
            <motion.div key="empty" className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-ink-400">
              <MonitorPlay size={34} className="text-ink-600" />
              <span className="text-sm">{live ? "Booting browser and planning..." : "No browser activity in this run"}</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      {shots.length > 0 && (
        <div className="flex gap-1.5 overflow-x-auto border-t border-white/[0.05] p-2 scroll-thin">
          {shots.map((s) => (
            <button key={s.seq} onClick={() => onPick(s)} title={`step ${s.step} · ${s.tag}`}
                    className={clsx("relative h-12 w-20 shrink-0 overflow-hidden rounded-md border transition",
                      shot?.seq === s.seq ? "border-signal" : "border-white/10 opacity-60 hover:opacity-100",
                      s.actor === "verifier" && "ring-1 ring-verified/50")}>
              <img src={s.url} alt="" className="h-full w-full object-cover object-top" loading="lazy" />
              <span className="absolute bottom-0 left-0 bg-ink-950/80 px-1 font-mono text-[9px] text-ink-300">{s.step}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
