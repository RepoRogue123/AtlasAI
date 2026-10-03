import { AnimatePresence, motion } from "framer-motion";
import { Database, ShieldAlert } from "lucide-react";
import type { AtlasEvent } from "../lib/api";
import type { Fact } from "../lib/useRunStream";
import { Empty, Panel } from "./ui";

export default function MemoryPanel({ facts, security, onShot }: {
  facts: Fact[]; security: AtlasEvent[]; onShot: (url: string) => void;
}) {
  return (
    <Panel className="flex-1" title="Working memory" right={<span className="font-mono text-[10.5px] text-ink-400">{facts.length} facts</span>}
           bodyClass="overflow-y-auto p-3 scroll-thin">
      {security.length > 0 && (
        <div className="mb-3 rounded-xl border border-risk/30 bg-risk/[0.07] p-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-risk"><ShieldAlert size={14} /> Injection guard</div>
          <p className="mt-1 text-[11.5px] leading-relaxed text-ink-300">
            {security.filter((s) => s.data.kind === "injection_detected").length} attempt(s) detected ·{" "}
            {security.filter((s) => s.data.kind === "blocked").length} action(s) blocked
          </p>
        </div>
      )}
      {facts.length === 0 ? (
        <Empty icon={<Database size={22} />} title="Nothing remembered yet">Values the agent discovers appear here with provenance.</Empty>
      ) : (
        <div className="space-y-2">
          <AnimatePresence>
            {facts.map((f) => (
              <motion.button key={f.key} layout initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }}
                             onClick={() => f.screenshot && onShot(f.screenshot)}
                             className="w-full rounded-xl border border-white/[0.06] bg-white/[0.02] p-2.5 text-left transition hover:border-verified/30">
                <div className="font-mono text-[10.5px] text-ink-400">{f.key}</div>
                <div className="mt-0.5 break-words text-[13px] font-semibold text-ink-100">{f.value}</div>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  <span className="chip max-w-full truncate border-info/25 text-info" title={f.source}>{f.source}</span>
                  <span className="chip border-white/10 text-ink-400">step {f.step}</span>
                </div>
              </motion.button>
            ))}
          </AnimatePresence>
        </div>
      )}
    </Panel>
  );
}
